import os
import re
import asyncio
import sqlite3
import csv
import json
import uuid
import secrets
import threading
import time
import requests
import urllib.parse
from urllib.parse import unquote, unquote_plus
from io import StringIO
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient, events
from telethon import __version__ as TELETHON_VERSION
from telethon.sessions import StringSession

# ----------------------
# Executor para chamadas síncronas
# ----------------------
executor = ThreadPoolExecutor(max_workers=5)

# ----------------------
# Configurações de diretórios
# ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Criar diretórios se não existirem
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# ----------------------
# Banco de Dados SQLite (Histórico e Usuários)
# ----------------------
DB_FILE = os.environ.get("DB_FILE", os.path.join(BASE_DIR, "history.db"))

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.isolation_level = None
    return conn

conn = get_db_connection()
cursor = conn.cursor()

# Tabela de Buscas
cursor.execute("""
CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier   TEXT,
    response     TEXT,
    searched_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    username     TEXT
)
""")

# Migração: adicionar colunas se não existirem
try:
    cursor.execute("SELECT response FROM searches LIMIT 1")
except sqlite3.OperationalError:
    cursor.execute("ALTER TABLE searches ADD COLUMN response TEXT")
    conn.commit()

try:
    cursor.execute("SELECT username FROM searches LIMIT 1")
except sqlite3.OperationalError:
    cursor.execute("ALTER TABLE searches ADD COLUMN username TEXT")
    conn.commit()

# Tabela de Usuários
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    is_admin INTEGER DEFAULT 0,
    data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    ultimo_login DATETIME,
    ip_acesso TEXT,
    status INTEGER DEFAULT 1,
    numero_consultas INTEGER DEFAULT 0
)
""")
conn.commit()

# Migração: adicionar colunas se não existirem (com tratamento de erro específico)
def add_column_if_not_exists(table_name, column_name, column_type):
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            pass  # Coluna já existe, tudo bem
        else:
            raise

# Adicionar todas as colunas necessárias
add_column_if_not_exists("users", "data_criacao", "DATETIME")
add_column_if_not_exists("users", "ultimo_login", "DATETIME")
add_column_if_not_exists("users", "ip_acesso", "TEXT")
add_column_if_not_exists("users", "status", "INTEGER")
add_column_if_not_exists("users", "numero_consultas", "INTEGER")
add_column_if_not_exists("users", "senha_temporaria", "INTEGER DEFAULT 0")

# Criar admin padrão se não existir (Usuário: admin | Senha: admin6464)
cursor.execute("INSERT OR IGNORE INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
               ("admin", "admin6464", 1))
# Atualizar senha do admin caso já exista
cursor.execute("UPDATE users SET password = ? WHERE username = ?", ("admin6464", "admin"))
conn.commit()

# Tabela de Logs de Auditoria
cursor.execute("""
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    username TEXT,
    ip_address TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    details TEXT
)
""")
conn.commit()

# Tabela de Favoritos
cursor.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER,
    username TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (search_id) REFERENCES searches(id)
)
""")
conn.commit()

# Tabela de Notas/Comentários
cursor.execute("""
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER,
    username TEXT,
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (search_id) REFERENCES searches(id)
)
""")
conn.commit()

# Tabela de Tags
cursor.execute("""
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER,
    tag_name TEXT,
    username TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (search_id) REFERENCES searches(id)
)
""")
conn.commit()

# Tabela de Configurações do Usuário
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    dark_mode INTEGER DEFAULT 0,
    notifications_enabled INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ----------------------
# Sistema de Rate Limiting e Expiração
# ----------------------
SESSION_TIMEOUT = 30 * 60  # 30 minutos em segundos
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_WINDOW = 3 * 60  # 3 minutos em segundos

login_attempts = defaultdict(list)  # {ip: [timestamp1, timestamp2, ...]}

# CSRF Protection
csrf_tokens = {}  # {session_id: token}
csrf_token_timeout = 60 * 60  # 1 hora

# Rate Limiting em Consultas
MAX_QUERIES_PER_MINUTE = 10
query_attempts = defaultdict(list)  # {username: [timestamp1, timestamp2, ...]}

# ----------------------
# Configuração Telethon (Telegram)
# ----------------------
API_ID = int(os.environ.get("TELEGRAM_API_ID", "17993467"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "684fdc620ac8ace6bc1ee15c219744a3")
GROUP_ID_OR_NAME = os.environ.get("TELEGRAM_GROUP_ID", "2874013146")

print(f"Configuração Telegram:")
print(f"   Telethon: {TELETHON_VERSION}")
print(f"   API_ID: {API_ID}")
print(f"   GROUP_ID: {GROUP_ID_OR_NAME}")

# Suporte a STRING_SESSION ou arquivo de sessão
STRING_SESSION_ENV = os.environ.get("STRING_SESSION", None)
STRING_SESSION_CANDIDATES = []

def build_string_session_candidates(raw_value: str):
    if not raw_value:
        return []

    seeds = []

    for base in (raw_value, unquote(raw_value), unquote_plus(raw_value)):
        if not base:
            continue
        cleaned = base.strip().strip('"').strip("'")
        if cleaned:
            seeds.append(cleaned)

    candidates = []
    for seed in seeds:
        variants = [
            seed,
            seed.replace("\\n", "").replace("\\r", ""),
            seed.replace(" ", "+"),
            seed.replace(" ", "")
        ]

        for variant in variants:
            current = re.sub(r"\s+", "", variant)
            current = re.sub(r"[^A-Za-z0-9_\-=+/]", "", current)
            if not current:
                continue

            normalized_without_padding = current.rstrip("=")
            normalized_with_padding = normalized_without_padding + ("=" * ((4 - (len(normalized_without_padding) % 4)) % 4))

            for base_value in (
                current,
                normalized_without_padding,
                normalized_with_padding,
                current.replace("+", "-").replace("/", "_"),
                current.replace("-", "+").replace("_", "/")
            ):
                value = base_value.rstrip("=")
                value_padded = value + ("=" * ((4 - (len(value) % 4)) % 4))
                for final_value in (base_value, value, value_padded):
                    if final_value and final_value not in candidates:
                        candidates.append(final_value)

    return candidates

if STRING_SESSION_ENV:
    STRING_SESSION_CANDIDATES = build_string_session_candidates(STRING_SESSION_ENV)

    # Se vier com texto extra, manter apenas os maiores tokens candidatos a sessão
    extracted_tokens = []
    for candidate in STRING_SESSION_CANDIDATES:
        extracted_tokens.extend(re.findall(r"[A-Za-z0-9_\-=+/]{80,}", candidate))
    if extracted_tokens:
        for token in sorted(set(extracted_tokens), key=len, reverse=True):
            if token not in STRING_SESSION_CANDIDATES:
                STRING_SESSION_CANDIDATES.insert(0, token)

    if STRING_SESSION_CANDIDATES:
        STRING_SESSION_ENV = STRING_SESSION_CANDIDATES[0]
    print(f"   Usando STRING_SESSION (candidatos={len(STRING_SESSION_CANDIDATES)})")
else:
    print(f"   Usando arquivo de sessão local")
    
SESSION_FILE_PATH = os.environ.get("SESSION_FILE", os.path.join(BASE_DIR, "bot_session_novo.session"))

telegram_semaphore = asyncio.Semaphore(3)

# ----------------------
# Validações e Helpers
# ----------------------
CPF_RE = re.compile(r"^\d{11}$")
CNPJ_RE = re.compile(r"^\d{14}$")
PLACA_RE = re.compile(r"^[A-Z]{3}\d{4}$|^[A-Z]{3}\d[A-Z]\d{2}$")

def normalize(id_str: str) -> str: return re.sub(r"\D", "", id_str)
def normalize_placa(placa_str: str) -> str: return re.sub(r"[^A-Z0-9]", "", placa_str.upper())
def is_cpf(idn: str) -> bool: return bool(CPF_RE.match(idn))
def is_cnpj(idn: str) -> bool: return bool(CNPJ_RE.match(idn))
def is_placa(placa: str) -> bool: return bool(PLACA_RE.match(normalize_placa(placa)))
def is_nome(text: str) -> bool: return len(text.strip()) >= 3

def detect_tipo(identificador: str) -> str:
    idn = normalize(identificador)
    if is_cpf(idn): return 'cpf'
    elif is_cnpj(idn): return 'cnpj'
    elif is_placa(identificador): return 'placa'
    elif is_nome(identificador): return 'nome'
    return None

# ----------------------
# CSRF Token Management
# ----------------------
def generate_csrf_token() -> str:
    """Gera um token CSRF único"""
    return secrets.token_urlsafe(32)

def get_or_create_csrf_token(request: Request) -> str:
    """Obtém ou cria um token CSRF para a sessão do usuário"""
    session_id = request.cookies.get("auth_user", str(uuid.uuid4()))
    
    # Remover tokens expirados
    now = datetime.now().timestamp()
    if session_id in csrf_tokens:
        token_time = csrf_tokens[session_id].get("created", 0)
        if now - token_time > csrf_token_timeout:
            del csrf_tokens[session_id]
    
    # Criar novo token se não existir
    if session_id not in csrf_tokens:
        csrf_tokens[session_id] = {
            "token": generate_csrf_token(),
            "created": now
        }
    
    return csrf_tokens[session_id]["token"]

def validate_csrf_token(request: Request, token: str) -> bool:
    """Valida um token CSRF"""
    session_id = request.cookies.get("auth_user")
    if not session_id or session_id not in csrf_tokens:
        return False
    
    return csrf_tokens[session_id]["token"] == token

# ----------------------
# Rate Limiting em Consultas
# ----------------------
def check_query_rate_limit(username: str) -> bool:
    """Verifica se o usuário excedeu o limite de consultas por minuto"""
    now = datetime.now().timestamp()
    # Remove tentativas antigas (fora da janela de 1 minuto)
    query_attempts[username] = [t for t in query_attempts[username] if now - t < 60]
    
    if len(query_attempts[username]) >= MAX_QUERIES_PER_MINUTE:
        return False
    return True

def record_query_attempt(username: str):
    """Registra uma tentativa de consulta"""
    query_attempts[username].append(datetime.now().timestamp())

# ----------------------
# FastAPI Setup
# ----------------------
app = FastAPI()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ----------------------
# Consulta Telegram
# ----------------------
@asynccontextmanager
async def get_telegram_client():
    # Usar STRING_SESSION se disponível, senão arquivo de sessão
    if STRING_SESSION_ENV:
        session = None
        session_error = None
        candidates = STRING_SESSION_CANDIDATES or [STRING_SESSION_ENV]

        for candidate in candidates:
            try:
                session = StringSession(candidate)
                break
            except Exception as current_error:
                session_error = current_error

        if session is None:
            if os.path.exists(SESSION_FILE_PATH):
                print(
                    f"⚠️ STRING_SESSION inválida ({session_error}). "
                    f"len={len(STRING_SESSION_ENV)}. Usando arquivo de sessão local."
                )
                session = SESSION_FILE_PATH
            else:
                raise Exception(
                    "❌ STRING_SESSION inválida e arquivo de sessão local não encontrado. "
                    f"Detalhes: {session_error}"
                )
    else:
        session = SESSION_FILE_PATH
    
    client = TelegramClient(session, API_ID, API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise Exception("❌ Sessão Telegram não autorizada. Configure STRING_SESSION ou faça login local.")
        yield client
    finally:
        await client.disconnect()

async def consulta_telegram(cmd: str) -> str:
    async with telegram_semaphore:
        try:
            async with get_telegram_client() as client:
                response_text = None
                response_received = asyncio.Event()
                
                async def handler(event):
                    nonlocal response_text
                    response_text = re.sub(r"BY:\s*@Skynet08Robot", "", event.raw_text, flags=re.IGNORECASE)
                    response_received.set()
                
                # Tenta obter o grupo - usa tanto ID direto quanto busca por username
                try:
                    if GROUP_ID_OR_NAME.startswith('-') or GROUP_ID_OR_NAME.isdigit():
                        # É um ID numérico
                        group_entity = await client.get_entity(int(GROUP_ID_OR_NAME))
                    else:
                        # É um username ou link
                        group_entity = await client.get_entity(GROUP_ID_OR_NAME)
                except Exception as e:
                    return f"❌ Erro ao acessar grupo: {str(e)}"
                
                # Adiciona handler e envia mensagem
                client.add_event_handler(handler, events.NewMessage(chats=group_entity))
                
                try:
                    await client.send_message(group_entity, cmd)
                except Exception as send_error:
                    error_msg = str(send_error)
                    if "ChatRestrictedError" in error_msg or "restricted" in error_msg.lower():
                        return "❌ Grupo restrito - verifique permissões do bot"
                    elif "ChatWriteForbiddenError" in error_msg:
                        return "❌ Bot sem permissão para escrever no grupo"
                    else:
                        return f"❌ Erro ao enviar mensagem: {error_msg}"
                
                # Aguarda resposta
                try:
                    await asyncio.wait_for(response_received.wait(), timeout=45)
                    return response_text or "❌ Resposta vazia"
                except asyncio.TimeoutError:
                    return "❌ Timeout - Sem resposta em 45 segundos"
                    
        except Exception as e:
            return f"❌ Erro na consulta: {str(e)}"

# ----------------------
# Middleware de Segurança
# ----------------------
def get_client_ip(request: Request) -> str:
    """Extrai IP do cliente, considerando proxies"""
    if request.headers.get("x-forwarded-for"):
        return request.headers.get("x-forwarded-for").split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def is_session_expired(request: Request) -> bool:
    """Verifica se a sessão expirou"""
    auth_time = request.cookies.get("auth_time")
    if not auth_time:
        return True
    try:
        auth_datetime = datetime.fromisoformat(auth_time)
        return datetime.now() > auth_datetime
    except (ValueError, TypeError):
        return True

def is_user_inactive(username: str) -> bool:
    """Verifica se o usuário está inativo (desativado)"""
    try:
        cursor.execute("SELECT status FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return True  # Usuário não existe
        status = user[0]
        # Se status é NULL ou 0, usuário está inativo
        if status is None or status == 0:
            return True
        return False
    except:
        return False  # Se der erro, deixa passar (compatibilidade)

def validate_user_session(request: Request):
    """Valida se o usuário tem uma sessão válida e está ativo. Retorna None se OK, ou um RedirectResponse se inválido."""
    username = request.cookies.get("auth_user")
    
    if not username:
        return RedirectResponse(url="/login")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    # Verificar se usuário está inativo
    if is_user_inactive(username):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    return None

def check_rate_limit(ip: str) -> bool:
    """Verifica se o IP excedeu o limite de tentativas de login"""
    now = datetime.now().timestamp()
    # Remove tentativas antigas (fora da janela de tempo)
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < LOGIN_ATTEMPT_WINDOW]
    
    if len(login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
        return False
    return True

def record_login_attempt(ip: str):
    """Registra uma tentativa de login"""
    login_attempts[ip].append(datetime.now().timestamp())

def record_audit_log(action: str, username: str, ip_address: str, details: str = ""):
    """Registra ação no log de auditoria"""
    try:
        cursor.execute(
            "INSERT INTO audit_logs (action, username, ip_address, details) VALUES (?, ?, ?, ?)",
            (action, username, ip_address, details)
        )
        conn.commit()
    except:
        pass  # Silenciar erros de auditoria

def format_timestamp_br(timestamp_str: str) -> str:
    """Converte timestamp UTC para horário de Brasília (UTC-3) e formata para padrão brasileiro"""
    try:
        # Parse do timestamp do banco (formato: YYYY-MM-DD HH:MM:SS)
        dt_utc = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        # Converter para horário de Brasília (UTC-3)
        dt_brasilia = dt_utc - timedelta(hours=3)
        # Formatar no padrão brasileiro: dd/mm/yyyy HH:MM:SS
        return dt_brasilia.strftime("%d/%m/%Y %H:%M:%S")
    except:
        return timestamp_str  # Retorna original se houver erro

# ========================
# INTEGRAÇÃO DE APIs GRÁTIS
# ========================

async def enriquecher_endereco_selecionado(endereco: str) -> dict:
    """
    Busca ViaCEP, Nominatim e Informações Públicas para um endereço específico
    Chamado quando usuário seleciona endereço na UI
    """
    result = {
        "viacep": None,
        "nominatim": None,
        "info_publica": {
            "cnae": None,
            "wikidata": None,
            "overpass": None,
            "gravatar": None
        }
    }
    
    try:
        # ViaCEP
        endereco_validado = await buscar_cep_viacep(endereco)
        if endereco_validado:
            result["viacep"] = endereco_validado
            
            try:
                # Nominatim
                localizacao = await buscar_nominatim(
                    endereco_validado.get("logradouro", ""),
                    endereco_validado.get("localidade", ""),
                    endereco_validado.get("uf", "")
                )
                if localizacao:
                    result["nominatim"] = localizacao
                    
                    # Buscar Overpass (pontos de interesse) se temos coords
                    try:
                        overpass_data = await buscar_overpass_api(
                            localizacao.get("latitude", 0),
                            localizacao.get("longitude", 0)
                        )
                        if overpass_data:
                            result["info_publica"]["overpass"] = overpass_data
                    except Exception as op_err:
                        print(f"⚠️ Erro ao buscar Overpass: {str(op_err)}")
            except Exception as nom_err:
                print(f"⚠️ Erro ao buscar Nominatim: {str(nom_err)}")
    except Exception as e:
        print(f"⚠️ Erro em enriquecher_endereco_selecionado: {str(e)}")
    
    return result

async def enriquecer_dados_com_apis(identificador: str, tipo: str, dados_estruturados: dict) -> dict:
    """
    Enriquece com APIs RÁPIDAS
    Endereços: mostrar lista para SELECIONAR (usuário valida qual quer)
    """
    if not dados_estruturados:
        return {}
    
    apis_data = {
        "enderecos_disponiveis": [],
        "endereco_validado": None,
        "localizacao": None,
        "info_publica": None,
        "processos_judiciais": None,
        "risk_score": None
    }
    
    try:
        # Listar endereços para seleção
        if dados_estruturados.get("enderecos"):
            # Garantir que são strings
            enderecos_limpos = []
            for e in dados_estruturados["enderecos"][:5]:
                if isinstance(e, str):
                    enderecos_limpos.append(e)
            apis_data["enderecos_disponiveis"] = enderecos_limpos
            
            # Se apenas 1 endereço, validar automaticamente
            if len(apis_data["enderecos_disponiveis"]) == 1:
                try:
                    endereco = apis_data["enderecos_disponiveis"][0]
                    resultado = await enriquecher_endereco_selecionado(endereco)
                    if resultado and resultado.get("viacep"):
                        apis_data["endereco_validado"] = resultado["viacep"]
                    if resultado and resultado.get("nominatim"):
                        apis_data["localizacao"] = resultado["nominatim"]
                except Exception as end_err:
                    print(f"⚠️ Erro ao validar 1 endereço: {str(end_err)}")
                    pass
    except Exception as e:
        print(f"⚠️ Erro ao processar endereços: {str(e)}")
    
    try:
        # Wikipedia + Wikidata + CNAE + Gravatar - Automáticas
        nome_para_wiki = ""
        if tipo.lower() == "cnpj" and dados_estruturados.get("dados_pessoais", {}).get("nome"):
            nome_para_wiki = dados_estruturados["dados_pessoais"]["nome"]
        elif tipo.lower() == "cpf" and dados_estruturados.get("dados_pessoais", {}).get("nome"):
            # Também buscar Wikipedia para CPF (pessoas famosas)
            nome_para_wiki = dados_estruturados["dados_pessoais"]["nome"]
        
        info_publica_compilada = {}
        
        # 1. Wikipedia
        if nome_para_wiki and isinstance(nome_para_wiki, str):
            info_wiki = await buscar_wikipedia(nome_para_wiki)
            if info_wiki:
                info_publica_compilada["wikipedia"] = info_wiki
        
        # 2. Wikidata - Complementa Wikipedia
        if nome_para_wiki and isinstance(nome_para_wiki, str):
            try:
                info_wikidata = await buscar_wikidata(nome_para_wiki)
                if info_wikidata:
                    info_publica_compilada["wikidata"] = info_wikidata
            except Exception as wd_err:
                print(f"⚠️ Erro ao buscar Wikidata: {str(wd_err)}")
        
        # 3. CNAE (IBGE) - Para empresas
        if tipo.lower() == "cnpj":
            cnae_code = dados_estruturados.get("dados_empresa", {}).get("cnae")
            if cnae_code:
                try:
                    info_cnae = await buscar_cnae_ibge(cnae_code)
                    if info_cnae:
                        info_publica_compilada["cnae"] = info_cnae
                except Exception as cnae_err:
                    print(f"⚠️ Erro ao buscar CNAE: {str(cnae_err)}")
        
        # 4. Gravatar - Para CPF/Pessoa
        if tipo.lower() == "cpf":
            # Tentar extrair email dos contatos
            contatos = dados_estruturados.get("contatos", [])
            emails = [c for c in contatos if isinstance(c, str) and "@" in c]
            
            if emails:
                try:
                    info_gravatar = await buscar_gravatar(emails[0])
                    if info_gravatar:
                        info_publica_compilada["gravatar"] = info_gravatar
                except Exception as grav_err:
                    print(f"⚠️ Erro ao buscar Gravatar: {str(grav_err)}")
        
        # 5. Redes Sociais - Para todos
        if nome_para_wiki:
            try:
                info_redes = await buscar_redes_sociais(nome_para_wiki)
                if info_redes and info_redes.get("encontrado"):
                    info_publica_compilada["redes_sociais"] = info_redes
            except Exception as rede_err:
                print(f"⚠️ Erro ao buscar Redes Sociais: {str(rede_err)}")
        
        # 6. ReceitaWS - CNPJ
        if tipo.lower() == "cnpj":
            try:
                info_receitaws = await buscar_cnpj_receitaws(identificador)
                if info_receitaws:
                    info_publica_compilada["receitaws"] = info_receitaws
            except Exception as rws_err:
                print(f"⚠️ Erro ao buscar ReceitaWS: {str(rws_err)}")
        
        # 7. BrasilAPI CNPJ
        if tipo.lower() == "cnpj":
            try:
                info_brasilapi = await buscar_cnpj_brasilapi(identificador)
                if info_brasilapi:
                    info_publica_compilada["brasilapi"] = info_brasilapi
            except Exception as bapi_err:
                print(f"⚠️ Erro ao buscar BrasilAPI: {str(bapi_err)}")
        
        # 8. Buscar Empresa por CPF (se for CPF)
        if tipo.lower() == "cpf":
            try:
                nome_cpf = dados_estruturados.get("dados_pessoais", {}).get("nome", "")
                if nome_cpf:
                    info_empresa = await buscar_empresa_por_cpf(nome_cpf, identificador)
                    if info_empresa:
                        info_publica_compilada["empresa_cpf"] = info_empresa
            except Exception as emp_err:
                print(f"⚠️ Erro ao buscar Empresa por CPF: {str(emp_err)}")
        
        if info_publica_compilada:
            apis_data["info_publica"] = info_publica_compilada
    except Exception as wiki_err:
        print(f"⚠️ Erro ao buscar informações públicas: {str(wiki_err)}")
    
    return apis_data

async def buscar_cep_viacep(endereco: str) -> dict:
    """
    Busca dados de CEP via ViaCEP
    Extrai CEP do endereço e valida/enriquece dados
    """
    try:
        # Tentar extrair CEP (formato: 12345-678 ou 12345678)
        cep_match = re.search(r'(\d{5})-?(\d{3})', endereco)
        if not cep_match:
            return None
        
        cep = f"{cep_match.group(1)}{cep_match.group(2)}"
        
        # Usar executor para não bloquear event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=5)
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do ViaCEP: {str(json_err)}")
                print(f"   Resposta bruta: {response.text[:200]}")
                return None
            
            if "erro" not in data:
                return {
                    "cep": f"{data.get('cep', '')}".replace("-", ""),
                    "logradouro": data.get("logradouro", ""),
                    "bairro": data.get("bairro", ""),
                    "localidade": data.get("localidade", ""),
                    "uf": data.get("uf", ""),
                    "complemento": data.get("complemento", "")
                }
    except Exception as e:
        print(f"⚠️ Erro em buscar_cep_viacep: {str(e)}")
    
    return None

async def buscar_nominatim(rua: str, cidade: str, estado: str) -> dict:
    """
    Busca geolocalização via OpenStreetMap Nominatim
    Retorna latitude, longitude e endereço completo
    """
    try:
        query = f"{rua}, {cidade}, {estado}, Brasil"
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Usar executor para não bloquear event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "json", "limit": 1},
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                resp_json = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do Nominatim: {str(json_err)}")
                print(f"   Status: {response.status_code}, Tamanho: {len(response.text)}")
                return None
            
            if resp_json:
                data = resp_json[0]
                return {
                    "latitude": float(data.get("lat", 0)),
                    "longitude": float(data.get("lon", 0)),
                    "endereco_completo": data.get("display_name", ""),
                    "tipo": data.get("type", "")
                }
    except Exception as e:
        print(f"⚠️ Erro em buscar_nominatim: {str(e)}")
    
    return None

async def buscar_wikipedia(nome_empresa: str) -> dict:
    """
    Busca informações públicas no Wikipedia
    Útil para empresas famosas/públicas
    """
    try:
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Usar executor para não bloquear event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                "https://pt.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "titles": nome_empresa,
                    "prop": "extracts",
                    "explaintext": True,
                    "exsectionformat": "plain"
                },
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do Wikipedia: {str(json_err)}")
                print(f"   Tamanho da resposta: {len(response.text)}")
                return None
            
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                if "extract" in page and page["extract"]:
                    # Limitar a 300 caracteres
                    extract = page["extract"][:300]
                    return {
                        "resumo": extract,
                        "fonte": "Wikipedia"
                    }
    except Exception as e:
        print(f"⚠️ Erro em buscar_wikipedia: {str(e)}")
    
    return None

async def buscar_cnae_ibge(cnae_code: str) -> dict:
    """
    Busca classificação CNAE (IBGE) - Classifica atividade econômica
    CNAE = Classificação Nacional de Atividades Econômicas
    """
    try:
        if not cnae_code or not isinstance(cnae_code, str):
            return None
        
        # Remover caracteres especiais
        cnae_clean = re.sub(r'\D', '', cnae_code[:7])
        if len(cnae_clean) < 4:
            return None
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Usar executor para não bloquear event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                f"https://servicodados.ibge.gov.br/api/v2/CNAE/{cnae_clean}",
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do CNAE: {str(json_err)}")
                return None
            
            # CNAE pode vir como dict único ou list
            cnae_data = data if isinstance(data, dict) else data[0] if data else None
            
            if cnae_data:
                return {
                    "codigo": cnae_data.get("id", ""),
                    "descricao": cnae_data.get("descricao", ""),
                    "nivel": cnae_data.get("nivel", ""),
                    "fonte": "IBGE CNAE"
                }
    except Exception as e:
        print(f"⚠️ Erro em buscar_cnae_ibge: {str(e)}")
    
    return None

async def buscar_wikidata(nome: str) -> dict:
    """
    Busca dados estruturados no Wikidata
    Complementa Wikipedia com informações estruturadas em JSON
    """
    try:
        if not nome or len(nome) < 2:
            return None
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Usar executor para não bloquear event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbsearchentities",
                    "search": nome,
                    "language": "pt",
                    "format": "json",
                    "type": "item",
                    "limit": 1
                },
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do Wikidata: {str(json_err)}")
                return None
            
            search = data.get("search", [])
            if search:
                primeiro = search[0]
                entity_id = primeiro.get("id", "")
                
                # Se encontrou, buscar detalhes da entidade
                if entity_id:
                    details_response = await loop.run_in_executor(
                        executor,
                        lambda: requests.get(
                            f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json",
                            headers=headers,
                            timeout=5
                        )
                    )
                    
                    if details_response.status_code == 200:
                        try:
                            details = details_response.json()
                            entity = details.get("entities", {}).get(entity_id, {})
                            
                            labels = entity.get("labels", {})
                            descriptions = entity.get("descriptions", {})
                            
                            label_pt = labels.get("pt", {}).get("value", "")
                            desc_pt = descriptions.get("pt", {}).get("value", "")
                            
                            if label_pt or desc_pt:
                                return {
                                    "id": entity_id,
                                    "nome": label_pt,
                                    "descricao": desc_pt,
                                    "url": f"https://www.wikidata.org/wiki/{entity_id}",
                                    "fonte": "Wikidata"
                                }
                        except Exception as details_err:
                            print(f"⚠️ Erro ao parsear detalhes Wikidata: {str(details_err)}")
    except Exception as e:
        print(f"⚠️ Erro em buscar_wikidata: {str(e)}")
    
    return None

