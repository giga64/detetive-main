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

✅ Busca por CPF, CNPJ, Placa Veicular, Nome e **OAB**  
✅ **Visualização de ficha OAB completa** (imagem direta do site oficial)  
✅ Histórico de buscas com filtros e tags  
✅ Gerenciamento de usuários/agentes  
✅ Integração com Telegram (consultas assíncronas)  
✅ Interface cyberpunk/detetive moderna  
✅ Sistema otimizado (sem dependências pesadas de OCR)

---

## ⚡ Notas Importantes

### Busca OAB - Solução Otimizada
- **Sem OCR**: Sistema busca diretamente a imagem da ficha OAB do site oficial (https://cna.oab.org.br)
- **Performance**: Consultas rápidas (~3-5s) sem downloads pesados
- **Timeout**: 20 segundos por busca OAB
- **Exibição**: Imagem centralizada e clicável para abrir em tamanho original

### Segurança
- Senhas criptografadas com bcrypt
- Proteção CSRF em todos os formulários
- Logs de auditoria completos
- Controle de acesso por nível (admin/agente)

### Banco de Dados
- SQLite com 8 tabelas principais
- Historico completo de pesquisas
- Sistema de favoritos e anotações
- Logs de auditoria detalhados

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

## � Docker Compose (Development)

**Pré-requisito:** Docker e Docker Compose instalados

```bash
# 1. Criar arquivo .env com variáveis
cat > .env << EOF
TELEGRAM_API_ID=seu_id
TELEGRAM_API_HASH=seu_hash
TELEGRAM_GROUP_ID=seu_grupo
STRING_SESSION=sua_session
ENABLE_OAB_OCR=true
PORT=8000
EOF

# 2. Iniciar todos os serviços (web + Redis + Celery)
docker-compose up -d

# 3. Verificar status
docker-compose ps

# 4. Ver logs
docker-compose logs -f web

# 5. Parar everything
docker-compose down
```

Acesse: http://localhost:8000/login

---

## 📁 Estrutura de Arquivos e Assets

### Diretórios

```
detetive-main/
├── app.py                    # Aplicação FastAPI principal
├── requirements.txt          # Dependências Python
├── docker-compose.yml        # Orquestração de containers
├── Dockerfile                # Build da web app
├── Dockerfile.celery         # Build dos workers Celery
│
├── generate_session.py       # Gerador de STRING_SESSION (Telegram)
├── cache_manager.py          # Gerenciador de cache (Redis)
├── job_queue.py              # Fila de tarefas (Celery)
├── sse_streaming.py          # Streaming SSE para consultas
│
├── templates/                # Templates HTML (Jinja2)
│   ├── login.html           # Tela de login
│   ├── modern-form.html     # Formulário de busca
│   ├── modern-result.html   # Resultados isolados
│   ├── historico.html       # Histórico com favoritos/tags
│   ├── usuarios.html        # Painel admin de usuários
│   ├── admin_dashboard.html # Dashboard administrativo
│   ├── admin_logs.html      # Logs de auditoria
│   └── ...outros
│
└── static/                   # Assets estáticos (CSS, JS, imagens)
    ├── favicon.png          # Ícone da aplicação
    ├── design-system.css    # Sistema de design (cores, componentes)
    ├── design-overrides.css # Overrides e animações
    ├── microinteractions.js # Feedback visual (ripple, toast, etc)
    ├── cursor-interactive.js # Cursor customizado
    └── loading-narrative.js  # Animações de loading detetivescas
```

### Assets Estáticos

- **`design-system.css`**: Root colors, typography, buttons, cards, badges, alerts, modals
- **`design-overrides.css`**: Scrollbar, selection, animations, utilities, responsive
- **`microinteractions.js`**: Ripple effects, hover glow, tooltips, copy-to-clipboard
- **`cursor-interactive.js`**: Cursor customizado com trail effect
- **`loading-narrative.js`**: Loading overlay com mensagens narrativas

Todos gerados automaticamente - **não modificar manualmente**.

---

## 🚨 Troubleshooting

**Erro: "Directory '/app/static' does not exist"**
- ✅ Resolvido: Diretório é criado automaticamente pelo app.py
- Se ainda persistir, rode: `mkdir -p static`

**Erro: "404 Not Found" para assets (CSS/JS)**
- ✅ Resolvido: Assets criados em `/static/design-*.css` e `*-interactive.js`
- Verifique: `ls -la static/` deve listar: `design-system.css`, `design-overrides.css`, `microinteractions.js`, `cursor-interactive.js`, `loading-narrative.js`, `favicon.png`

**Erro: "Sessão Telegram não autorizada"**
- ✅ Verifique `.env`: `STRING_SESSION` está preenchida?
- Regenere a sessão: `python generate_session.py`

**Aplicação em crash**
- Verifique logs: `docker-compose logs web` (ou `uvicorn` se rodando localmente)
- Confirme: `TELEGRAM_API_ID` e `TELEGRAM_API_HASH` estão corretos em `.env`
- Teste banco de dados: `ls -la *.db` deve listar `detetive.db`, `usuarios.db`, `history.db`

**Redis não conecta**
- Teste: `redis-cli ping` deve retornar `PONG`
- Se usar Docker: `docker-compose logs redis`

**Celery worker não processa tarefas**
- Verifique: `docker-compose logs celery-worker`
- Confirme que Redis está saudável: `docker-compose ps` → redis health = healthy

---

## 🔐 Segurança

✅ **Implementadas:**
- Senhas criptografadas com **bcrypt** (rounds=12)
- Proteção **CSRF** em todos os formulários (tokens com 1h TTL)
- Autenticação server-side (não confia em cookies de client)
- Logs de auditoria para todas as ações sensíveis
- Rate limiting: 5 tentativas login/IP, 10 consultas/minuto por usuário
- Isolamento de dados: usuários veem só seu próprio histórico (admin vê tudo)

⚠️ **TODO (produção):**
- Session signing/validation (cookies devem ser assinadas)
- HTTPS obrigatório em produção
- WAF (Web Application Firewall) em produção
- Política de retenção de logs de auditoria

---

## 📦 Stack Técnico

| Camada | Tecnologia |
|--------|------------|
| **Frontend** | HTML5 + CSS3 + Vanilla JS (Jinja2 templates) |
| **Backend** | FastAPI + Uvicorn (async Python) |
| **Telegram** | Telethon (sessão StringSession) |
| **Cache** | Redis (via cache_manager.py) |
| **Queue** | Celery (job_queue.py) |
| **Database** | SQLite (3 databases: detetive, usuarios, history) |
| **Deploy** | Docker Compose / Railway |

---

## 🔗 Links Úteis

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Telethon Documentation](https://docs.telethon.dev)
- [Railway Docs](https://docs.railway.app)
- [Docker Compose Docs](https://docs.docker.com/compose)

---

## 📝 Contribuir

1. Fork o repositório
2. Crie uma branch: `git checkout -b feature/sua-feature`
3. Commit: `git commit -am 'Add: sua-feature'`
4. Push: `git push origin feature/sua-feature`
5. Open a Pull Request

---

**Desenvolvido com ❤️ para investigações digitais.**
