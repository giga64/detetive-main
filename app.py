import os
import re
import asyncio
import sqlite3
import csv
import json
import uuid
import secrets
from io import StringIO
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient, events
from telethon.sessions import StringSession

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
    is_admin INTEGER DEFAULT 0
)
""")
conn.commit()

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
LOGIN_ATTEMPT_WINDOW = 15 * 60  # 15 minutos em segundos

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

print(f"🔧 Configuração Telegram:")
print(f"   API_ID: {API_ID}")
print(f"   GROUP_ID: {GROUP_ID_OR_NAME}")

# Suporte a STRING_SESSION ou arquivo de sessão
STRING_SESSION_ENV = os.environ.get("STRING_SESSION", None)
if STRING_SESSION_ENV:
    # Remover espaços, quebras de linha e caracteres extras
    STRING_SESSION_ENV = STRING_SESSION_ENV.strip()
    print(f"   Usando STRING_SESSION")
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
        session = StringSession(STRING_SESSION_ENV)
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
                    response_text = re.sub(r"🔛\s*BY:\s*@Skynet08Robot", "", event.raw_text, flags=re.IGNORECASE)
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

def parse_resultado_consulta(resultado_texto: str) -> dict:
    """Faz parsing do resultado textual e retorna dados estruturados"""
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
        "risco": None
    }
    
    # Helper para extrair valor após label
    def get_value(label, text=resultado_texto):
        match = re.search(rf'{label}:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        return match.group(1).strip() if match else None
    
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
                WHERE username IS NOT NULL
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
        return templates.TemplateResponse("login.html", {
            "request": request,
            "erro": "Sistema temporariamente indisponível. Tente novamente mais tarde."
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
    cursor.execute("SELECT is_admin FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    
    if user:
        # Login bem-sucedido
        record_audit_log("LOGIN_SUCCESS", username, client_ip, "")
        response = RedirectResponse(url="/", status_code=303)
        auth_time = (datetime.now() + timedelta(seconds=SESSION_TIMEOUT)).isoformat()
        response.set_cookie(key="auth_user", value=username, max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
        response.set_cookie(key="is_admin", value=str(user[0]), max_age=SESSION_TIMEOUT, httponly=True, samesite="Lax")
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
    return response

# ----------------------
# Rotas do Sistema
# ----------------------
@app.get("/", response_class=HTMLResponse)
def form(request: Request):
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
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
    
    # Top 10 usuários
    cursor.execute("""
        SELECT username, COUNT(*) as total
        FROM searches
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
    if not request.cookies.get("auth_user"): 
        return RedirectResponse(url="/login")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
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
        
        # Salvar no histórico apenas se não for erro
        if not resultado.startswith("❌"):
            try:
                username = request.cookies.get("auth_user")
                cursor.execute(
                    "INSERT INTO searches (identifier, response, username) VALUES (?, ?, ?)", 
                    (identificador, resultado, username)
                )
                conn.commit()
            except:
                pass
        
        # Parser do resultado para dados estruturados
        dados_estruturados = parse_resultado_consulta(resultado) if not resultado.startswith("❌") else None
        
        return templates.TemplateResponse("modern-result.html", {
            "request": request, 
            "mensagem": identificador, 
            "resultado": resultado, 
            "dados": dados_estruturados,
            "identifier": identificador,
            "csrf_token": get_or_create_csrf_token(request)
        })
    except Exception as e:
        username = request.cookies.get("auth_user", "unknown")
        client_ip = get_client_ip(request)
        record_audit_log("QUERY_ERROR", username, client_ip, str(e))
        return templates.TemplateResponse("modern-form.html", {
            "request": request,
            "erro": "Erro ao processar consulta. Tente novamente mais tarde."
        })