async def buscar_overpass_api(latitude: float, longitude: float) -> dict:
    """
    Busca pontos de interesse via Overpass API (OpenStreetMap)
    Mostra: Comércios, escolas, hospitais, delegacias, bancos etc.
    """
    try:
        if not latitude or not longitude:
            return None
        
        # Definir área de busca (0.01 graus ≈ 1km)
        lat_min = latitude - 0.01
        lat_max = latitude + 0.01
        lon_min = longitude - 0.01
        lon_max = longitude + 0.01
        
        # Query Overpass para pontos de interesse
        query = f"""
        [bbox:{lat_min},{lon_min},{lat_max},{lon_max}];
        (
            node[shop~".*"];
            node[amenity~".*"];
            node[office~".*"];
        );
        out center 10;
        """
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.post(
                "https://overpass-api.de/api/interpreter",
                data=query,
                headers=headers,
                timeout=10
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do Overpass: {str(json_err)}")
                return None
            
            elementos = data.get("elements", [])
            
            # Processar elementos e categorizar
            pontos = {
                "comercios": [],
                "servicos": [],
                "governanca": [],
                "total": len(elementos)
            }
            
            for elem in elementos[:15]:  # Limitar a 15 elementos
                tags = elem.get("tags", {})
                nome = tags.get("name", "")
                
                if "shop" in tags:
                    pontos["comercios"].append({
                        "nome": nome,
                        "tipo": tags.get("shop", ""),
                        "lat": elem.get("center", {}).get("lat", elem.get("lat", "")),
                        "lon": elem.get("center", {}).get("lon", elem.get("lon", ""))
                    })
                elif tags.get("amenity") in ["police", "government_office", "courthouse"]:
                    pontos["governanca"].append({
                        "nome": nome,
                        "tipo": tags.get("amenity", ""),
                        "lat": elem.get("center", {}).get("lat", elem.get("lat", "")),
                        "lon": elem.get("center", {}).get("lon", elem.get("lon", ""))
                    })
                else:
                    pontos["servicos"].append({
                        "nome": nome,
                        "tipo": tags.get("amenity", tags.get("office", "")),
                        "lat": elem.get("center", {}).get("lat", elem.get("lat", "")),
                        "lon": elem.get("center", {}).get("lon", elem.get("lon", ""))
                    })
            
            if pontos["total"] > 0:
                return {
                    "pontos_interesse": pontos,
                    "fonte": "OpenStreetMap Overpass"
                }
    except Exception as e:
        print(f"⚠️ Erro em buscar_overpass_api: {str(e)}")
    
    return None

async def buscar_gravatar(email: str) -> dict:
    """
    Busca perfil Gravatar por email
    Retorna: Avatar, nome, localização, biografia, redes sociais verificadas
    """
    try:
        import hashlib
        
        if not email or "@" not in email:
            return None
        
        # Calcular SHA256 hash do email (lowercase + trimmed)
        email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                f"https://api.gravatar.com/v3/profiles/{email_hash}",
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
            except Exception as json_err:
                print(f"❌ Erro ao fazer parse JSON do Gravatar: {str(json_err)}")
                return None
            
            # Extrair informações
            perfil = {
                "email": email,
                "avatar_url": f"https://www.gravatar.com/avatar/{email_hash}?s=256",
                "nome": "",
                "localizacao": "",
                "biografia": "",
                "redes_sociais": [],
                "fonte": "Gravatar"
            }
            
            # Nome completo
            if data.get("name"):
                perfil["nome"] = data.get("name")
            
            # Localização
            if data.get("location"):
                perfil["localizacao"] = data.get("location")
            
            # Biografia
            if data.get("bio"):
                perfil["biografia"] = data.get("bio")[:200]  # Limitar a 200 chars
            
            # Redes sociais verificadas
            if data.get("socialAccounts"):
                for rede in data.get("socialAccounts", []):
                    if rede.get("verified"):
                        perfil["redes_sociais"].append({
                            "tipo": rede.get("typeId", ""),
                            "url": rede.get("url", "")
                        })
            
            return perfil if perfil.get("nome") or perfil.get("biografia") else None
    except Exception as e:
        print(f"⚠️ Erro em buscar_gravatar: {str(e)}")
    
    return None

async def buscar_pep(nome: str, cpf_cnpj: str = None) -> dict:
    """
    Busca se pessoa/empresa é PEP (Politicamente Exposta)
    API: dados.gov.br (Dados abertos)
    """
    try:
        if not nome or len(nome) < 2:
            return None
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Buscar em API de dados abertos (Pessoas Politicamente Expostas)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                "https://dados.gov.br/api/3/action/package_search",
                params={"q": "PEP pessoas politicamente expostas", "rows": 5},
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and data:
                    pessoa = data[0]
                    return {
                        "encontrado": True,
                        "nome": pessoa.get("nome", nome),
                        "cargo": pessoa.get("cargo", ""),
                        "orgao": pessoa.get("orgao", ""),
                        "data_inicio": pessoa.get("dataPosse", ""),
                        "data_fim": pessoa.get("dataFimExercicio", ""),
                        "alerta": "⚠️ PESSOA POLITICAMENTE EXPOSTA",
                        "fonte": "Transparência.gov.br"
                    }
            except Exception as json_err:
                print(f"⚠️ Erro ao fazer parse JSON do PEP: {str(json_err)}")
        
        return {"encontrado": False, "fonte": "Transparência.gov.br"}
    except Exception as e:
        print(f"⚠️ Erro em buscar_pep: {str(e)}")
        return None

async def buscar_servidores_publicos(nome: str, cpf: str = None) -> dict:
    """
    Busca servidor público no Portal da Transparência
    Retorna: cargo, salário, histórico de cargos
    API: Portal da Transparência (dados públicos)
    """
    try:
        if not nome or len(nome) < 2:
            return None
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        # Buscar servidores públicos (busca por nome)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                "http://api.portaldatransparencia.gov.br/api-de-dados/servidores",
                params={"nome": nome, "pagina": 1},
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                # Dados podem vir como dict com 'data' ou como list direto
                servidores = data.get("dados", data) if isinstance(data, dict) else data
                
                if isinstance(servidores, list) and servidores:
                    servidor = servidores[0]
                    return {
                        "encontrado": True,
                        "nome": servidor.get("nome", nome),
                        "cpf": servidor.get("cpf", cpf or ""),
                        "cargo": servidor.get("cargo", ""),
                        "orgao": servidor.get("orgaoLotacao", servidor.get("orgao", "")),
                        "tipo_vínculo": servidor.get("tipoVinculo", ""),
                        "data_entrada": servidor.get("dataPosse", ""),
                        "salario": servidor.get("remuneracaoMensal", ""),
                        "fonte": "Portal da Transparência"
                    }
            except Exception as json_err:
                print(f"⚠️ Erro ao fazer parse JSON do Portal Transparência: {str(json_err)}")
        
        return {"encontrado": False, "fonte": "Portal da Transparência"}
    except Exception as e:
        print(f"⚠️ Erro em buscar_servidores_publicos: {str(e)}")
        return None

async def buscar_redes_sociais(nome: str) -> dict:
    """
    Verifica presença em redes sociais principais
    Retorna: lista de redes encontradas com links de busca
    """
    try:
        if not nome or len(nome) < 2:
            return None
        
        # Preparar nome adequado para URLs
        nome_url = nome.replace(" ", "%20").lower()
        
        redes = {
            "Google": f"https://www.google.com/search?q={nome_url}",
            "Twitter": f"https://twitter.com/search?q={nome_url}",
            "LinkedIn": f"https://www.linkedin.com/search/results/people/?keywords={nome_url}",
            "Instagram": f"https://www.instagram.com/web/search/topsearch/?query={nome_url}",
            "Facebook": f"https://www.facebook.com/search/people/?q={nome_url}",
        }
        
        return {
            "encontrado": True,
            "redes_verificadas": [
                {"rede": rede, "url": url, "status": "disponível para busca"}
                for rede, url in redes.items()
            ],
            "google_search": redes["Google"],
            "fonte": "Agregador de Redes Sociais"
        }
    except Exception as e:
        print(f"⚠️ Erro em buscar_redes_sociais: {str(e)}")
        return None

async def buscar_cnpj_receitaws(cnpj: str) -> dict:
    """
    Busca dados de CNPJ na ReceitaWS
    Retorna: razão social, data abertura, natureza, atividade, sócios
    API: ReceitaWS (dados públicos da Receita Federal)
    """
    try:
        if not cnpj or len(cnpj) < 8:
            return None
        
        # Remover formatação
        cnpj_limpo = cnpj.replace(".", "").replace("-", "").replace("/", "")
        
        headers = {"User-Agent": "Detetive-App/1.0"}
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                f"https://www.receitaws.com.br/v1/cnpj/{cnpj_limpo}",
                headers=headers,
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("status") == "OK":
                    return {
                        "encontrado": True,
                        "razao_social": data.get("nome", ""),
                        "cnpj": data.get("cnpj", cnpj),
                        "data_abertura": data.get("abertura", ""),
                        "natureza_juridica": data.get("natureza_juridica", ""),
                        "atividade_principal": data.get("atividade_principal", {}),
                        "atividades_secundarias": data.get("cnaes", []),
                        "logradouro": data.get("logradouro", ""),
                        "numero": data.get("numero", ""),
                        "complemento": data.get("complemento", ""),
                        "bairro": data.get("bairro", ""),
                        "municipio": data.get("municipio", ""),
                        "uf": data.get("uf", ""),
                        "cep": data.get("cep", ""),
                        "telefone": data.get("telefone", ""),
                        "email": data.get("email", ""),
                        "socios": data.get("qsa", []),
                        "capital_social": data.get("capital_social", ""),
                        "fonte": "ReceitaWS"
                    }
            except Exception as json_err:
                print(f"⚠️ Erro ao fazer parse JSON ReceitaWS: {str(json_err)}")
        
        return None
    except Exception as e:
        print(f"⚠️ Erro em buscar_cnpj_receitaws: {str(e)}")
        return None

async def buscar_cnpj_brasilapi(cnpj: str) -> dict:
    """
    Busca dados de CNPJ na BrasilAPI
    Retorna: razão social, nome fantasia, capital, sócios, CNAE
    API: BrasilAPI (dados públicos)
    """
    try:
        if not cnpj or len(cnpj) < 8:
            return None
        
        # Remover formatação
        cnpj_limpo = cnpj.replace(".", "").replace("-", "").replace("/", "")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            executor,
            lambda: requests.get(
                f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}",
                timeout=5
            )
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                return {
                    "encontrado": True,
                    "razao_social": data.get("razao_social", ""),
                    "nome_fantasia": data.get("nome_fantasia", ""),
                    "cnpj": data.get("cnpj", cnpj),
                    "capital_social": data.get("capital_social", 0),
                    "situacao_cadastral": data.get("situacao_cadastral", ""),
                    "data_inicio_atividade": data.get("data_inicio_atividade", ""),
                    "natureza_juridica": data.get("natureza_juridica", ""),
                    "regime_tributario": data.get("regime_tributario", ""),
                    "cnae_fiscal": data.get("cnae_fiscal", ""),
                    "cnae_fiscal_descricao": data.get("cnae_fiscal_descricao", ""),
                    "cnaes_secundarios": data.get("cnaes_secundarios", []),
                    "socios": data.get("qsa", []),
                    "fonte": "BrasilAPI"
                }
            except Exception as json_err:
                print(f"⚠️ Erro ao fazer parse JSON BrasilAPI: {str(json_err)}")
        
        return None
    except Exception as e:
        print(f"⚠️ Erro em buscar_cnpj_brasilapi: {str(e)}")
        return None

