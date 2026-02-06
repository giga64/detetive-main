import os
from telethon.sync import TelegramClient

# ✅ Credenciais do Telegram - Use variáveis de ambiente
API_ID = int(os.environ.get("TELEGRAM_API_ID", "17993467"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "684fdc620ac8ace6bc1ee15c219744a3")

# Validação
if not API_ID or not API_HASH:
    print("❌ ERRO: Defina as variáveis de ambiente:")
    print("   export TELEGRAM_API_ID=seu_id_aqui")
    print("   export TELEGRAM_API_HASH=seu_hash_aqui")
    exit(1)

# Nome do arquivo de sessão que será criado
SESSION_NAME = 'bot_session_novo'

def main():
    print("🔐 Iniciando login no Telegram...")
    with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        print("✅ Login realizado com sucesso.")
        print("⚠️ Arquivo de sessão salvo como:", f"{SESSION_NAME}.session")

if __name__ == '__main__':
    main()
