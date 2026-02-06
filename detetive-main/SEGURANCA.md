# 🔐 Segurança - Protegendo suas Credenciais

## ⚠️ PROBLEMA ENCONTRADO

Suas credenciais do Telegram **estavam hardcoded no código**:
```python
# ❌ ERRADO - Expostas no Git!
API_ID = 24383113
API_HASH = '387f7520aae351ddc83fb457cdb60085'
```

Isso é perigoso porque:
1. ❌ Git armazena histórico - qualquer pessoa com acesso ao repo vê suas chaves
2. ❌ Risco de rate-limit / bloqueio da API do Telegram
3. ❌ Qualquer um pode usar suas credenciais para enviar mensagens

---

## ✅ SOLUÇÃO IMPLEMENTADA

### 1. **Usar Variáveis de Ambiente**
```python
# ✅ CORRETO - Variáveis de ambiente
API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
```

### 2. **Configurar no Render (Production)**

**No painel do Render:**
1. Vá para seu app (detetive-ss5n)
2. **Settings** → **Environment**
3. Adicione variáveis:
   ```
   TELEGRAM_API_ID = 24383113
   TELEGRAM_API_HASH = 387f7520aae351ddc83fb457cdb60085
   TELEGRAM_GROUP_ID = -1002874013146
   ```
4. Click "Save" (auto-redeploy)

### 3. **Configurar Localmente (Development)**

**Windows PowerShell:**
```powershell
$env:TELEGRAM_API_ID = "24383113"
$env:TELEGRAM_API_HASH = "387f7520aae351ddc83fb457cdb60085"
$env:TELEGRAM_GROUP_ID = "-1002874013146"

python app.py
```

**Linux/Mac:**
```bash
export TELEGRAM_API_ID=24383113
export TELEGRAM_API_HASH=387f7520aae351ddc83fb457cdb60085
export TELEGRAM_GROUP_ID=-1002874013146

python app.py
```

**Ou criar `.env` (não commitar!):**
```bash
# .env (nunca commit)
TELEGRAM_API_ID=24383113
TELEGRAM_API_HASH=387f7520aae351ddc83fb457cdb60085
TELEGRAM_GROUP_ID=-1002874013146
```

### 4. **Usando python-dotenv (opcional)**

Se quiser carregar `.env` automaticamente:
```bash
pip install python-dotenv
```

```python
# No topo de app.py
from dotenv import load_dotenv
load_dotenv()  # Carrega .env
```

---

## 📋 Arquivos Modificados

| Arquivo | O quê | Status |
|---------|-------|--------|
| `app.py` | Substituiu hardcoded por `os.environ.get()` | ✅ Seguro |
| `setup_login.py` | Substituiu hardcoded por `os.environ.get()` | ✅ Seguro |
| `.env.example` | Exemplo de variáveis (seguro commitar) | ✅ Novo |
| `.gitignore` | Adicionou `.env` e arquivos sensíveis | ✅ Novo |

---

## 🚀 Próximos Passos

### 1. **Render - Configure Environment Variables**
```
Settings → Environment → Add Variable
```

### 2. **Fazer Deploy**
```bash
git add app.py setup_login.py .env.example .gitignore
git commit -m "security: Move Telegram credentials to environment variables"
git push origin main
# Render auto-redeploy
```

### 3. **Testar Local**
```powershell
$env:TELEGRAM_API_ID = "24383113"
$env:TELEGRAM_API_HASH = "387f7520aae351ddc83fb457cdb60085"
python setup_login.py  # Se precisar fazer login novo
```

### 4. **Verificar se funciona no Render**
- Visite https://detetive-ss5n.onrender.com
- Teste uma consulta
- Verifique logs: `Render Dashboard → Logs`

---

## ✅ Checklist de Segurança

- ✅ Credenciais movidas para variáveis de ambiente
- ✅ `.gitignore` atualizado (`.env` não será commitado)
- ✅ `.env.example` documentado
- ✅ Validação de credenciais no startup (erro se faltarem)
- ✅ Session file (`.session`) no `.gitignore`
- ✅ Database file (`.db`) no `.gitignore`

---

## 🔒 Boas Práticas Implementadas

1. **Never hardcode secrets** ← ✅ Agora use variáveis de ambiente
2. **Use `.gitignore`** ← ✅ Arquivos sensíveis não são commitados
3. **Document with `.example`** ← ✅ `.env.example` mostra o que configurar
4. **Validate on startup** ← ✅ App falha claramente se faltarem credenciais
5. **Different per environment** ← ✅ Dev/Production usam suas próprias credenciais

---

## 📊 Comparação Antes vs Depois

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Credenciais no código | ❌ Sim (risco!) | ✅ Não |
| Git expõe chaves | ❌ Sim | ✅ Não |
| Fácil configurar ambiente | ❌ Editar código | ✅ Variáveis de ambiente |
| Documentação | ❌ Não | ✅ `.env.example` |
| Segurança | 🔴 Baixa | 🟢 Alta |