@app.get("/historico", response_class=HTMLResponse)
def historico(request: Request):
    if not request.cookies.get("auth_user"): 
        return RedirectResponse(url="/login")
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
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
    
    return templates.TemplateResponse("historico.html", {"request": request, "consultas": consultas})

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
    
    # Buscar todas as consultas do usuário
    cursor.execute(
        "SELECT id, identifier, response FROM searches WHERE username = ?",
        (username,)
    )
    searches = cursor.fetchall()
    
    resultados = []
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por telefone
        if dados["telefones"]:
            for telefone in dados["telefones"]:
                telefone_clean = ''.join(filter(str.isdigit, telefone))
                if telefone_clean == phone_clean:
                    resultados.append({
                        "identifier": identifier,
                        "nome": dados["dados_pessoais"].get("nome", "N/A"),
                        "cpf": dados["dados_pessoais"].get("cpf", "N/A"),
                        "tipo": "Proprietário"
                    })
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
    
    # Buscar todas as consultas do usuário
    cursor.execute(
        "SELECT id, identifier, response FROM searches WHERE username = ?",
        (username,)
    )
    searches = cursor.fetchall()
    
    resultados = []
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por email
        if dados["emails"]:
            for mail in dados["emails"]:
                if mail.lower() == email_lower:
                    resultados.append({
                        "identifier": identifier,
                        "nome": dados["dados_pessoais"].get("nome", "N/A"),
                        "cpf": dados["dados_pessoais"].get("cpf", "N/A"),
                        "tipo": "Proprietário"
                    })
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
    
    # Buscar todas as consultas do usuário
    cursor.execute(
        "SELECT id, identifier, response FROM searches WHERE username = ?",
        (username,)
    )
    searches = cursor.fetchall()
    
    resultados = []
    for search_id, identifier, response in searches:
        # Parser do resultado
        dados = parse_resultado_consulta(response)
        
        # Procurar por endereço (busca parcial)
        if dados["enderecos"]:
            for endereco in dados["enderecos"]:
                endereco_norm = endereco.lower().strip()
                # Busca por similaridade (se contém palavras-chave)
                if address_norm in endereco_norm or endereco_norm in address_norm:
                    resultados.append({
                        "identifier": identifier,
                        "nome": dados["dados_pessoais"].get("nome", "N/A"),
                        "cpf": dados["dados_pessoais"].get("cpf", "N/A"),
                        "endereco": endereco,
                        "tipo": "Residente"
                    })
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
async def limpar_historico(request: Request):
    if not request.cookies.get("auth_user"):
        return RedirectResponse(url="/login", status_code=303)
    
    # Verificar expiração de sessão
    if is_session_expired(request):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("auth_user")
        response.delete_cookie("is_admin")
        response.delete_cookie("auth_time")
        return response
    
    username = request.cookies.get("auth_user")
    client_ip = get_client_ip(request)
    cursor.execute("DELETE FROM searches WHERE username = ?", (username,))
    conn.commit()
    record_audit_log("CLEAR_HISTORY", username, client_ip, "")
    return RedirectResponse(url="/historico", status_code=303)

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
    
    cursor.execute("SELECT id, username, is_admin FROM users")
    csrf_token = get_or_create_csrf_token(request)
    return templates.TemplateResponse("usuarios.html", {
        "request": request, 
        "usuarios": cursor.fetchall(),
        "csrf_token": csrf_token
    })

@app.post("/usuarios/novo")
async def create_user(request: Request, new_user: str = Form(...), new_pass: str = Form(...), admin: str = Form(None), csrf_token: str = Form(...)):
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
    
    try:
        cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                     (new_user, new_pass, 1 if admin else 0))
        conn.commit()
        record_audit_log("CREATE_USER", username, client_ip, f"Novo usuário: {new_user}, admin: {bool(admin)}")
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
        record_audit_log("INVALID_CSRF", username, client_ip, "Tentativa de alterar senha com CSRF inválido")
        return RedirectResponse(url="/usuarios", status_code=303)
    
    try:
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_pass, user_id))
        conn.commit()
        record_audit_log("CHANGE_PASSWORD", username, client_ip, f"Senha alterada para ID: {user_id}")
    except:
        record_audit_log("CHANGE_PASSWORD_FAILED", username, client_ip, f"Falha ao alterar senha para ID: {user_id}")
    
    return RedirectResponse(url="/usuarios", status_code=303)

# ----------------------
# Teste de Conexão Telegram
# ----------------------
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
    
    return templates.TemplateResponse("historico.html", {"request": request, "consultas": consultas, "is_favorites": True})

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9000)))