# 🔍 OneSeek - Investigações Digitais

Deploy de um sistema de investigação digital com Telethon + FastAPI no Railway.

## 🚀 Deploy Rápido no Railway

### Pré-requisitos
- Conta no [Railway.app](https://railway.app)
- Repositório GitHub com este projeto
- Suas credenciais Telegram (`API_ID` e `API_HASH`)

### Passo 1: Conectar o Repositório GitHub
1. Acesse https://railway.app
2. New Project → Deploy from GitHub
3. Selecione seu repositório e branch

### Passo 2: Configurar Variáveis de Ambiente
No painel Railway → Variables, adicione:

| Variável | Valor | Descrição |
|----------|-------|-----------|
| `TELEGRAM_API_ID` | `seu_id` | ID da API Telegram |
| `TELEGRAM_API_HASH` | `seu_hash` | Hash da API Telegram |
| `TELEGRAM_GROUP_ID` | `id_grupo` | ID do grupo Telegram para onde enviar comandos |
| `STRING_SESSION` | *(veja passo 3)* | Sessão Telegram (STRING) |
| `ENABLE_OAB_OCR` | `true` | **RECOMENDADO:** `true` para exibir imagem completa da ficha OAB. Use `false` para apenas dados básicos (mais rápido) |

### Passo 3: Gerar STRING_SESSION (IMPORTANTE)

**Localmente:**
```bash
pip install -r requirements.txt
python generate_session.py
```

Siga as instruções, faça login no Telegram e copie a string gerada.

**No Railroad:**
1. Em Variables, adicione: `STRING_SESSION` = `<string copiada>`
2. Configure também o volume persistente em `/data`

### Passo 4: Build & Start Commands
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`

Obs: Se quiser usar gunicorn, altere para:
```
gunicorn -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:$PORT
```

### Passo 5: Deploy
Clique em **Deploy** e aguarde o build.

---

## 🔐 Credenciais Padrão

- **Usuário**: `admin`
- **Senha**: `admin123`

Altere após primeiro login!

---

## 📋 Funcionalidades

✅ Busca por CPF, CNPJ, Placa Veicular e Nome  
✅ Histórico de buscas  
✅ Gerenciamento de usuários/agentes  
✅ Integração com Telegram  
✅ Interface cyberpunk/detetive  

---

## 🛠️ Desenvolvimento Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Gerar sessão Telegram (local)
python generate_session.py

# Rodar a aplicação
uvicorn app:app --reload
```

Acesse: http://localhost:8000/login

---

## 🚨 Troubleshooting

**Erro: "Sessão Telegram não autorizada"**
- Verifique se `STRING_SESSION` está definida corretamente
- Regenere a sessão com `generate_session.py` se expirou

**Erro: "Directory '/app/static' does not exist"**
- Os diretórios são criados automaticamente. Se persistir, verifique se o code foi atualizado no Railway.

**Aplicação em crash**
- Verifique os logs: Railway → Logs
- Confirme que `TELEGRAM_API_ID` e `TELEGRAM_API_HASH` estão corretos

---

## 📦 Stack Técnico

- **Backend**: FastAPI + Uvicorn
- **Telegram**: Telethon (assíncrono)
- **Banco de Dados**: SQLite
- **Frontend**: HTML + CSS (Jinja2)
- **Deploy**: Railway

---

## 📝 Estrutura

```
detetive-main/
├── app.py                 # Aplicação principal
├── generate_session.py    # Script para gerar STRING_SESSION
├── requirements.txt       # Dependências Python
├── templates/             # Templates HTML
│   ├── login.html
│   ├── modern-form.html
│   ├── modern-result.html
│   ├── historico.html
│   └── usuarios.html
└── static/               # Arquivos estáticos (CSS, JS)
```

---

## 🔗 Links úteis

- [Telethon Docs](https://docs.telethon.dev)
- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Railway Docs](https://docs.railway.app)

---

**Desenvolvido com ❤️ para investigações digitais.**
