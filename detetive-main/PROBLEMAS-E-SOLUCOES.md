# 🔧 Problemas Identificados e Soluções Implementadas

## 🔴 **Problemas que causavam crashes com múltiplas requisições:**

### 1. **Threading Lock + Async = Deadlock**
**Problema:** Usava `threading.Lock()` (bloqueante) dentro de código async (não-bloqueante)
```python
# ❌ ERRADO - Causava deadlock
with telegram_lock:  # Bloqueia thread
    await client.connect()  # Async espera
```
**Solução:** Usar `asyncio.Semaphore()` para limitar conexões simultâneas de forma async-safe
```python
# ✅ CORRETO
async with telegram_semaphore:  # Sem bloqueio de thread
    async with get_telegram_client() as client:
        # Múltiplas requisições podem competir sem deadlock
```

### 2. **Event Handler não removido**
**Problema:** Handler Telegram registrado infinitamente, causando memory leak e respostas duplicadas
```python
# ❌ ERRADO - Handler nunca removido
client.add_event_handler(handler, events.NewMessage(chats=GROUP_ID))
# Requisição seguinte vê resposta da requisição anterior!
```
**Solução:** Remover handler após usar
```python
# ✅ CORRETO
try:
    client.add_event_handler(handler, events.NewMessage(chats=GROUP_ID))
    await client.send_message(GROUP_ID, cmd)
    await asyncio.wait_for(response_received.wait(), timeout=45)
finally:
    client.remove_event_handler(handler)  # Sempre remove!
```

### 3. **SQLite bloqueado com múltiplas requisições**
**Problema:** SQLite usa locks file-level, travando com concorrência
```python
# ❌ ERRADO - Sem timeout, bloqueia indefinidamente
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
```
**Solução:** Modo autocommit com timeout
```python
# ✅ CORRETO
conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
conn.isolation_level = None  # Autocommit mode - sem locks longos
```

### 4. **Timeout pequeno (30s) - Bot Telegram pode demorar**
**Problema:** Em horários de pico, o bot do Telegram pode demorar >30s, causando timeout
**Solução:** Aumentar timeout para 45s + retry automático com backoff exponencial
```python
# ✅ CORRETO
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def consulta_telegram(cmd: str) -> str:
    await asyncio.wait_for(response_received.wait(), timeout=45)
    # Retenta automaticamente 3 vezes com espera exponencial (2s, 4s, 8s...)
```

### 5. **Sem tratamento de exceções específicas**
**Problema:** Erros genéricos não diferenciavam "bot indisponível" de "erro de conexão"
**Solução:** Capturar e mensagens de erro específicas
```python
# ✅ CORRETO
except asyncio.TimeoutError:
    return "❌ Timeout aguardando resposta do bot. O servidor está sobrecarregado."
except Exception as e:
    if "database is locked" in error_msg.lower():
        return "❌ Banco de dados bloqueado. Tente novamente em alguns segundos."
```

---

## 📋 **Mudanças no código:**

### `app.py`:
- ✅ Removido `import threading` → `from tenacity import retry, ...`
- ✅ Substituído `threading.Lock()` → `asyncio.Semaphore(3)` (máx 3 conexões simultâneas)
- ✅ SQLite: adicionado `timeout=10` e `isolation_level=None`
- ✅ Handler: agora remove após usar (no bloco `finally`)
- ✅ Função `consulta_telegram()`: adicionado `@retry` decorator
- ✅ Timeout aumentado de 30s → 45s
- ✅ Mensagens de erro mais descritivas

### `requirements.txt`:
- ✅ Adicionado `tenacity` (para retry automático)

---

## 🚀 **Como atualizar no Render:**

1. **Git commit & push:**
   ```bash
   git add app.py requirements.txt
   git commit -m "fix: Resolver crashes com múltiplas requisições - usar asyncio.Semaphore, remover handlers, adicionar retry"
   git push origin main
   ```

2. **Render redeploy automaticamente** (webhook configurado)

3. **Testar:** Fazer múltiplas pesquisas simultâneas no site

---

## ✅ **Comportamento esperado agora:**

| Cenário | Antes | Depois |
|---------|-------|--------|
| 1 requisição | ✅ OK | ✅ OK |
| 2-3 simultâneas | 🔴 Crash | ✅ Fila (Semaphore) |
| 4+ simultâneas | 🔴 Crash | ✅ Max 3, resto aguarda |
| Bot timeout | 🔴 Erro | ✅ Retry 3x automático |
| Banco travado | 🔴 Erro vago | ✅ Msg clara + retry |
| Memory leak | 🔴 Site fica lento | ✅ Handler sempre removido |

---

## 📊 **Métricas melhoradas:**

- **Concorrência**: ~1 → ~3 requisições simultâneas
- **Retry**: Manual → Automático (3 tentativas)
- **Timeout**: 30s → 45s
- **Memory leak**: Sim → Não
- **Mensagens erro**: Genéricas → Específicas

