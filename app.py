import os
import re
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel
from tenacity import retry, stop_after_attempt, wait_exponential

# ----------------------
# Configurações de diretórios
# ----------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

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
    searched_at  DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

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

# Criar admin padrão se não existir (Usuário: admin | Senha: admin123)
cursor.execute("INSERT OR IGNORE INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
               ("admin", "admin123", 1))
conn.commit()

# ----------------------
# Configuração Telethon (Telegram)
# ----------------------
API_ID = int(os.environ.get("TELEGRAM_API_ID", "17993467"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "684fdc620ac8ace6bc1ee15c219744a3")
SESSION_FILE = os.environ.get("SESSION_FILE", os.path.join(BASE_DIR, "bot_session_novo.session"))
GROUP_ID_OR_NAME = os.environ.get("TELEGRAM_GROUP_ID", "2874013146")

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
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized(): raise Exception("Não autorizado")
        yield client
    finally:
        await client.disconnect()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def consulta_telegram(cmd: str) -> str:
    async with telegram_semaphore:
        async with get_telegram_client() as client:
            response_text = None
            response_received = asyncio.Event()
            async def handler(event):
                nonlocal response_text
                response_text = re.sub(r"🔛\s*BY:\s*@Skynet08Robot", "", event.raw_text, flags=re.IGNORECASE)
                response_received.set()
            
            group_entity = PeerChannel(int(GROUP_ID_OR_NAME))
            client.add_event_handler(handler, events.NewMessage(chats=group_entity))
            await client.send_message(group_entity, cmd)
            try:
                await asyncio.wait_for(response_received.wait(), timeout=45)
                return response_text or "❌ Vazio"
            except:
                return "❌ Timeout"

# ----------------------
# Rotas de Autenticação
# ----------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    cursor.execute("SELECT is_admin FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    if user:
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="auth_user", value=username)
        response.set_cookie(key="is_admin", value=str(user[0]))
        return response
    return templates.TemplateResponse("login.html", {"request": request, "erro": "ACESSO NEGADO"})

# ----------------------
# Rotas do Sistema
# ----------------------
@app.get("/", response_class=HTMLResponse)
def form(request: Request):
    if not request.cookies.get("auth_user"): return RedirectResponse(url="/login")
    return templates.TemplateResponse("modern-form.html", {"request": request})

@app.post("/consulta", response_class=HTMLResponse)
async def do_consulta(request: Request):
    if not request.cookies.get("auth_user"): return RedirectResponse(url="/login")
    form_data = await request.form()
    identificador = str(form_data.get("identificador", "")).strip()
    tipo_manual = str(form_data.get("tipo", "")).strip().lower()
    tipo = tipo_manual if (tipo_manual and tipo_manual != "auto") else detect_tipo(identificador)
    
    if tipo == 'cpf': cmd = f"/cpf3 {normalize(identificador)}"
    elif tipo == 'cnpj': cmd = f"/cnpj3 {normalize(identificador)}"
    elif tipo == 'placa': cmd = f"/placa {normalize_placa(identificador)}"
    elif tipo == 'nome': cmd = f"/nome {identificador}"
    else: return templates.TemplateResponse("modern-form.html", {"request": request, "erro": "Tipo desconhecido"})
    
    resultado = await consulta_telegram(cmd)
    return templates.TemplateResponse("modern-result.html", {"request": request, "mensagem": identificador, "resultado": resultado, "identifier": identificador})

@app.get("/historico", response_class=HTMLResponse)
def historico(request: Request):
    if not request.cookies.get("auth_user"): return RedirectResponse(url="/login")
    return templates.TemplateResponse("historico.html", {"request": request})

# ----------------------
# Gestão de Usuários
# ----------------------
@app.get("/usuarios", response_class=HTMLResponse)
async def list_users(request: Request):
    if request.cookies.get("is_admin") != "1": return RedirectResponse(url="/")
    cursor.execute("SELECT id, username, is_admin FROM users")
    return templates.TemplateResponse("usuarios.html", {"request": request, "users": cursor.fetchall()})

@app.post("/usuarios/novo")
async def create_user(request: Request, new_user: str = Form(...), new_pass: str = Form(...), admin: str = Form(None)):
    if request.cookies.get("is_admin") == "1":
        try:
            cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", (new_user, new_pass, 1 if admin else 0))
            conn.commit()
        except: pass
    return RedirectResponse(url="/usuarios", status_code=303)

@app.get("/usuarios/deletar/{user_id}")
async def delete_user(request: Request, user_id: int):
    if request.cookies.get("is_admin") == "1":
        cursor.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))
        conn.commit()
    return RedirectResponse(url="/usuarios", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 9000)))