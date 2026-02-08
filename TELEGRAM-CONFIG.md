# 🔧 Configuração do Telegram

## ❌ Erro: ChatRestrictedError

Se você está recebendo o erro:
```
ChatRestrictedError: The chat is restricted and cannot be used in that request
```

## 📋 Soluções

### 1️⃣ Verificar Permissões do Bot no Grupo

O bot precisa ter permissão para:
- ✅ Enviar mensagens
- ✅ Ler mensagens
- ✅ Postar no grupo (se for canal)

### 2️⃣ Verificar se o Grupo está Privado/Público

**Para grupos privados:**
- Use o ID numérico do grupo (ex: `-1001234567890`)
- Adicione o bot como **administrador** ou membro com permissão de postar

**Para grupos/canais públicos:**
- Use o username (ex: `@meu_grupo`)
- Certifique-se que o bot está no grupo

### 3️⃣ Como Obter o ID do Grupo

**Método 1: Usando @RawDataBot**
1. Adicione `@RawDataBot` ao grupo
2. Ele enviará o ID do grupo
3. Use esse ID na variável `TELEGRAM_GROUP_ID`

**Método 2: Código Python**
```python
from telethon.sync import TelegramClient

client = TelegramClient('session', API_ID, API_HASH)
client.start()

# Listar todos os diálogos
for dialog in client.iter_dialogs():
    print(f"{dialog.name}: {dialog.id}")
```

### 4️⃣ Variáveis de Ambiente

Configure estas variáveis:

```bash
TELEGRAM_API_ID=17993467
TELEGRAM_API_HASH=684fdc620ac8ace6bc1ee15c219744a3
TELEGRAM_GROUP_ID=-1001234567890  # Seu ID do grupo aqui
STRING_SESSION=sua_string_session_aqui
```

### 5️⃣ Gerar String Session

Execute `generate_session.py`:
```bash
python generate_session.py
```

Salve a string gerada na variável `STRING_SESSION`.

## 🔍 Testando a Conexão

O sistema agora mostra mensagens de erro mais claras:
- ❌ **Grupo restrito** - verifique permissões
- ❌ **Bot sem permissão** - adicione o bot como admin
- ❌ **Erro ao acessar grupo** - ID do grupo incorreto
- ❌ **Timeout** - grupo não responde

## 📝 Checklist

- [ ] Bot está no grupo/canal
- [ ] Bot tem permissão para postar
- [ ] ID do grupo está correto (com `-` se for grupo privado)
- [ ] STRING_SESSION está válida
- [ ] API_ID e API_HASH estão corretos

## 💡 Dica

Use `-100` antes do ID para grupos:
- ❌ Errado: `1234567890`
- ✅ Correto: `-1001234567890`
