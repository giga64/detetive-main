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
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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
    
    csrf_token = get_or_create_csrf_token(request)
    return templates.TemplateResponse("modern-form.html", {"request": request, "csrf_token": csrf_token})

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
        
        return templates.TemplateResponse("modern-result.html", {
            "request": request, 
            "mensagem": identificador, 
            "resultado": resultado, 
            "identifier": identificador
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
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches WHERE username = ? ORDER BY searched_at DESC LIMIT 100", (username,))
    searches = cursor.fetchall()
    consultas = [{"id": s[0], "id_alvo": s[1], "data": format_timestamp_br(s[3]), "response": s[2]} for s in searches]
    return templates.TemplateResponse("historico.html", {"request": request, "consultas": consultas})

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9000)))