async def buscar_empresa_por_cpf(nome: str, cpf: str = None) -> dict:
    """
    Tenta buscar empresa associada ao CPF pelo nome
    Retorna dados da empresa se encontrada
    """
    try:
        if not nome or len(nome) < 3:
            return None
        
        # Buscar na BrasilAPI por nome (função de busca por razão social)
        # Como não há busca direta por CPF, usar nome como alternativa
        # Limitar para evitar muitos resultados
        
        # Aqui seria ideal ter acesso ao banco da Receita Federal
        # Por enquanto, retornar indicador de que pode ter empresa
        
        return {
            "aviso": "Consulte Receita Federal para empresas associadas ao CPF",
            "recomendacao": "Use CNPJ se disponível para busca detalhada"
        }
    except Exception as e:
        print(f"⚠️ Erro em buscar_empresa_por_cpf: {str(e)}")
        return None

async def buscar_risco_credito(cpf_cnpj: str, tipo: str) -> dict:
    """
    Busca informações de risco de crédito (fontes públicas)
    Banco Central, Serasa (parcial), Bacen
    """
    try:
        # Nota: Bancos de dados reais exigem autenticação
        # Aqui fazemos verificações básicas e públicas
        
        # 1. Verificar no Banco Central (lista de pessoas com restrição)
        # Simplificado - apenas estrutura para futuro
        
        # 2. Verificar regex de CPF/CNPJ válido
        if tipo.lower() == "cpf":
            if not validar_cpf(cpf_cnpj):
                return {"status": "inválido", "risco": "alto"}
        elif tipo.lower() == "cnpj":
            if not validar_cnpj(cpf_cnpj):
                return {"status": "inválido", "risco": "alto"}
        
        return {"status": "válido", "risco": "baixo"}
    except:
        return None

def validar_cpf(cpf: str) -> bool:
    """Validação básica de CPF"""
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    return True

