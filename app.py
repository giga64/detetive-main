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

# Criar admin padrão se não existir (Usuário: admin | Senha: admin6464)
cursor.execute("INSERT OR IGNORE INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
               ("admin", "admin6464", 1))
# Atualizar senha do admin caso já exista
cursor.execute("UPDATE users SET password = ? WHERE username = ?", ("admin6464", "admin"))
conn.commit()

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
    if not request.cookies.get("auth_user"): 
        return RedirectResponse(url="/login")
    
    form_data = await request.form()
    identificador = str(form_data.get("identificador", "")).strip()
    tipo_manual = str(form_data.get("tipo", "")).strip().lower()
    
    if not identificador:
        return templates.TemplateResponse("modern-form.html", {
            "request": request, 
            "erro": "Digite um identificador válido"
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
                cursor.execute(
                    "INSERT INTO searches (identifier, response) VALUES (?, ?)", 
                    (identificador, resultado)
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
        return templates.TemplateResponse("modern-form.html", {
            "request": request,
            "erro": f"Erro ao processar consulta: {str(e)}"
        })

@app.get("/historico", response_class=HTMLResponse)
def historico(request: Request):
    if not request.cookies.get("auth_user"): return RedirectResponse(url="/login")
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches ORDER BY searched_at DESC LIMIT 100")
    searches = cursor.fetchall()
    consultas = [{"id_alvo": s[1], "data": s[3], "response": s[2]} for s in searches]
    return templates.TemplateResponse("historico.html", {"request": request, "consultas": consultas})

@app.get("/api/historico")
def api_historico(request: Request):
    if not request.cookies.get("auth_user"): raise HTTPException(status_code=401, detail="Não autorizado")
    cursor.execute("SELECT id, identifier, response, searched_at FROM searches ORDER BY searched_at DESC LIMIT 100")
    searches = cursor.fetchall()
    return [{"id": s[0], "identifier": s[1], "response": s[2], "searched_at": s[3]} for s in searches]

# ----------------------
# Gestão de Usuários (Apenas Admin)
# ----------------------
@app.get("/usuarios", response_class=HTMLResponse)
async def list_users(request: Request):
    # Apenas admin pode gerenciar usuários
    if request.cookies.get("is_admin") != "1": 
        return RedirectResponse(url="/")
    cursor.execute("SELECT id, username, is_admin FROM users")
    return templates.TemplateResponse("usuarios.html", {
        "request": request, 
        "usuarios": cursor.fetchall()
    })

@app.post("/usuarios/novo")
async def create_user(request: Request, new_user: str = Form(...), new_pass: str = Form(...), admin: str = Form(None)):
    # Apenas admin pode criar usuários
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/", status_code=303)
    try:
        cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", 
                     (new_user, new_pass, 1 if admin else 0))
        conn.commit()
    except: 
        pass
    return RedirectResponse(url="/usuarios", status_code=303)

@app.get("/usuarios/deletar/{user_id}")
async def delete_user(request: Request, user_id: int):
    # Apenas admin pode deletar usuários (exceto outros admins)
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/", status_code=303)
    cursor.execute("DELETE FROM users WHERE id = ? AND is_admin = 0", (user_id,))
    conn.commit()
    return RedirectResponse(url="/usuarios", status_code=303)

@app.post("/usuarios/alterar-senha")
async def change_password(request: Request, user_id: int = Form(...), new_pass: str = Form(...)):
    # Apenas admin pode alterar senhas de usuários
    if request.cookies.get("is_admin") != "1":
        return RedirectResponse(url="/", status_code=303)
    try:
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_pass, user_id))
        conn.commit()
    except:
        pass
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