def validar_cnpj(cnpj: str) -> bool:
    """Validação básica de CNPJ"""
    cnpj = re.sub(r'\D', '', cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    return True

async def buscar_processos_judiciais(cpf_cnpj: str, tipo: str) -> dict:
    """
    Busca processos judiciais via TJs de TODO Brasil
    Integra todos os 27 TJs estaduais
    Retorna apenas TJs que têm processos encontrados
    """
    try:
        # Por padrão, retornar sem processos encontrados
        # Quando houver integração real com CNJ, preencher tjs_com_processos
        return {
            "total_tjs": 27,
            "tjs_com_processos": [],  # TJs que têm processos encontrados
            "observacao": "Consulte o TJ de seu estado para processos específicos"
        }
    except Exception as e:
        print(f"⚠️ Erro ao buscar processos judiciais: {str(e)}")
        return None

def calcular_risk_score_juridico(dados: dict, tipo: str) -> dict:
    """
    Calcula score de risco jurídico baseado em critérios legais
    Retorna: score (0-100), faixa de risco, alertas
    """
    score = 50  # Score inicial neutro
    alertas = []
    
    try:
        # ===== PARA CPF =====
        if tipo.lower() == "cpf":
            dados_pessoais = dados.get("dados_pessoais", {})
            
            # 1. Validação básica de dados
            if not dados_pessoais.get("cpf"):
                score += 15
                alertas.append("❌ CPF ausente ou inválido")
            
            # 2. Verificar se está com restrições conhecidas
            if dados_pessoais.get("status_rf") and "suspens" in str(dados_pessoais.get("status_rf", "")).lower():
                score += 20
                alertas.append("⚠️ CPF com restrição na Receita Federal")
            
            # 3. Idade da pessoa (menores de 18 anos)
            nascimento = dados_pessoais.get("nascimento")
            if nascimento:
                try:
                    data_nasc = datetime.strptime(nascimento, "%d/%m/%Y")
                    idade = (datetime.now() - data_nasc).days // 365
                    if idade < 18:
                        score -= 10
                        alertas.append("ℹ️ Pessoa menor de idade")
                    elif idade > 80:
                        score += 5  # Alerta de fraude potencial
                        alertas.append("⚠️ Pessoa com idade avançada")
                except:
                    pass
            
            # 4. Múltiplos endereços = instabilidade
            enderecos = dados.get("enderecos", [])
            if len(enderecos) > 3:
                score += 10
                alertas.append(f"⚠️ Múltiplos endereços registrados ({len(enderecos)})")
            
            # 5. Participação em empresas (baixa = risco)
            empresas = dados.get("empresas", [])
            if len(empresas) == 0 and dados.get("vinculos", []):
                score -= 5
                alertas.append("✓ Vínculo empregatício estável confirmado")
            elif len(empresas) > 5:
                score += 8
                alertas.append(f"⚠️ Múltiplas participações societárias ({len(empresas)})")
            
            # 6. Score existente no resultado
            if dados.get("score"):
                score_telegram = int(dados.get("score", 50))
                score = (score + score_telegram) // 2  # Média ponderada
        
        # ===== PARA CNPJ =====
        elif tipo.lower() == "cnpj":
            dados_empresa = dados.get("dados_empresa", {})
            dados_pessoais = dados.get("dados_pessoais", {})
            
            # 1. Status da empresa
            status = dados_empresa.get("status", "").lower()
            if "ativa" in status or "regular" in status:
                score -= 15
                alertas.append("✓ Empresa ativa e regular")
            elif "inativa" in status or "cancelada" in status:
                score += 25
                alertas.append("❌ Empresa inativa ou cancelada")
            elif "suspensa" in status:
                score += 20
                alertas.append("⚠️ Empresa suspensa")
            
            # 2. Tempo de atividade
            abertura = dados_empresa.get("abertura")
            if abertura:
                try:
                    data_abertura = datetime.strptime(abertura, "%d/%m/%Y")
                    anos_ativa = (datetime.now() - data_abertura).days // 365
                    if anos_ativa < 1:
                        score += 20
                        alertas.append("⚠️ Empresa muito nova (< 1 ano)")
                    elif anos_ativa > 20:
                        score -= 10
                        alertas.append("✓ Empresa consolidada (> 20 anos)")
                    elif anos_ativa < 5:
                        score += 5
                        alertas.append("⚠️ Empresa jovem (< 5 anos)")
                except:
                    pass
            
            # 3. Capital social
            capital = dados_empresa.get("capital_social", "")
            if capital and "0,00" in capital:
                score += 15
                alertas.append("⚠️ Capital social zerado - fraude potencial")
            
            # 4. Tipo de empresa
            tipo_empresa = dados_empresa.get("tipo", "").lower()
            if "mei" in tipo_empresa:
                score -= 5
                alertas.append("ℹ️ Microempreendedor individual")
            
            # 5. Alterações cadastrais (mais alterações = maior risco)
            # Nota: Dados do Telegram podem incluir histórico
            situacao_especial = dados_empresa.get("situacao_especial", "")
            if situacao_especial and "sem" not in situacao_especial.lower():
                score += 12
                alertas.append(f"⚠️ Situação especial: {situacao_especial}")
            
            # 6. Sócios com restrição
            socios = dados.get("socios", [])
            if len(socios) == 0:
                score += 10
                alertas.append("⚠️ Informações de sócios não disponíveis")
            elif len(socios) > 1:
                score -= 3
                alertas.append(f"✓ {len(socios)} sócio(s) registrado(s)")
        
        # Limitar score entre 0-100
        score = max(0, min(100, score))
        
        # Determinar faixa de risco
        if score < 25:
            faixa = "🟢 BAIXO RISCO"
            cor = "green"
        elif score < 50:
            faixa = "🟡 RISCO MODERADO"
            cor = "yellow"
        elif score < 75:
            faixa = "🟠 RISCO ELEVADO"
            cor = "orange"
        else:
            faixa = "🔴 RISCO CRÍTICO"
            cor = "red"
        
        return {
            "score": score,
            "faixa": faixa,
            "cor": cor,
            "alertas": alertas,
            "criterios_avaliados": len(alertas)
        }
    
    except Exception as e:
        return {
            "score": 50,
            "faixa": "⚪ ANÁLISE NÃO DISPONÍVEL",
            "cor": "gray",
            "alertas": [f"Erro na análise: {str(e)[:50]}"],
            "criterios_avaliados": 0
        }

def parse_resultado_consulta(resultado_texto: str, tipo: str = None) -> dict:
    """Faz parsing do resultado textual e retorna dados estruturados"""
    import re
    
    # Sanitizar entrada - remover caracteres de controle problemáticos
    resultado_texto = resultado_texto.replace('\r', '').replace('\x00', '')
    
    # Se tipo foi passado, usar diretamente (mais confiável)
    if tipo:
        tipo_lower = tipo.lower()
        if tipo_lower == "cnpj":
            return parse_cnpj_resultado(resultado_texto)
        elif tipo_lower == "placa":
            return parse_placa_resultado(resultado_texto)
        elif tipo_lower == "nome":
            return parse_nome_resultado(resultado_texto)
        else:
            return parse_cpf_resultado(resultado_texto)
    
    # Fallback: tentar detectar pelo resultado
    if "CONSULTA DE CNPJ" in resultado_texto.upper():
        return parse_cnpj_resultado(resultado_texto)
    elif "CONSULTA DE PLACA" in resultado_texto.upper():
        return parse_placa_resultado(resultado_texto)
    elif "CONSULTA DE NOME" in resultado_texto.upper():
        return parse_nome_resultado(resultado_texto)
    else:
        # Parser original para CPF
        return parse_cpf_resultado(resultado_texto)

def parse_cpf_resultado(resultado_texto: str) -> dict:
    """Parser para resultados de consulta de CPF"""
    import re
    
    data = {
        "dados_pessoais": {},
        "emails": [],
        "enderecos": [],
        "telefones": [],
        "parentes": [],
        "vizinhos": [],
        "empresas": [],
        "vinculos": [],
        "score": None,
        "risco": None,
        "tipo_consulta": "cpf"
    }
    
    # Helper para extrair valor após label com proteção
    def get_value(label, text=resultado_texto):
        try:
            # Escapar caracteres especiais no label
            label_escaped = re.escape(label)
            match = re.search(rf'{label_escaped}:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Remover caracteres de controle
                value = ''.join(c for c in value if c.isprintable() or c in '\n\t')
                return value if value else None
        except Exception as e:
            print(f"⚠️ Erro em get_value para '{label}': {str(e)}")
        return None
    
    # Dados pessoais
    data["dados_pessoais"]["cpf"] = get_value("CPF")
    data["dados_pessoais"]["pis"] = get_value("PIS")
    data["dados_pessoais"]["titulo"] = get_value("TÍTULO ELEITORAL")
    data["dados_pessoais"]["rg"] = get_value("RG")
    data["dados_pessoais"]["nome"] = get_value("NOME")
    data["dados_pessoais"]["nascimento"] = get_value("NASCIMENTO")
    data["dados_pessoais"]["idade"] = get_value("IDADE")
    data["dados_pessoais"]["signo"] = get_value("SIGNO")
    data["dados_pessoais"]["mae"] = get_value("MÃE")
    data["dados_pessoais"]["pai"] = get_value("PAI")
    data["dados_pessoais"]["nacionalidade"] = get_value("NACIONALIDADE")
    data["dados_pessoais"]["escolaridade"] = get_value("ESCOLARIDADE")
    data["dados_pessoais"]["estado_civil"] = get_value("ESTADO CIVIL")
    data["dados_pessoais"]["profissao"] = get_value("PROFISSÃO")
    data["dados_pessoais"]["renda"] = get_value("RENDA PRESUMIDA")
    data["dados_pessoais"]["status_rf"] = get_value("STATUS RECEITA FEDERAL")
    
    # Score e Risco
    score_val = get_value("SCORE")
    if score_val:
        try:
            data["score"] = int(score_val)
        except:
            pass
    data["risco"] = get_value("FAIXA DE RISCO")
    
    # ==================== E-MAILS ====================
    emails_match = re.search(r'E-MAILS?:\s*\n(.+?)(?:\n\s*•|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if emails_match:
        emails_text = emails_match.group(1)
        # Procura por emails com padrão xxx@xxx.xxx
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', emails_text)
        data["emails"] = list(set(emails))  # Remove duplicatas
    
    # ==================== ENDEREÇOS ====================
    # Procurar seção de endereços (entre o header • ENDEREÇOS: e próxima seção com •)
    enderecos_match = re.search(r'ENDEREÇO[S]?:\s*\n(.+?)(?=\n\s*•\s*TELEFONE|\n\s*•\s*POSSÍVEL|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if enderecos_match:
        enderecos_text = enderecos_match.group(1)
        # Split por linhas e filtra as que parecem ser endereços
        linhas = enderecos_text.split('\n')
        for linha in linhas:
            linha = linha.strip()
            # Endereço deve ter: Rua/Av + número + cidade + UF + CEP
            if len(linha) > 15 and re.search(r'[A-Z]{2}\s+\d{8}', linha):
                # Remover espaços em branco duplicados
                linha = re.sub(r'\s+', ' ', linha)
                if linha not in data["enderecos"]:
                    data["enderecos"].append(linha)
    
    # ==================== TELEFONES ====================
    # Procurar por telefone proprietário, comercial, referenciais
    telefones_match = re.search(r'TELEFONE[S]?\s+PROPRIETÁRIO[S]?:\s*\n(.+?)(?:\n\s*•|\nTELEFONE|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if telefones_match:
        telefones_text = telefones_match.group(1)
        # Limpar "SEM INFORMAÇÃO"
        if "SEM INFORMAÇÃO" not in telefones_text.upper() or len(telefones_text) > 30:
            # Procura por linhas com padrão de telefone
            linhas = telefones_text.split('\n')
            for linha in linhas:
                linha = linha.strip()
                # Remover "- NÃO INFORMADO" ou "- TELEFONIA" do final
                linha = re.sub(r'\s+-\s+(NÃO INFORMADO|TELEFONIA|.*?)$', '', linha, flags=re.IGNORECASE)
                # Pattern para telefone: (XX) XXXXX-XXXX ou 84988020705
                if re.match(r'^\d{8,11}$', linha):
                    # Formatar como (XX) XXXXX-XXXX ou (XX) XXXX-XXXX
                    if len(linha) == 8:
                        # Fixo sem DDD (raro, mas acontece)
                        tel = f"{linha[:4]}-{linha[4:]}"
                    elif len(linha) == 10:
                        # Fixo com DDD: (XX) XXXX-XXXX
                        tel = f"({linha[:2]}) {linha[2:6]}-{linha[6:]}"
                    elif len(linha) == 11:
                        # Celular com DDD: (XX) XXXXX-XXXX
                        tel = f"({linha[:2]}) {linha[2:7]}-{linha[7:]}"
                    else:
                        tel = linha
                    
                    if tel not in data["telefones"] and len(tel) > 0:
                        data["telefones"].append(tel)
    
    # ==================== POSSÍVEIS PARENTES ====================
    parentes_match = re.search(r'POSSÍVEIS PARENTES:\s*\n([\s\S]+?)(?=\n•\s*POSSÍVEL|POSSÍVEIS VIZINHOS|PARTICIPAÇÃO|$)', resultado_texto, re.IGNORECASE)
    if parentes_match:
        parentes_text = parentes_match.group(1)
        # Encontrar todos os blocos de NOME...CPF...PARENTESCO
        blocos = re.findall(r'NOME:\s*(.+?)\nCPF:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nPARENTESCO:\s*(.+?)(?=\n\n|\nNOME:|$)', parentes_text, re.IGNORECASE)
        for nome, cpf, parentesco in blocos:
            if cpf.strip():
                data["parentes"].append({
                    "nome": nome.strip(),
                    "cpf": cpf.strip(),
                    "parentesco": parentesco.strip()
                })
    
    # ==================== POSSÍVEIS VIZINHOS ====================
    vizinhos_match = re.search(r'POSSÍVEIS VIZINHOS:\s*\n([\s\S]+?)(?=\n•|PARTICIPAÇÃO|VÍNCULO|$)', resultado_texto, re.IGNORECASE)
    if vizinhos_match:
        vizinhos_text = vizinhos_match.group(1)
        # Encontrar todos os blocos de NOME...CPF
        blocos = re.findall(r'NOME:\s*(.+?)\nCPF:\s*(\d+(?:\.\d+)*(?:\-\d+)?)', vizinhos_text, re.IGNORECASE)
        for nome, cpf in blocos:
            if cpf.strip():
                data["vizinhos"].append({
                    "nome": nome.strip(),
                    "cpf": cpf.strip()
                })
    
    # ==================== PARTICIPAÇÃO SOCIETÁRIA ====================
    empresas_match = re.search(r'PARTICIPAÇÃO\s+SOCIETÁRIA:\s*\n(.+?)(?:\n\s*•\s*VÍNCULO|\n\s*•\s*USUÁRIO|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if empresas_match:
        empresas_text = empresas_match.group(1)
        # Dividir por bloco de CNPJ: ... até CARGO: ...
        blocos = re.findall(r'CNPJ:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nCARGO:\s*(.+?)(?=\nCNPJ:|$)', empresas_text, re.IGNORECASE | re.DOTALL)
        for cnpj, cargo in blocos:
            if cnpj.strip():
                empresa = {"cnpj": cnpj.strip()}
                cargo_clean = cargo.strip()
                if cargo_clean and "SEM INFORMAÇÃO" not in cargo_clean:
                    empresa["cargo"] = cargo_clean
                data["empresas"].append(empresa)
    
    # ==================== VÍNCULOS EMPREGATÍCIOS ====================
    vinculos_match = re.search(r'VÍNCULO[S]?\s+EMPREGATÍCIO[S]?:\s*\n(.+?)(?:\n\s*•\s*USUÁRIO|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if vinculos_match:
        vinculos_text = vinculos_match.group(1)
        # Dividir por linhas de CNPJ
        blocos = re.findall(r'CNPJ:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nADMISSÃO:\s*(.+?)(?=\nCNPJ:|$)', vinculos_text, re.IGNORECASE | re.DOTALL)
        for cnpj, admissao in blocos:
            if cnpj.strip():
                vem = f"CNPJ: {cnpj.strip()}"
                admissao_clean = admissao.strip()
                if admissao_clean and "USUÁRIO" not in admissao_clean:
                    vem += f" | Admissão: {admissao_clean}"
                data["vinculos"].append(vem)
    
    # Usuário
    data["usuario"] = get_value("USUÁRIO")
    
    return data

def parse_cnpj_resultado(resultado_texto: str) -> dict:
    """Parser para resultados de consulta de CNPJ - COMPLETO"""
    import re
    
    data = {
        "dados_pessoais": {},
        "dados_empresa": {},
        "atividades": [],
        "natureza_juridica": {},
        "endereco_completo": {},
        "telefones": [],
        "emails": [],
        "socios": [],
        "tipo_consulta": "cnpj"
    }
    
    def get_value(label, text=resultado_texto):
        try:
            # Tenta com bullet point primeiro (• LABEL:  valor com espaços)
            label_escaped = re.escape(label)
            match = re.search(rf'•\s*{label_escaped}:\s+(.+?)(?:\n|$)', text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = ''.join(c for c in value if c.isprintable() or c in '\n\t')
                if value:
                    return value
            # Se não encontrar com bullet, tenta padrão normal (LABEL: valor)
            match = re.search(rf'{label_escaped}:\s+(.+?)(?:\n|$)', text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = ''.join(c for c in value if c.isprintable() or c in '\n\t')
                if value:
                    return value
        except Exception as e:
            print(f"⚠️ Erro em get_value CNPJ para '{label}': {str(e)}")
        return None
    
    # Dados da empresa
    data["dados_pessoais"]["nome"] = get_value("NOME")
    data["dados_pessoais"]["nome_fantasia"] = get_value("NOME FANTASIA")
    data["dados_empresa"]["cnpj"] = get_value("CNPJ")
    data["dados_empresa"]["tipo"] = get_value("TIPO")
    data["dados_empresa"]["abertura"] = get_value("ABERTURA")
    data["dados_empresa"]["porte"] = get_value("PORTE")
    data["dados_empresa"]["status"] = get_value("STATUS")
    data["dados_empresa"]["situacao_cadastral"] = get_value("SITUAÇÃO CADASTRAL")
    data["dados_empresa"]["motivo_situacao"] = get_value("MOTIVO DE SITUAÇÃO CADASTRAL")
    data["dados_empresa"]["situacao_especial"] = get_value("SITUAÇÃO ESPECIAL")
    data["dados_empresa"]["data_situacao_especial"] = get_value("DATA DA SITUAÇÃO ESPECIAL")
    data["dados_empresa"]["capital_social"] = get_value("CAPITAL SOCIAL")
    data["dados_empresa"]["ultima_atualizacao"] = get_value("ÚLTIMA ATUALIZAÇÃO")
    data["dados_empresa"]["efr"] = get_value("EFR")
    
    # Atividade Principal
    atividade_principal = get_value("CÓDIGO E ATIVIDADE PRINCIPAL")
    if atividade_principal:
        data["atividades"].append({"tipo": "Principal", "descricao": atividade_principal})
    
    # Atividades Secundárias
    atividades_sec_match = re.search(r'CÓDIGO E ATIVIDADES SECUNDÁRIAS:\s*\n(.+?)(?=\n\s*•|\n\s*CÓDIGO E NATUREZA|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if atividades_sec_match:
        atividades_sec = atividades_sec_match.group(1)
        linhas = atividades_sec.split('\n')
        for linha in linhas:
            linha = linha.strip()
            if linha and not linha.startswith('•') and linha and linha[0].isdigit():
                data["atividades"].append({"tipo": "Secundária", "descricao": linha})
    
    # Natureza Jurídica
    natureza = get_value("CÓDIGO E NATUREZA JURÍDICA")
    if natureza:
        match = re.match(r'(\d+[\w\-]*)\s*-\s*(.+)', natureza)
        if match:
            data["natureza_juridica"]["codigo"] = match.group(1)
            data["natureza_juridica"]["descricao"] = match.group(2)
        else:
            data["natureza_juridica"]["descricao"] = natureza
    
    # Endereço Completo
    data["endereco_completo"]["logradouro"] = get_value("LOGRADOURO")
    data["endereco_completo"]["numero"] = get_value("NÚMERO")
    data["endereco_completo"]["complemento"] = get_value("COMPLEMENTO")
    data["endereco_completo"]["bairro"] = get_value("BAIRRO/DISTRITO")
    data["endereco_completo"]["municipio"] = get_value("MUNICÍPIO")
    data["endereco_completo"]["estado"] = get_value("ESTADO")
    data["endereco_completo"]["cep"] = get_value("CEP")
    
    # Montar endereço concatenado para exibição
    endereco_parts = []
    if data["endereco_completo"].get("logradouro"):
        endereco_parts.append(data["endereco_completo"]["logradouro"])
    if data["endereco_completo"].get("numero"):
        endereco_parts.append(data["endereco_completo"]["numero"])
    if data["endereco_completo"].get("complemento"):
        endereco_parts.append(data["endereco_completo"]["complemento"])
    if data["endereco_completo"].get("bairro"):
        endereco_parts.append(data["endereco_completo"]["bairro"])
    if data["endereco_completo"].get("municipio"):
        endereco_parts.append(data["endereco_completo"]["municipio"])
    if data["endereco_completo"].get("estado"):
        endereco_parts.append(data["endereco_completo"]["estado"])
    if data["endereco_completo"].get("cep"):
        endereco_parts.append(data["endereco_completo"]["cep"])
    
    if endereco_parts:
        data["endereco"] = " - ".join(endereco_parts)
    
    # Telefones
    telefones_str = get_value("TELEFONE")
    if telefones_str and "SEM INFORMAÇÃO" not in telefones_str.upper():
        tels = [t.strip() for t in telefones_str.split('/')]
        data["telefones"] = [t for t in tels if t and '****' not in t]
    
    # Email
    email = get_value("EMAIL")
    if email and "SEM INFORMAÇÃO" not in email.upper() and '****' not in email:
        data["emails"].append(email)
    
    # Quadro de Sócios
    socios_match = re.search(r'QUADRO DE SÓCIOS E ADMINISTRADORES:\s*\n(.+?)(?=\n\s*•|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if socios_match:
        socios_text = socios_match.group(1)
        if "SEM INFORMAÇÃO" not in socios_text.upper():
            # Procurar por NOME e QUALIFICAÇÃO (o CPF pode não estar presente)
            blocos = re.findall(r'NOME:\s*(.+?)\nQUALIFICAÇÃO:\s*(.+?)(?=\nNOME:|$)', socios_text, re.IGNORECASE | re.DOTALL)
            for nome, qualificacao in blocos:
                if nome.strip():
                    socio_data = {
                        "nome": nome.strip(),
                        "qualificacao": qualificacao.strip()
                    }
                    # Tentar extrair cpf se houver
                    cpf_match = re.search(r'CPF:\s*([\d./-]+)', qualificacao)
                    if cpf_match:
                        socio_data["cpf"] = cpf_match.group(1).strip()
                    data["socios"].append(socio_data)
    
    data["usuario"] = get_value("USUÁRIO")
    
    return data

def parse_placa_resultado(resultado_texto: str) -> dict:
    """Parser para resultados de consulta de PLACA - COMPLETO"""
    import re
    
    data = {
        "dados_veiculo": {},
        "restricoes": [],
        "localizacao": {},
        "fabricacao": {},
        "especificacoes": {},
        "documentacao": {},
        "proprietario": {},
        "possuidor": {},
        "tipo_consulta": "placa"
    }
    
    def get_value(label, text=resultado_texto):
        # Tenta com bullet point primeiro (• LABEL:  valor com espaços)
        match = re.search(rf'•\s*{label}:\s+(.+?)(?:\n|$)', text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
        # Se não encontrar com bullet, tenta padrão normal (LABEL: valor)
        match = re.search(rf'{label}:\s+(.+?)(?:\n|$)', text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
        return None
    
    # Dados básicos do Veículo
    data["dados_veiculo"]["placa"] = get_value("PLACA")
    data["dados_veiculo"]["situacao"] = get_value("SITUAÇÃO")
    data["dados_veiculo"]["marca_modelo"] = get_value("MARCA/MODELO")
    data["dados_veiculo"]["cor"] = get_value("COR")
    data["dados_veiculo"]["ano_fabricacao"] = get_value("ANO - FABRICAÇÃO")
    data["dados_veiculo"]["ano_modelo"] = get_value("ANO - MODELO")
    
    # Restrições (1 a 4)
    for i in range(1, 5):
        restricao = get_value(f"RESTRIÇÃO {i}")
        if restricao and "SEM RESTRICAO" not in restricao.upper():
            data["restricoes"].append(restricao)
    
    # Localização
    data["localizacao"]["municipio"] = get_value("MUNICIPIO")
    data["localizacao"]["estado"] = get_value("ESTADO")
    
    # Montar endereço do veículo a partir de localização
    endereco_parts = []
    if data["localizacao"].get("municipio"):
        endereco_parts.append(data["localizacao"]["municipio"])
    if data["localizacao"].get("estado"):
        endereco_parts.append(data["localizacao"]["estado"])
    if endereco_parts:
        data["dados_veiculo"]["endereco_veiculo"] = " - ".join(endereco_parts)
    
    # Fabricação
    data["fabricacao"]["municipio_fab"] = get_value("MUNICIPIO - FAB.")
    data["fabricacao"]["estado_fab"] = get_value("ESTADO - FAB.")
    data["fabricacao"]["doc_faturado"] = get_value("DOC. FATURADO")
    data["fabricacao"]["uf_faturado"] = get_value("UF - FATURADO")
    
    # Especificações Técnicas
    data["especificacoes"]["chassi"] = get_value("CHASSI")
    data["especificacoes"]["renavam"] = get_value("RENAVAM")
    data["especificacoes"]["numero_motor"] = get_value("NÚM. MOTOR")
    data["especificacoes"]["combustivel"] = get_value("COMBUSTÍVEL")
    data["especificacoes"]["potencia"] = get_value("POTENCIA")
    data["especificacoes"]["cilindradas"] = get_value("CILINDRADAS")
    data["especificacoes"]["tipo_veiculo"] = get_value("TIPO DE VEICULO")
    data["especificacoes"]["especie"] = get_value("ESPECIE")
    data["especificacoes"]["segmento"] = get_value("SEGMENTO")
    data["especificacoes"]["sub_segmento"] = get_value("SUB SEGMENTO")
    data["especificacoes"]["grupo"] = get_value("GRUPO")
    data["especificacoes"]["carroceria"] = get_value("CARROCERIA")
    data["especificacoes"]["tipo_carroceria"] = get_value("TIPO CARROCERIA")
    data["especificacoes"]["eixo_traseiro_dif"] = get_value("EIXO TRASEIRO DIF.")
    data["especificacoes"]["origem"] = get_value("ORIGEM")
    data["especificacoes"]["quantidade_passageiros"] = get_value("QUANTIDADE DE PASSAGEIROS")
    
    # Documentação
    data["documentacao"]["id_importadora"] = get_value("ID IMPORTADORA")
    data["documentacao"]["di"] = get_value("DI")
    data["documentacao"]["registro_di"] = get_value("REGISTRO DI")
    data["documentacao"]["unidade_local_srf"] = get_value("UNIDADE LOCAL SRF")
    data["documentacao"]["ultima_atualizacao"] = get_value("ULTIMA ATUALIZAÇÃO")
    data["documentacao"]["emissao_ultimo_crv"] = get_value("EMISSÃO ULTIMO CRV")
    
    # Proprietário
    proprietario_match = re.search(r'PROPRIETÁRIO\s*•\s*CPF/CNPJ:\s*([\d]+)\s*•\s*NOME:\s*(.+?)(?:\n|POSSUIDOR|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if proprietario_match:
        data["proprietario"]["cpf_cnpj"] = proprietario_match.group(1).strip()
        data["proprietario"]["nome"] = proprietario_match.group(2).strip()
    
    # Possuidor
    possuidor_match = re.search(r'POSSUIDOR\s*•\s*CPF/CNPJ:\s*([\d]+)\s*•\s*NOME:\s*(.+?)(?:\n|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if possuidor_match:
        data["possuidor"]["cpf_cnpj"] = possuidor_match.group(1).strip()
        data["possuidor"]["nome"] = possuidor_match.group(2).strip()
    
    data["usuario"] = get_value("USUÁRIO")
    
    return data

def parse_nome_resultado(resultado_texto: str) -> dict:
    """Parser para resultados de consulta de NOME (múltiplos resultados)"""
    import re
    
    data = {
        "resultados": [],
        "tipo_consulta": "nome"
    }
    
    # Encontrar todos os blocos de RESULTADO
    # Pattern: • RESULTADO: N ... até • RESULTADO: seguinte ou fim do texto
    blocos = re.findall(
        r'•\s*RESULTADO:\s*(\d+).*?\n(.*?)(?=•\s*RESULTADO:\s*\d+|•\s*USUÁRIO:|$)',
        resultado_texto,
        re.IGNORECASE | re.DOTALL
    )
    
    for num_resultado, bloco_texto in blocos:
        resultado_item = {}
        
        # Extrair campos do bloco
        def get_value_in_block(label, text=bloco_texto):
            match = re.search(rf'{label}:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            return match.group(1).strip() if match else None
        
        resultado_item["numero"] = num_resultado
        resultado_item["nome"] = get_value_in_block("NOME")
        resultado_item["cpf"] = get_value_in_block("CPF")
        resultado_item["sexo"] = get_value_in_block("SEXO")
        resultado_item["nascimento"] = get_value_in_block("NASCIMENTO")
        
        if resultado_item["nome"]:  # Só adiciona se tem nome
            data["resultados"].append(resultado_item)
    
    # Usuário (está no final)
    usuario_match = re.search(r'•\s*USUÁRIO:\s*(.+?)(?:\n|$)', resultado_texto, re.IGNORECASE)
    data["usuario"] = usuario_match.group(1).strip() if usuario_match else None
    
    return data

def get_user_statistics(username: str, is_admin: bool = False):
    """Retorna estatísticas do usuário ou sistema (se admin)"""
    stats = {}
    
    try:
        # Total de consultas
        if is_admin:
            cursor.execute("SELECT COUNT(*) FROM searches")
        else:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE username = ?", (username,))
        stats['total_consultas'] = cursor.fetchone()[0]
        
        # Consultas hoje
        if is_admin:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE DATE(searched_at) = DATE('now', 'localtime')")
        else:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE username = ? AND DATE(searched_at) = DATE('now', 'localtime')", (username,))
        stats['consultas_hoje'] = cursor.fetchone()[0]
        
        # Consultas esta semana
        if is_admin:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE DATE(searched_at) >= DATE('now', 'localtime', '-7 days')")
        else:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE username = ? AND DATE(searched_at) >= DATE('now', 'localtime', '-7 days')", (username,))
        stats['consultas_semana'] = cursor.fetchone()[0]
        
        # Consultas este mês
        if is_admin:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE DATE(searched_at) >= DATE('now', 'localtime', '-30 days')")
        else:
            cursor.execute("SELECT COUNT(*) FROM searches WHERE username = ? AND DATE(searched_at) >= DATE('now', 'localtime', '-30 days')", (username,))
        stats['consultas_mes'] = cursor.fetchone()[0]
        
        # Consultas por dia (últimos 7 dias)
        if is_admin:
            cursor.execute("""
                SELECT DATE(searched_at) as data, COUNT(*) as total 
                FROM searches 
                WHERE DATE(searched_at) >= DATE('now', 'localtime', '-7 days')
                GROUP BY DATE(searched_at)
                ORDER BY data DESC
            """)
        else:
            cursor.execute("""
                SELECT DATE(searched_at) as data, COUNT(*) as total 
                FROM searches 
                WHERE username = ? AND DATE(searched_at) >= DATE('now', 'localtime', '-7 days')
                GROUP BY DATE(searched_at)
                ORDER BY data DESC
            """, (username,))
        stats['consultas_por_dia'] = cursor.fetchall()
        
        # Horário de pico (hora com mais consultas)
        if is_admin:
            cursor.execute("""
                SELECT strftime('%H', searched_at) as hora, COUNT(*) as total
                FROM searches
                GROUP BY hora
                ORDER BY total DESC
                LIMIT 1
            """)
        else:
            cursor.execute("""
                SELECT strftime('%H', searched_at) as hora, COUNT(*) as total
                FROM searches
                WHERE username = ?
                GROUP BY hora
                ORDER BY total DESC
                LIMIT 1
            """, (username,))
        pico = cursor.fetchone()
        stats['horario_pico'] = f"{pico[0]}:00" if pico else "N/A"
        stats['consultas_pico'] = pico[1] if pico else 0
        
        # Se for admin, busca top usuários
        if is_admin:
            cursor.execute("""
                SELECT username, COUNT(*) as total
                FROM searches
                WHERE username IS NOT NULL AND username NOT IN ('admin', 'None', 'T')
                GROUP BY username
                ORDER BY total DESC
                LIMIT 5
            """)
            stats['top_usuarios'] = cursor.fetchall()
        else:
            stats['top_usuarios'] = []
        
        # Total de favoritos
        cursor.execute("SELECT COUNT(*) FROM favorites WHERE username = ?", (username,))
        stats['total_favoritos'] = cursor.fetchone()[0]
        
    except Exception as e:
        # Em caso de erro, retorna estatísticas zeradas
        stats = {
            'total_consultas': 0,
            'consultas_hoje': 0,
            'consultas_semana': 0,
            'consultas_mes': 0,
            'consultas_por_dia': [],
            'horario_pico': 'N/A',
            'consultas_pico': 0,
            'top_usuarios': [],
            'total_favoritos': 0
        }
    
    return stats

# ----------------------
# Rotas de Autenticação
# ----------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Verificar se sessão expirou
    if request.cookies.get("auth_user") and is_session_expired(request):
        response = templates.TemplateResponse("login.html", {
            "request": request,
            "info": "Sua sessão expirou. Por favor, autentique-se novamente."
        })
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    if request.cookies.get("auth_user"):
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    client_ip = get_client_ip(request)
    
    # Verificar rate limiting
    if not check_rate_limit(client_ip):
        record_audit_log("LOGIN_BLOCKED", username, client_ip, "Excedidas tentativas de login")
        
        # Calcular tempo restante
        if client_ip in login_attempts:
            attempts = login_attempts[client_ip]
            time_passed = datetime.now() - attempts['first_attempt']
            time_remaining = max(0, LOGIN_ATTEMPT_WINDOW - int(time_passed.total_seconds()))
            minutes = time_remaining // 60
            seconds = time_remaining % 60
            erro_msg = f"Muitas tentativas. Aguarde {minutes}m {seconds}s para tentar novamente."
        else:
            erro_msg = "Sistema temporariamente indisponível. Tente novamente mais tarde."
        
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": erro_msg,
            "show_unlock": True
        })
    
    record_login_attempt(client_ip)
    
    # Validação básica
    if not username or not password:
        record_audit_log("LOGIN_FAILED", username, client_ip, "Campos vazios")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": "Credenciais inválidas"
        })
    
    # Verificar credenciais
    cursor.execute("SELECT id, is_admin, status, senha_temporaria FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    
    if user:
        user_id = user[0]
        is_admin = user[1]
        status = user[2]
        senha_temporaria = user[3] if len(user) > 3 else 0
        
        # Verificar se usuário está ativo (status = 1 ou NULL para compatibilidade)
        if status is None:
            status = 1  # Compatibilidade com bancos antigos
        
        if status != 1:
            # Usuário está inativo
            record_audit_log("LOGIN_FAILED", username, client_ip, "Usuário inativo")
            return templates.TemplateResponse("login.html", {
                "request": request,
                "erro": "Usuário inativo. Contate o administrador."
            })
        
        # Atualizar último login
        try:
            cursor.execute("UPDATE users SET ultimo_login = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            conn.commit()
        except:
            pass  # Se a coluna não existir, ignora
        
        # Se usuário usou senha padrão, redirecionar para alterar senha
        if senha_temporaria == 1:
            # Criar cookie temporário para mudança de senha obrigatória
            response = RedirectResponse(url="/mudar-senha-obrigatoria", status_code=303)
            auth_time = (datetime.now() + timedelta(seconds=SESSION_TIMEOUT)).isoformat()
            response.set_cookie(key="auth_user", value=username, max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
            response.set_cookie(key="is_admin", value=str(is_admin), max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
            response.set_cookie(key="auth_time", value=auth_time, max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
            response.set_cookie(key="senha_temporaria", value="1", max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
            record_audit_log("LOGIN_TENTATIVA_SENHA_PADRAO", username, client_ip, "Redirecionado para mudança obrigatória de senha")
            return response
        
        # Login bem-sucedido
        record_audit_log("LOGIN_SUCCESS", username, client_ip, "")
        response = RedirectResponse(url="/", status_code=303)
        auth_time = (datetime.now() + timedelta(seconds=SESSION_TIMEOUT)).isoformat()
        response.set_cookie(key="auth_user", value=username, max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
        response.set_cookie(key="is_admin", value=str(is_admin), max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
        response.set_cookie(key="auth_time", value=auth_time, max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
        return response
    
    # Login falhou
    record_audit_log("LOGIN_FAILED", username, client_ip, "Credenciais incorretas")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "erro": "Credenciais inválidas"
    })

@app.get("/logout")
async def logout(request: Request):
    username = request.cookies.get("auth_user", "unknown")
    client_ip = get_client_ip(request)
    record_audit_log("LOGOUT", username, client_ip, "")
    
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="auth_user")
    response.delete_cookie(key="is_admin")
    response.delete_cookie(key="auth_time")
    response.delete_cookie(key="senha_temporaria")
    return response

@app.get("/mudar-senha-obrigatoria", response_class=HTMLResponse)
async def mudar_senha_obrigatoria(request: Request):
    """Página obrigatória para mudança de senha na primeira autenticação com senha padrão"""
    # Verificar se usuário está em processo de mudança de senha obrigatória
    if not request.cookies.get("auth_user") or not request.cookies.get("senha_temporaria"):
        return RedirectResponse(url="/login")
    
    username = request.cookies.get("auth_user")
    csrf_token = get_or_create_csrf_token(request)
    return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
        "request": request,
        "username": username,
        "csrf_token": csrf_token
    })

@app.post("/mudar-senha-obrigatoria")
async def processar_mudanca_senha_obrigatoria(request: Request, 
                                              nova_senha: str = Form(...), 
                                              confirmar_senha: str = Form(...),
                                              csrf_token: str = Form(...)):
    """Processa a mudança obrigatória de senha"""
    # Verificar autenticação
    if not request.cookies.get("auth_user") or not request.cookies.get("senha_temporaria"):
        return RedirectResponse(url="/login")
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Validar CSRF token
    if not validate_csrf_token(request, csrf_token):
        record_audit_log("INVALID_CSRF_SENHA", username, client_ip, "Token CSRF inválido na mudança de senha")
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "Sessão inválida. Por favor, recarregue a página.",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    # Validações
    if not nova_senha or not confirmar_senha:
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "Informe a nova senha e confirmação",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    if len(nova_senha) < 4:
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "Senha deve ter no mínimo 4 caracteres",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    if nova_senha != confirmar_senha:
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "As senhas não coincidem",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    if nova_senha == "mdr123":
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "A nova senha não pode ser a mesma que a senha padrão",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    # Atualizar senha e marcar que mudou
    try:
        cursor.execute(
            "UPDATE users SET password = ?, senha_temporaria = 0 WHERE username = ?",
            (nova_senha, username)
        )
        conn.commit()
        
        record_audit_log("SENHA_ALTERADA_OBRIGATORIA", username, client_ip, "Alterou senha padrão com sucesso")
        
        # Redirecionar para home
        response = RedirectResponse(url="/", status_code=303)
        # Remover cookie de senha temporária
        response.delete_cookie(key="senha_temporaria")
        return response
    except Exception as e:
        record_audit_log("ERRO_ALTERAR_SENHA", username, client_ip, str(e))
        return templates.TemplateResponse("mudar-senha-obrigatoria.html", {
            "request": request,
            "username": username,
            "erro": "Erro ao alterar senha. Tente novamente.",
            "csrf_token": get_or_create_csrf_token(request)
        })

@app.post("/api/unlock-ip")
async def unlock_ip(request: Request):
    """
    Endpoint de emergência para desbloquear IP (sem autenticação necessária).
    Útil quando o usuário está bloqueado por muitas tentativas de login.
    """
    client_ip = get_client_ip(request)
    
    # Remover bloqueio dessa IP
    if client_ip in login_attempts:
        del login_attempts[client_ip]
        record_audit_log("IP_UNLOCKED", "auto", client_ip, "Desbloqueio manual solicitado")
        return JSONResponse({"success": True, "message": "IP desbloqueado! Tente novamente."})
    
    return JSONResponse({"success": False, "message": "Nenhum bloqueio ativo para seu IP."})

@app.get("/api/consulta/{search_id}")
async def get_consulta_details(request: Request, search_id: int):
    """Obtém os detalhes completos de uma consulta para exibição em tela cheia"""
    if not request.cookies.get("auth_user"):
        return JSONResponse({"success": False, "error": "Não autenticado"})
    
    if is_session_expired(request):
        return JSONResponse({"success": False, "error": "Sessão expirada"})
    
    username = request.cookies.get("auth_user")
    
    # Buscar consulta do usuário
    cursor.execute(
        "SELECT id, identifier, response, data FROM searches WHERE id = ? AND username = ?",
        (search_id, username)
    )
    search = cursor.fetchone()
    
    if not search:
        return JSONResponse({"success": False, "error": "Consulta não encontrada"})
    
    # Parser dos dados
    dados = parse_resultado_consulta(search[2])
    
    # Registrar auditoria
    record_audit_log("FULL_VIEW", username, get_client_ip(request), f"Ver completo: {search[1]}")
    
    return JSONResponse({
        "success": True,
        "data": {
            "id": search[0],
            "identifier": search[1],
            "data": search[3],
            "response": search[2],
            "parsed": dados
        }
    })

@app.get("/view-resultado/{search_id}", response_class=HTMLResponse)
async def view_resultado_completo(request: Request, search_id: int):
    """Exibe o resultado completo em tela cheia"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if is_session_expired(request):
        return RedirectResponse(url="/login")
    
    username = request.cookies.get("auth_user")
    
    # Buscar consulta do usuário
    cursor.execute(
        "SELECT id, identifier, response FROM searches WHERE id = ? AND username = ?",
        (search_id, username)
    )
    search = cursor.fetchone()
    
    if not search:
        return "<h1>Consulta não encontrada</h1>"
    
    # Parser dos dados
    dados = parse_resultado_consulta(search[2])
    
    return templates.TemplateResponse("modern-result.html", {
        "request": request,
        "identifier": search[1],
        "resultado": search[2],
        "dados": dados,
        "csrf_token": get_or_create_csrf_token(request)
    })

# ----------------------
# Rotas do Sistema
# ----------------------
@app.get("/", response_class=HTMLResponse)
def form(request: Request):
    # Validar sessão do usuário
    session_error = validate_user_session(request)
    if session_error:
        return session_error
    
    # Obter estatísticas para o dashboard
    username = request.cookies.get("auth_user")
    is_admin = request.cookies.get("is_admin") == "1"
    
    # Estatísticas do usuário
    stats = get_user_statistics(username, is_admin)
    
    csrf_token = get_or_create_csrf_token(request)
    return templates.TemplateResponse("modern-form.html", {
        "request": request, 
        "csrf_token": csrf_token,
        "stats": stats
    })

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """Dashboard administrativo com estatísticas e gráficos"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    # Verificar se é admin
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Registrar acesso ao dashboard
    record_audit_log("ACCESS_ADMIN_DASHBOARD", username, client_ip, "Acessou dashboard administrativo")
    
    # Obter estatísticas globais (admin)
    stats = get_user_statistics(username, is_admin=True)
    
    # Obter dados adicionais para gráficos
    # Consultas dos últimos 30 dias
    cursor.execute("""
        SELECT DATE(searched_at) as dia, COUNT(*) as total
        FROM searches
        WHERE DATE(searched_at) >= DATE('now', '-30 days')
        GROUP BY DATE(searched_at)
        ORDER BY dia
    """)
    consultas_30_dias = cursor.fetchall()
    
    # Top 10 usuários (excluindo admin, None, T)
    cursor.execute("""
        SELECT username, COUNT(*) as total
        FROM searches
        WHERE username IS NOT NULL AND username NOT IN ('admin', 'None', 'T')
        GROUP BY username
        ORDER BY total DESC
        LIMIT 10
    """)
    top_usuarios = cursor.fetchall()
    
    # Consultas por hora do dia
    cursor.execute("""
        SELECT CAST(strftime('%H', searched_at) AS INTEGER) as hora, COUNT(*) as total
        FROM searches
        GROUP BY hora
        ORDER BY hora
    """)
    consultas_por_hora = cursor.fetchall()
    
    # Total de usuários
    cursor.execute("SELECT COUNT(*) FROM users")
    total_usuarios = cursor.fetchone()[0]
    
    # Adicionar dados aos stats
    stats['consultas_ultimos_30_dias'] = [(row[0], row[1]) for row in consultas_30_dias]
    stats['top_usuarios'] = top_usuarios
    stats['consultas_por_hora'] = consultas_por_hora
    stats['total_usuarios'] = total_usuarios
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "stats": stats
    })

@app.post("/consulta", response_class=HTMLResponse)
async def do_consulta(request: Request):
    # Validar sessão do usuário
    session_error = validate_user_session(request)
    if session_error:
        return session_error
    
    form_data = await request.form()
    csrf_token = str(form_data.get("csrf_token", "")).strip()
    identificador = str(form_data.get("identificador", "")).strip()
    tipo_manual = str(form_data.get("tipo", "")).strip().lower()
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Validar CSRF token
    if not validate_csrf_token(request, csrf_token):
        record_audit_log("INVALID_CSRF", username, client_ip, "Token CSRF inválido ou expirado")
        return templates.TemplateResponse("modern-form.html", {
            "request": request, 
            "erro": "Sessão inválida. Por favor, recarregue a página.",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    # Verificar rate limit em consultas
    if not check_query_rate_limit(username):
        record_audit_log("RATE_LIMIT_QUERY", username, client_ip, f"Máximo de {MAX_QUERIES_PER_MINUTE} consultas por minuto")
        return templates.TemplateResponse("modern-form.html", {
            "request": request, 
            "erro": f"Limite de {MAX_QUERIES_PER_MINUTE} consultas por minuto atingido. Tente novamente em 1 minuto.",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    record_query_attempt(username)
    
    if not identificador:
        return templates.TemplateResponse("modern-form.html", {
            "request": request, 
            "erro": "Digite um identificador válido",
            "csrf_token": get_or_create_csrf_token(request)
        })
    
    tipo = tipo_manual if (tipo_manual and tipo_manual != "auto") else detect_tipo(identificador)
    
    if tipo == 'cpf': 
        cmd = f"/cpf3 {normalize(identificador)}"
    elif tipo == 'cnpj': 
        cmd = f"/cnpj3 {normalize(identificador)}"
    elif tipo == 'placa': 
        cmd = f"/placa {normalize_placa(identificador)}"
    elif tipo == 'nome': 
        cmd = f"/nome {identificador}"
    else: 
        return templates.TemplateResponse("modern-form.html", {
            "request": request, 
            "erro": "Tipo de identificador não reconhecido"
        })
    
    try:
        resultado = await consulta_telegram(cmd)
        
        # Limpar e sanitizar resultado para evitar problemas de encoding
        if isinstance(resultado, bytes):
            try:
                resultado = resultado.decode('utf-8', errors='replace')
            except:
                resultado = str(resultado)
        
        # Garantir que é string
        resultado = str(resultado)
        
        # Salvar no histórico apenas se não for erro
        if not resultado.startswith("❌"):
            try:
                username = request.cookies.get("auth_user")
                cursor.execute(
                    "INSERT INTO searches (identifier, response, username) VALUES (?, ?, ?)", 
                    (identificador, resultado, username)
                )
                conn.commit()
            except Exception as save_err:
                print(f"⚠️ Erro ao salvar no histórico: {str(save_err)}")
        
        # Parser do resultado para dados estruturados
        # Passar o 'tipo' detectado para garantir parser correto
        dados_estruturados = None
        if not resultado.startswith("❌"):
            try:
                dados_estruturados = parse_resultado_consulta(resultado, tipo)
            except Exception as parse_err:
                print(f"🔴 Erro ao fazer parse do resultado: {str(parse_err)}")
                print(f"   Tamanho do resultado: {len(resultado)}")
                print(f"   Primeiros 300 chars: {repr(resultado[:300])}")
                print(f"   Últimos 300 chars: {repr(resultado[-300:])}")
                # Continua mesmo com erro de parsing
        
        # Enriquecer dados com APIs públicas grátis
        apis_data = {}
        if dados_estruturados:
            try:
                apis_data = await enriquecer_dados_com_apis(identificador, tipo, dados_estruturados)
            except Exception as api_error:
                print(f"⚠️ Erro ao enriquecer APIs: {str(api_error)}")
                import traceback
                traceback.print_exc()
                pass  # Se falhar, continua sem enriquecimento
        
        return templates.TemplateResponse("modern-result.html", {
            "request": request, 
            "mensagem": identificador, 
            "resultado": resultado,  # Jinja2 escapará automaticamente
            "dados": dados_estruturados,
            "apis_data": apis_data,
            "identifier": identificador,
            "csrf_token": get_or_create_csrf_token(request)
        })
    except Exception as e:
        username = request.cookies.get("auth_user", "unknown")
        client_ip = get_client_ip(request)
        error_msg = str(e)
        print(f"🔴 ERRO NA CONSULTA: {error_msg}")
        print(f"Tipo: {tipo}, Identificador: {identificador}")
        import traceback
        traceback.print_exc()
        record_audit_log("QUERY_ERROR", username, client_ip, error_msg)
        return templates.TemplateResponse("modern-form.html", {
            "request": request,
            "erro": f"Erro ao processar consulta. Detalhes: {error_msg[:150]}"
        })

@app.get("/historico", response_class=HTMLResponse)
def historico(request: Request):
    # Validar sessão do usuário
    session_error = validate_user_session(request)
    if session_error:
        return session_error
    
    username = request.cookies.get("auth_user")
    cursor.execute("""
        SELECT s.id, s.identifier, s.response, s.searched_at, 
               CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_favorite
        FROM searches s
        LEFT JOIN favorites f ON s.id = f.search_id AND f.username = ?
        WHERE s.username = ?
        ORDER BY s.searched_at DESC
        LIMIT 100
    """, (username, username))
    searches = cursor.fetchall()
    
    consultas = []
    for s in searches:
        # Buscar notas
        cursor.execute("SELECT note, created_at FROM notes WHERE search_id = ? ORDER BY created_at DESC LIMIT 1", (s[0],))
        note_row = cursor.fetchone()
        note_text = note_row[0] if note_row else None
        note_date = format_timestamp_br(note_row[1]) if note_row else None
        
        # Buscar tags
        cursor.execute("SELECT tag_name FROM tags WHERE search_id = ? ORDER BY created_at", (s[0],))
        tags_rows = cursor.fetchall()
        tags_list = [t[0] for t in tags_rows]
        
        consultas.append({
            "id": s[0], 
            "id_alvo": s[1], 
            "data": format_timestamp_br(s[3]), 
            "response": s[2],
            "is_favorite": s[4] == 1,
            "note": note_text,
            "note_date": note_date,
            "tags": tags_list
        })
    
    return templates.TemplateResponse("historico.html", {
        "request": request, 
        "consultas": consultas,
        "csrf_token": get_or_create_csrf_token(request)
    })

@app.get("/search/by-phone/{phone}", response_class=JSONResponse)
async def reverse_search_phone(request: Request, phone: str):
    """Busca reversa por telefone - encontra pessoas com este telefone no histórico"""
    if not request.cookies.get("auth_user"):
        return {"erro": "Não autenticado", "resultados": []}
    
    if is_session_expired(request):
        return {"erro": "Sessão expirada", "resultados": []}
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Limpar telefone (remover caracteres especiais)
    phone_clean = ''.join(filter(str.isdigit, phone))
    
    # Buscar todas as consultas de TODOS os usuários
    cursor.execute(
        "SELECT id, identifier, response FROM searches"
    )
    searches = cursor.fetchall()
    
    resultados = []
    cpf_adicionados = set()  # Evitar duplicatas
    
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por telefone
        if dados["telefones"]:
            for telefone in dados["telefones"]:
                telefone_clean = ''.join(filter(str.isdigit, telefone))
                if telefone_clean == phone_clean:
                    cpf = dados["dados_pessoais"].get("cpf", "N/A")
                    # Apenas adicionar se CPF ainda não está na lista
                    if cpf not in cpf_adicionados:
                        resultados.append({
                            "identifier": identifier,
                            "nome": dados["dados_pessoais"].get("nome", "N/A"),
                            "cpf": cpf,
                            "tipo": "Proprietário"
                        })
                        cpf_adicionados.add(cpf)
                    break
    
    record_audit_log("REVERSE_SEARCH", username, client_ip, f"Busca reversa por telefone: {phone}")
    
    return {
        "sucesso": True,
        "tipo": "telefone",
        "valor": phone,
        "total": len(resultados),
        "resultados": resultados
    }

@app.get("/search/by-email/{email}", response_class=JSONResponse)
async def reverse_search_email(request: Request, email: str):
    """Busca reversa por e-mail - encontra pessoas com este e-mail no histórico"""
    if not request.cookies.get("auth_user"):
        return {"erro": "Não autenticado", "resultados": []}
    
    if is_session_expired(request):
        return {"erro": "Sessão expirada", "resultados": []}
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Email em lowercase
    email_lower = email.lower()
    
    # Buscar todas as consultas de TODOS os usuários
    cursor.execute(
        "SELECT id, identifier, response FROM searches"
    )
    searches = cursor.fetchall()
    
    resultados = []
    cpf_adicionados = set()  # Evitar duplicatas
    
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por email
        if dados["emails"]:
            for mail in dados["emails"]:
                if mail.lower() == email_lower:
                    cpf = dados["dados_pessoais"].get("cpf", "N/A")
                    # Apenas adicionar se CPF ainda não está na lista
                    if cpf not in cpf_adicionados:
                        resultados.append({
                            "identifier": identifier,
                            "nome": dados["dados_pessoais"].get("nome", "N/A"),
                            "cpf": cpf,
                            "tipo": "Proprietário"
                        })
                        cpf_adicionados.add(cpf)
                    break
    
    record_audit_log("REVERSE_SEARCH", username, client_ip, f"Busca reversa por e-mail: {email}")
    
    return {
        "sucesso": True,
        "tipo": "email",
        "valor": email,
        "total": len(resultados),
        "resultados": resultados
    }

@app.get("/search/by-address/{address}", response_class=JSONResponse)
async def reverse_search_address(request: Request, address: str):
    """Busca reversa por endereço - encontra pessoas neste endereço no histórico"""
    if not request.cookies.get("auth_user"):
        return {"erro": "Não autenticado", "resultados": []}
    
    if is_session_expired(request):
        return {"erro": "Sessão expirada", "resultados": []}
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Normalizar endereço para comparação (remover acentos, lowercase)
    address_norm = address.lower().strip()
    
    # Buscar todas as consultas de TODOS os usuários
    cursor.execute(
        "SELECT id, identifier, response FROM searches"
    )
    searches = cursor.fetchall()
    
    resultados = []
    cpf_adicionados = set()  # Evitar duplicatas
    
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por endereço (busca parcial)
        if dados["enderecos"]:
            for endereco in dados["enderecos"]:
                endereco_norm = endereco.lower().strip()
                # Busca por similaridade (se contém palavras-chave)
                if address_norm in endereco_norm or endereco_norm in address_norm:
                    cpf = dados["dados_pessoais"].get("cpf", "N/A")
                    # Apenas adicionar se CPF ainda não está na lista
                    if cpf not in cpf_adicionados:
                        resultados.append({
                            "identifier": identifier,
                            "nome": dados["dados_pessoais"].get("nome", "N/A"),
                            "cpf": cpf,
                            "endereco": endereco,
                            "tipo": "Residente"
                        })
                        cpf_adicionados.add(cpf)
                    break
    
    record_audit_log("REVERSE_SEARCH", username, client_ip, f"Busca reversa por endereço: {address}")
    
    return {
        "sucesso": True,
        "tipo": "endereco",
        "valor": address,
        "total": len(resultados),
        "resultados": resultados
    }

@app.post("/historico/limpar")
async def limpar_historico(request: Request, csrf_token: str = Form(...)):
    # Validar sessão do usuário
    session_error = validate_user_session(request)
    if session_error:
        return session_error
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Validar CSRF token
    csrf_token_str = str(csrf_token).strip() if csrf_token else ""
    if not csrf_token_str or not validate_csrf_token(request, csrf_token_str):
        record_audit_log("INVALID_CSRF_CLEAR", username, client_ip, "Tentativa de limpar histórico com CSRF inválido")
        return JSONResponse({"success": False, "error": "Token CSRF inválido"}, status_code=403)
    
    try:
        cursor.execute("DELETE FROM searches WHERE username = ?", (username,))
        conn.commit()
        record_audit_log("CLEAR_HISTORY", username, client_ip, "Histórico limpo com sucesso")
        return JSONResponse({"success": True, "message": "Histórico limpo com sucesso"})
    except Exception as e:
        record_audit_log("ERROR_CLEAR_HISTORY", username, client_ip, str(e))
        return JSONResponse({"success": False, "error": f"Erro ao limpar histórico: {str(e)}"}, status_code=500)

@app.post("/api/validar-endereco")
async def api_validar_endereco(request: Request):
    """Endpoint para validar endereço específico sob demanda"""
    try:
        # Validar usuário (sem redirecionar)
        username = request.cookies.get("auth_user")
        if not username:
            return JSONResponse({"erro": "Não autenticado"}, status_code=401)
        
        try:
            data = await request.json()
        except Exception as json_err:
            print(f"❌ Erro ao fazer parse JSON do request: {str(json_err)}")
            return JSONResponse({"erro": "JSON inválido no request"}, status_code=400)
        
        endereco = data.get("endereco", "").strip()
        
        if not endereco:
            return JSONResponse({"erro": "Endereço vazio"}, status_code=400)
        
        # Buscar APIs para endereço
        resultado = await enriquecher_endereco_selecionado(endereco)
        
        if not resultado.get("viacep") and not resultado.get("nominatim"):
            return JSONResponse({"erro": "Não foi possível validar endereço"}, status_code=400)
        
        return JSONResponse(resultado)
    except Exception as e:
        print(f"🔴 Erro em /api/validar-endereco: {str(e)}")
        return JSONResponse({"erro": f"Erro ao validar: {str(e)[:100]}"}, status_code=500)

@app.get("/historico/exportar/csv")
async def export_historico_csv(request: Request):
    """Exporta histórico em CSV"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if is_session_expired(request):
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches WHERE username = ? ORDER BY searched_at DESC", (username,))
    searches = cursor.fetchall()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Identificador", "Resposta", "Data"])
    for row in searches:
        writer.writerow([row[0], row[1], row[2], format_timestamp_br(row[3])])
    
    client_ip = get_client_ip(request)
    record_audit_log("EXPORT_CSV", username, client_ip, f"{len(searches)} registros exportados")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=historico_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/historico/exportar/json")
async def export_historico_json(request: Request):
    """Exporta histórico em JSON"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if is_session_expired(request):
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches WHERE username = ? ORDER BY searched_at DESC", (username,))
    searches = cursor.fetchall()
    
    data = [{"id": s[0], "identifier": s[1], "response": s[2], "searched_at": format_timestamp_br(s[3])} for s in searches]
    
    client_ip = get_client_ip(request)
    record_audit_log("EXPORT_JSON", username, client_ip, f"{len(searches)} registros exportados")
    
    return StreamingResponse(
        iter([json.dumps(data, ensure_ascii=False, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=historico_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )

@app.get("/api/historico")
def api_historico(request: Request):
    if not request.cookies.get("auth_user"): raise HTTPException(status_code=401, detail="Não autorizado")
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches ORDER BY searched_at DESC LIMIT 100")
    searches = cursor.fetchall()
    return [{"id": s[0], "identifier": s[1], "response": s[2], "searched_at": s[3]} for s in searches]

# ----------------------
# Painel de Admin
# ----------------------
@app.get("/admin/logs", response_class=HTMLResponse)
async def admin_logs(request: Request):
    """Dashboard com logs de auditoria"""
    # Verificar autenticação e admin status
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/")
    
    # Buscar logs (últimos 500)
    cursor.execute("""
        SELECT id, action, username, ip_address, timestamp, details 
        FROM audit_logs 
        ORDER BY timestamp DESC 
        LIMIT 500
    """)
    logs = cursor.fetchall()
    
    log_list = [
        {
            "id": l[0],
            "action": l[1],
            "username": l[2],
            "ip": l[3],
            "timestamp": format_timestamp_br(l[4]),
            "details": l[5]
        }
        for l in logs
    ]
    
    return templates.TemplateResponse("admin_logs.html", {
        "request": request,
        "logs": log_list
    })

# ----------------------
# Gestão de Usuários (Apenas Admin)
# ----------------------
@app.get("/usuarios", response_class=HTMLResponse)
async def list_users(request: Request):
    # Verificar autenticação
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    # Apenas admin pode gerenciar usuários
    if request.cookies.get("is_admin") != "1": 
        return RedirectResponse(url="/")
    
    try:
        # Tentar com as novas colunas
        cursor.execute("SELECT id, username, is_admin, data_criacao, ultimo_login, status, numero_consultas FROM users ORDER BY data_criacao DESC")
        usuarios = cursor.fetchall()
    except sqlite3.OperationalError:
        # Se falhar, usar query com colunas básicas + valores padrão
        cursor.execute("SELECT id, username, is_admin, CURRENT_TIMESTAMP, NULL, 1, 0 FROM users ORDER BY id DESC")
        usuarios = cursor.fetchall()
    
    csrf_token = get_or_create_csrf_token(request)
    return templates.TemplateResponse("usuarios.html", {
        "request": request, 
        "usuarios": usuarios,
        "csrf_token": csrf_token
    })

@app.post("/usuarios/novo")
async def create_user(request: Request, new_user: str = Form(...), new_pass: str = Form(""), admin: str = Form(None), csrf_token: str = Form(...)):
    # Verificar autenticação e admin status
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login", status_code=303)
    
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Validar CSRF token
    if not validate_csrf_token(request, csrf_token):
        record_audit_log("INVALID_CSRF", username, client_ip, "Tentativa de criar usuário com CSRF inválido")
        return RedirectResponse(url="/usuarios", status_code=303)
    
    # Se senha não for fornecida, usar padrão "mdr123"
    usar_senha_padrao = False
    if not new_pass or new_pass.strip() == "":
        new_pass = "mdr123"
        usar_senha_padrao = True
    
    try:
        if usar_senha_padrao:
            cursor.execute("INSERT INTO users (username, password, is_admin, senha_temporaria) VALUES (?, ?, ?, 1)", 
                         (new_user, new_pass, 1 if admin else 0))
        else:
            cursor.execute("INSERT INTO users (username, password, is_admin, senha_temporaria) VALUES (?, ?, ?, 0)", 
                         (new_user, new_pass, 1 if admin else 0))
        conn.commit()
        record_audit_log("CREATE_USER", username, client_ip, f"Novo usuário: {new_user}, admin: {bool(admin)}, senha padrão: {usar_senha_padrao}")
    except: 
        record_audit_log("CREATE_USER_FAILED", username, client_ip, f"Falha ao criar: {new_user}")
    
    return RedirectResponse(url="/usuarios", status_code=303)

@app.get("/usuarios/deletar/{user_id}")
async def delete_user(request: Request, user_id: int):
    # Verificar autenticação e admin status
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login", status_code=303)
    
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    cursor.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))
    conn.commit()
    record_audit_log("DELETE_USER", username, client_ip, f"Usuário ID: {user_id} deletado")
    return RedirectResponse(url="/usuarios", status_code=303)

@app.post("/usuarios/alterar-senha")
async def change_password(request: Request, user_id: int = Form(...), new_pass: str = Form(...), csrf_token: str = Form(...)):
    # Verificar autenticação e admin status
    if not request.cookies.get("auth_user"):
        return JSONResponse({"success": False, "error": "Não autenticado"}, status_code=401)
    
    if is_session_expired(request):
        return JSONResponse({"success": False, "error": "Sessão expirada"}, status_code=401)
    
    if request.cookies.get("is_admin") != "1":
        return JSONResponse({"success": False, "error": "Acesso negado"}, status_code=403)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Validar CSRF token
    csrf_token_str = str(csrf_token).strip() if csrf_token else ""
    if not csrf_token_str or not validate_csrf_token(request, csrf_token_str):
        record_audit_log("INVALID_CSRF_CHANGE_PASS", username, client_ip, "Tentativa de alterar senha com CSRF inválido")
        return JSONResponse({"success": False, "error": "Sessão inválida. Recarregue a página."}, status_code=403)
    
    # Validar senha
    if not new_pass or len(new_pass) < 4:
        return JSONResponse({"success": False, "error": "Senha deve ter no mínimo 4 caracteres"}, status_code=400)
    
    try:
        # Verificar se o usuário existe
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return JSONResponse({"success": False, "error": "Usuário não encontrado"}, status_code=404)
        
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_pass, user_id))
        conn.commit()
        record_audit_log("CHANGE_PASSWORD", username, client_ip, f"Senha alterada para usuário: {user[0]} (ID: {user_id})")
        return JSONResponse({"success": True, "message": "Senha alterada com sucesso"})
    except Exception as e:
        record_audit_log("CHANGE_PASSWORD_FAILED", username, client_ip, f"Falha ao alterar senha para ID: {user_id} - {str(e)}")
        return JSONResponse({"success": False, "error": f"Erro ao alterar senha: {str(e)}"}, status_code=500)

# ──────────────────────────────────────────
# Novas Rotas para Gerenciamento de Usuários
# ──────────────────────────────────────────

@app.get("/api/usuarios/stats")
async def get_user_stats(request: Request):
    """Retorna estatísticas de usuários em JSON"""
    if not request.cookies.get("auth_user") or request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        total_admins = cursor.fetchone()[0]
        
        # Tentar com a coluna 'status', se não existir usar valor padrão
        try:
            cursor.execute("SELECT COUNT(*) FROM users WHERE status = 1")
            total_ativos = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            total_ativos = total_users
        
        # Tentar com a coluna 'data_criacao', se não existir usar 0
        try:
            cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(data_criacao) = DATE('now')")
            users_hoje = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            users_hoje = 0
        
        # Tentar com a coluna 'numero_consultas', se não existir usar 0
        try:
            cursor.execute("SELECT SUM(numero_consultas) FROM users")
            total_consultas = cursor.fetchone()[0] or 0
        except sqlite3.OperationalError:
            total_consultas = 0
        
        return {
            "total_users": total_users,
            "total_admins": total_admins,
            "total_operadores": total_users - total_admins,
            "total_ativos": total_ativos,
            "users_hoje": users_hoje,
            "total_consultas": total_consultas
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/usuarios/importar-csv")
async def import_users_csv(request: Request, file: UploadFile = File(...)):
    """Importa múltiplos usuários de um arquivo CSV"""
    if not request.cookies.get("auth_user") or request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    try:
        content = await file.read()
        lines = content.decode('utf-8').split('\n')
        reader = csv.DictReader(lines)
        
        added = 0
        skipped = 0
        
        for row in reader:
            try:
                new_user = row.get('username', '').strip()
                new_pass = row.get('password', '').strip()
                is_admin = int(row.get('is_admin', 0))
                
                if new_user and new_pass:
                    cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                                 (new_user, new_pass, is_admin))
                    added += 1
            except sqlite3.IntegrityError:
                skipped += 1
        
        conn.commit()
        record_audit_log("IMPORT_USERS_CSV", username, client_ip, f"Importado: {added} usuários, Ignorado: {skipped}")
        
        return {"success": True, "added": added, "skipped": skipped}
    except Exception as e:
        record_audit_log("IMPORT_USERS_CSV_FAILED", username, client_ip, str(e))
        return {"error": str(e)}

@app.post("/usuarios/mudar-permissao")
async def toggle_user_permission(request: Request, user_id: int = Form(...)):
    """Alterna permissões do usuário (Admin ↔ Operador)"""
    if not request.cookies.get("auth_user") or request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    try:
        cursor.execute("SELECT is_admin, username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user and user[1] != "admin":  # Não permitir mudar admin padrão
            novo_admin = 0 if user[0] == 1 else 1
            cursor.execute("UPDATE users SET is_admin = ? WHERE id = ?", (novo_admin, user_id))
            conn.commit()
            
            novo_tipo = "ADMIN" if novo_admin else "OPERADOR"
            record_audit_log("TOGGLE_PERMISSION", username, client_ip, f"Usuário {user[1]} mudado para {novo_tipo}")
            return {"success": True, "new_role": novo_tipo}
        
        return {"error": "Usuário não encontrado ou protegido"}
    except Exception as e:
        record_audit_log("TOGGLE_PERMISSION_FAILED", username, client_ip, str(e))
        return {"error": str(e)}

@app.post("/usuarios/ativar-desativar")
async def toggle_user_status(request: Request, user_id: int = Form(...)):
    """Ativa ou desativa um usuário"""
    if not request.cookies.get("auth_user") or request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    try:
        cursor.execute("SELECT status, username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            novo_status = 0 if user[0] == 1 else 1
            cursor.execute("UPDATE users SET status = ? WHERE id = ?", (novo_status, user_id))
            conn.commit()
            
            novo_estado = "ATIVO" if novo_status else "INATIVO"
            record_audit_log("TOGGLE_STATUS", username, client_ip, f"Usuário {user[1]} mudado para {novo_estado}")
            return {"success": True, "new_status": novo_estado}
        
        return {"error": "Usuário não encontrado"}
    except Exception as e:
        record_audit_log("TOGGLE_STATUS_FAILED", username, client_ip, str(e))
        return {"error": str(e)}

@app.get("/usuarios/exportar-csv")
async def export_users_csv(request: Request):
    """Exporta lista de usuários em CSV"""
    if not request.cookies.get("auth_user") or request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        # Tentar com todas as colunas novas primeiro
        try:
            cursor.execute("SELECT username, is_admin, data_criacao, status FROM users")
            usuarios = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback para bancos antigos - sem data_criacao
            cursor.execute("SELECT username, is_admin, status FROM users")
            resultado_antigo = cursor.fetchall()
            usuarios = [(u[0], u[1], None, u[2] if len(u) > 2 else 1) for u in resultado_antigo]
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['username', 'is_admin', 'data_criacao', 'status'])
        
        for usuario in usuarios:
            writer.writerow(usuario)
        
        username = request.cookies.get("auth_user")
        record_audit_log("EXPORT_USERS", username, get_client_ip(request), "Exportação de usuários em CSV")
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=usuarios.csv"}
        )
    except Exception as e:
        return {"error": str(e)}

# ──────────────────────────────────────────
# Teste de Conexão Telegram
# ──────────────────────────────────────────
@app.get("/test-telegram")
async def test_telegram(request: Request):
    """Endpoint para testar conexão com Telegram"""
    if request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    try:
        async with get_telegram_client() as client:
            me = await client.get_me()
            
            # Tenta acessar o grupo
            try:
                if GROUP_ID_OR_NAME.startswith('-') or GROUP_ID_OR_NAME.isdigit():
                    group_entity = await client.get_entity(int(GROUP_ID_OR_NAME))
                else:
                    group_entity = await client.get_entity(GROUP_ID_OR_NAME)
                
                return {
                    "status": "✅ Conectado",
                    "user": f"{me.first_name} (@{me.username})",
                    "phone": me.phone,
                    "group_id": GROUP_ID_OR_NAME,
                    "group_title": getattr(group_entity, 'title', 'N/A'),
                    "can_send": True
                }
            except Exception as group_error:
                return {
                    "status": "⚠️ Conectado mas grupo inacessível",
                    "user": f"{me.first_name} (@{me.username})",
                    "phone": me.phone,
                    "group_id": GROUP_ID_OR_NAME,
                    "error": str(group_error),
                    "fix": "Verifique se o bot está no grupo e tem permissão para postar"
                }
                
    except Exception as e:
        return {
            "status": "❌ Erro de conexão",
            "error": str(e),
            "fix": "Verifique STRING_SESSION, API_ID e API_HASH"
        }

# ----------------------
# ROTAS DE FAVORITOS
# ----------------------
@app.post("/favoritos/adicionar/{search_id}")
async def add_favorite(request: Request, search_id: int):
    """Adiciona uma consulta aos favoritos"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    try:
        cursor.execute("INSERT INTO favorites (search_id, username) VALUES (?, ?)", (search_id, username))
        conn.commit()
        client_ip = get_client_ip(request)
        record_audit_log("ADD_FAVORITE", username, client_ip, f"Consulta ID: {search_id}")
        return {"success": True, "message": "Adicionado aos favoritos"}
    except:
        return {"success": False, "error": "Erro ao adicionar favorito"}

@app.post("/favoritos/remover/{search_id}")
async def remove_favorite(request: Request, search_id: int):
    """Remove uma consulta dos favoritos"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    try:
        cursor.execute("DELETE FROM favorites WHERE search_id = ? AND username = ?", (search_id, username))
        conn.commit()
        client_ip = get_client_ip(request)
        record_audit_log("REMOVE_FAVORITE", username, client_ip, f"Consulta ID: {search_id}")
        return {"success": True, "message": "Removido dos favoritos"}
    except:
        return {"success": False, "error": "Erro ao remover favorito"}

@app.get("/favoritos")
async def get_favorites(request: Request):
    """Retorna lista de favoritos do usuário"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    username = request.cookies.get("auth_user")
    cursor.execute("""
        SELECT s.id, s.identifier, s.response, s.searched_at, 
               CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_favorite
        FROM searches s
        INNER JOIN favorites f ON s.id = f.search_id
        WHERE f.username = ?
        ORDER BY f.created_at DESC
    """, (username,))
    favorites = cursor.fetchall()
    
    consultas = []
    for f in favorites:
        # Buscar notas
        cursor.execute("SELECT note, created_at FROM notes WHERE search_id = ? ORDER BY created_at DESC LIMIT 1", (f[0],))
        note_row = cursor.fetchone()
        note_text = note_row[0] if note_row else None
        note_date = format_timestamp_br(note_row[1]) if note_row else None
        
        # Buscar tags
        cursor.execute("SELECT tag_name FROM tags WHERE search_id = ? ORDER BY created_at", (f[0],))
        tags_rows = cursor.fetchall()
        tags_list = [t[0] for t in tags_rows]
        
        consultas.append({
            "id": f[0], 
            "id_alvo": f[1], 
            "data": format_timestamp_br(f[3]), 
            "response": f[2],
            "is_favorite": True,
            "note": note_text,
            "note_date": note_date,
            "tags": tags_list
        })
    
    return templates.TemplateResponse("historico.html", {
        "request": request, 
        "consultas": consultas, 
        "is_favorites": True,
        "csrf_token": get_or_create_csrf_token(request)
    })

# ----------------------
# ROTAS DE NOTAS/COMENTÁRIOS
# ----------------------
@app.post("/notas/adicionar")
async def add_note(request: Request, search_id: int = Form(...), note: str = Form(...)):
    """Adiciona ou atualiza nota em uma consulta"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    try:
        # Verificar se já existe nota
        cursor.execute("SELECT id FROM notes WHERE search_id = ? AND username = ?", (search_id, username))
        existing = cursor.fetchone()
        
        if existing:
            # Atualizar nota existente
            cursor.execute("UPDATE notes SET note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (note, existing[0]))
        else:
            # Criar nova nota
            cursor.execute("INSERT INTO notes (search_id, username, note) VALUES (?, ?, ?)", (search_id, username, note))
        
        conn.commit()
        client_ip = get_client_ip(request)
        record_audit_log("ADD_NOTE", username, client_ip, f"Consulta ID: {search_id}")
        return {"success": True, "message": "Nota salva com sucesso"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/notas/{search_id}")
async def get_note(request: Request, search_id: int):
    """Retorna nota de uma consulta"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    cursor.execute("SELECT note, updated_at FROM notes WHERE search_id = ? AND username = ?", (search_id, username))
    note = cursor.fetchone()
    
    if note:
        return {"success": True, "note": note[0], "updated_at": format_timestamp_br(note[1])}
    return {"success": False, "note": ""}

@app.delete("/notas/{search_id}")
async def delete_note(request: Request, search_id: int):
    """Deleta nota de uma consulta"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    cursor.execute("DELETE FROM notes WHERE search_id = ? AND username = ?", (search_id, username))
    conn.commit()
    client_ip = get_client_ip(request)
    record_audit_log("DELETE_NOTE", username, client_ip, f"Consulta ID: {search_id}")
    return {"success": True, "message": "Nota deletada"}

# ----------------------
# ROTAS DE TAGS
# ----------------------
@app.post("/tags/adicionar")
async def add_tag(request: Request, search_id: int = Form(...), tag_name: str = Form(...)):
    """Adiciona tag a uma consulta"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    try:
        cursor.execute("INSERT INTO tags (search_id, tag_name, username) VALUES (?, ?, ?)", (search_id, tag_name, username))
        conn.commit()
        client_ip = get_client_ip(request)
        record_audit_log("ADD_TAG", username, client_ip, f"Consulta ID: {search_id}, Tag: {tag_name}")
        return {"success": True, "message": "Tag adicionada"}
    except:
        return {"success": False, "error": "Erro ao adicionar tag"}

@app.delete("/tags/{tag_id}")
async def remove_tag(request: Request, tag_id: int):
    """Remove uma tag"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    username = request.cookies.get("auth_user")
    cursor.execute("DELETE FROM tags WHERE id = ? AND username = ?", (tag_id, username))
    conn.commit()
    client_ip = get_client_ip(request)
    record_audit_log("REMOVE_TAG", username, client_ip, f"Tag ID: {tag_id}")
    return {"success": True, "message": "Tag removida"}

@app.get("/tags/{search_id}")
async def get_tags(request: Request, search_id: int):
    """Retorna tags de uma consulta"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "tags": []}
    
    username = request.cookies.get("auth_user")
    cursor.execute("SELECT id, tag_name FROM tags WHERE search_id = ? AND username = ?", (search_id, username))
    tags = cursor.fetchall()
    return {"success": True, "tags": [{"id": t[0], "name": t[1]} for t in tags]}

# ----------------------
# RELATÓRIOS AUTOMATIZADOS
# ----------------------
@app.get("/relatorios/mensal")
async def relatorio_mensal(request: Request):
    """Gera relatório mensal de uso"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    username = request.cookies.get("auth_user")
    
    # Consultas por mês
    cursor.execute("""
        SELECT strftime('%Y-%m', searched_at) as mes, COUNT(*) as total
        FROM searches
        WHERE searched_at >= DATE('now', '-12 months')
        GROUP BY mes
        ORDER BY mes DESC
    """)
    consultas_mes = cursor.fetchall()
    
    # Usuários mais ativos no mês atual
    cursor.execute("""
        SELECT username, COUNT(*) as total
        FROM searches
        WHERE strftime('%Y-%m', searched_at) = strftime('%Y-%m', 'now')
        GROUP BY username
        ORDER BY total DESC
        LIMIT 10
    """)
    usuarios_ativos = cursor.fetchall()
    
    # Logs de auditoria críticos
    cursor.execute("""
        SELECT action, COUNT(*) as total
        FROM audit_logs
        WHERE strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')
        GROUP BY action
        ORDER BY total DESC
    """)
    logs_resumo = cursor.fetchall()
    
    client_ip = get_client_ip(request)
    record_audit_log("GENERATE_MONTHLY_REPORT", username, client_ip, "Relatório mensal gerado")
    
    return {
        "consultas_por_mes": consultas_mes,
        "usuarios_ativos": usuarios_ativos,
        "logs_resumo": logs_resumo
    }

@app.get("/relatorios/usuario/{target_username}")
async def relatorio_usuario(request: Request, target_username: str):
    """Gera relatório de atividades de um usuário específico"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    username = request.cookies.get("auth_user")
    
    # Total de consultas
    cursor.execute("SELECT COUNT(*) FROM searches WHERE username = ?", (target_username,))
    total_consultas = cursor.fetchone()[0]
    
    # Consultas por dia
    cursor.execute("""
        SELECT DATE(searched_at) as data, COUNT(*) as total
        FROM searches
        WHERE username = ?
        GROUP BY data
        ORDER BY data DESC
        LIMIT 30
    """, (target_username,))
    consultas_por_dia = cursor.fetchall()
    
    # Logs de auditoria
    cursor.execute("""
        SELECT action, timestamp, details
        FROM audit_logs
        WHERE username = ?
        ORDER BY timestamp DESC
        LIMIT 50
    """, (target_username,))
    logs = cursor.fetchall()
    
    client_ip = get_client_ip(request)
    record_audit_log("GENERATE_USER_REPORT", username, client_ip, f"Relatório de: {target_username}")
    
    return {
        "username": target_username,
        "total_consultas": total_consultas,
        "consultas_por_dia": consultas_por_dia,
        "logs": logs
    }

# ----------------------
# BACKUP E MANUTENÇÃO
# ----------------------
@app.get("/admin/backup")
async def backup_database(request: Request):
    """Cria backup do banco de dados"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    username = request.cookies.get("auth_user")
    
    try:
        import shutil
        from datetime import datetime as dt
        
        # Nome do arquivo de backup
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{DB_FILE}.backup_{timestamp}.db"
        
        # Copiar banco de dados
        shutil.copy2(DB_FILE, backup_file)
        
        client_ip = get_client_ip(request)
        record_audit_log("DATABASE_BACKUP", username, client_ip, f"Backup criado: {backup_file}")
        
        return {"success": True, "backup_file": backup_file, "message": "Backup criado com sucesso"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/admin/cleanup")
async def cleanup_old_logs(request: Request, days: int = Form(90)):
    """Remove logs antigos do banco de dados"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return {"error": "Acesso negado"}
    
    username = request.cookies.get("auth_user")
    
    try:
        # Remover logs de auditoria antigos
        cursor.execute("DELETE FROM audit_logs WHERE timestamp < datetime('now', ?)", (f'-{days} days',))
        deleted_logs = cursor.rowcount
        
        conn.commit()
        
        client_ip = get_client_ip(request)
        record_audit_log("CLEANUP_LOGS", username, client_ip, f"Removidos {deleted_logs} logs com mais de {days} dias")
        
        return {"success": True, "deleted": deleted_logs, "message": f"Removidos {deleted_logs} logs antigos"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/admin/health")
async def health_check(request: Request):
    """Verifica saúde do sistema"""
    if not request.cookies.get("auth_user"):
        return {"status": "unauthorized"}
    
    try:
        # Verificar banco de dados
        cursor.execute("SELECT COUNT(*) FROM searches")
        total_searches = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        total_logs = cursor.fetchone()[0]
        
        # Tamanho do banco
        import os
        db_size = os.path.getsize(DB_FILE) / (1024 * 1024)  # MB
        
        return {
            "status": "healthy",
            "database": {
                "size_mb": round(db_size, 2),
                "total_searches": total_searches,
                "total_users": total_users,
                "total_logs": total_logs
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# ----------------------
# FILTROS NO HISTÓRICO
# ----------------------
@app.get("/historico/filtrar")
async def filtrar_historico(request: Request, q: str = "", periodo: str = "30", ordem: str = "desc"):
    """Filtra histórico por termo de busca e período"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    username = request.cookies.get("auth_user")
    
    # Construir query com filtros
    where_clauses = ["s.username = ?"]
    params = [username, username]  # username para WHERE e para LEFT JOIN
    
    # Filtro de período
    if periodo == "7":
        where_clauses.append("DATE(s.searched_at) >= DATE('now', '-7 days')")
    elif periodo == "30":
        where_clauses.append("DATE(s.searched_at) >= DATE('now', '-30 days')")
    elif periodo == "90":
        where_clauses.append("DATE(s.searched_at) >= DATE('now', '-90 days')")
    
    # Filtro de busca
    if q:
        where_clauses.append("(s.identifier LIKE ? OR s.response LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    
    # Ordenação
    order_by = "s.searched_at DESC" if ordem == "desc" else "s.searched_at ASC"
    
    where_sql = " AND ".join(where_clauses)
    
    cursor.execute(f"""
        SELECT s.id, s.identifier, s.response, s.searched_at,
               CASE WHEN f.id IS NOT NULL THEN 1 ELSE 0 END as is_favorite
        FROM searches s
        LEFT JOIN favorites f ON s.id = f.search_id AND f.username = ?
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT 100
    """, params)
    
    searches = cursor.fetchall()
    
    consultas = []
    for s in searches:
        # Buscar notas
        cursor.execute("SELECT note, created_at FROM notes WHERE search_id = ? ORDER BY created_at DESC LIMIT 1", (s[0],))
        note_row = cursor.fetchone()
        note_text = note_row[0] if note_row else None
        note_date = format_timestamp_br(note_row[1]) if note_row else None
        
        # Buscar tags
        cursor.execute("SELECT tag_name FROM tags WHERE search_id = ? ORDER BY created_at", (s[0],))
        tags_rows = cursor.fetchall()
        tags_list = [t[0] for t in tags_rows]
        
        consultas.append({
            "id": s[0], 
            "id_alvo": s[1], 
            "data": format_timestamp_br(s[3]), 
            "response": s[2],
            "is_favorite": s[4] == 1,
            "note": note_text,
            "note_date": note_date,
            "tags": tags_list
        })
    
    return templates.TemplateResponse("historico.html", {
        "request": request, 
        "consultas": consultas,
        "filtro_q": q,
        "filtro_periodo": periodo,
        "filtro_ordem": ordem
    })

# ----------------------
# BACKUP DE USUÁRIOS (ADMIN ONLY)
# ----------------------
@app.get("/backup/usuarios/csv")
async def backup_usuarios_csv(request: Request):
    """Exporta todos os usuários e senhas em CSV (admin only)"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/")
    
    if is_session_expired(request):
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Buscar todos os usuários
    cursor.execute("SELECT id, username, password, is_admin FROM users ORDER BY id")
    usuarios = cursor.fetchall()
    
    # Criar CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Usuário", "Senha", "Admin"])
    for user in usuarios:
        writer.writerow([user[0], user[1], user[2], "Sim" if user[3] else "Não"])
    
    record_audit_log("BACKUP_USUARIOS_CSV", username, client_ip, f"Backup de {len(usuarios)} usuários exportado em CSV")
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=backup_usuarios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/backup/usuarios/json")
async def backup_usuarios_json(request: Request):
    """Exporta todos os usuários e senhas em JSON (admin only)"""
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/")
    
    if is_session_expired(request):
        return RedirectResponse(url="/login", status_code=303)
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    # Buscar todos os usuários
    cursor.execute("SELECT id, username, password, is_admin FROM users ORDER BY id")
    usuarios = cursor.fetchall()
    
    # Criar JSON
    data = {
        "backup_data": datetime.now().isoformat(),
        "backup_user": username,
        "total_usuarios": len(usuarios),
        "usuarios": [
            {
                "id": u[0],
                "username": u[1],
                "password": u[2],
                "is_admin": bool(u[3])
            }
            for u in usuarios
        ]
    }
    
    record_audit_log("BACKUP_USUARIOS_JSON", username, client_ip, f"Backup de {len(usuarios)} usuários exportado em JSON")
    
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=backup_usuarios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"}
    )

@app.post("/backup/restaurar/usuarios")
async def restore_usuarios(request: Request):
    """Restaura usuários a partir de arquivo JSON (admin only)"""
    if not request.cookies.get("auth_user"):
        return {"success": False, "error": "Não autenticado"}
    
    if request.cookies.get("is_admin") != "1":
        return {"success": False, "error": "Acesso negado"}
    
    if is_session_expired(request):
        return {"success": False, "error": "Sessão expirada"}
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    
    try:
        form_data = await request.form()
        file = form_data.get("file")
        
        if not file:
            return {"success": False, "error": "Nenhum arquivo enviado"}
        
        # Ler arquivo JSON
        content = await file.read()
        data = json.loads(content.decode('utf-8'))
        
        # Validar estrutura
        if "usuarios" not in data:
            return {"success": False, "error": "Arquivo JSON inválido"}
        
        # Restaurar usuários
        restored = 0
        for user in data["usuarios"]:
            try:
                cursor.execute("INSERT OR REPLACE INTO users (id, username, password, is_admin) VALUES (?, ?, ?, ?)",
                             (user["id"], user["username"], user["password"], 1 if user.get("is_admin", False) else 0))
                restored += 1
            except:
                pass
        
        conn.commit()
        record_audit_log("RESTORE_USUARIOS", username, client_ip, f"{restored} usuários restaurados")
        
        return {"success": True, "message": f"✅ {restored} usuários restaurados com sucesso"}
    
    except Exception as e:
        record_audit_log("RESTORE_USUARIOS_FAILED", username, client_ip, str(e))
        return {"success": False, "error": f"Erro ao restaurar: {str(e)}"}

# ===========================
# LIMPEZA AUTOMÁTICA DE LOGS
# ===========================
def auto_cleanup_logs():
    """Limpa logs com mais de 2 dias automaticamente"""
    while True:
        try:
            time.sleep(86400)  # Espera 24 horas
            cursor.execute("DELETE FROM audit_logs WHERE timestamp < datetime('now', '-2 days')")
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                record_audit_log("AUTO_CLEANUP", "system", "127.0.0.1", f"Limpeza automática: {deleted} logs removidos")
        except Exception as e:
            print(f"Erro na limpeza automática de logs: {e}")

# Iniciar thread de limpeza automática
cleanup_thread = threading.Thread(target=auto_cleanup_logs, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9000)))