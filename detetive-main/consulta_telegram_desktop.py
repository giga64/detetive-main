import os
import sys
import time
import subprocess
from telethon import TelegramClient, events

# ----------------------
# CONFIGURAÇÃO TELETHON
# ----------------------
API_ID = 24383113                 # seu API ID
API_HASH = '387f7520aae351ddc83fb457cdb60085'  # seu API Hash
SESSION_NAME = 'bot_session'      # nome do arquivo de sessão
GROUP_ID = -1002874013146         # ID numérico do grupo privado

# --------------------------------
# Comando a enviar (ex: /cpf3 ou /cnpj)
# --------------------------------
if len(sys.argv) < 2:
    print("Usage: python consulta_telegram_desktop.py '/cpf3 <CPF>' or '/cnpj <CNPJ>'")
    sys.exit(1)
# Une todos os argumentos para incluir parâmetro
cmd = " ".join(sys.argv[1:])
# Ajusta caso usuário tenha usado '//' no início
if cmd.startswith("//"):
    cmd = cmd.lstrip("/")  # remove barras extras, mantendo '/cpf3'

# ----------------------
# Abre Telegram Desktop (opcional)
# ----------------------
telegram_exe = os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe")
if os.path.exists(telegram_exe):
    subprocess.Popen([telegram_exe])
    # espera o aplicativo abrir
    time.sleep(5)

# ----------------------
# ENVIO VIA TELETHON
# ----------------------
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def main():
    await client.start()
    # Envia mensagem diretamente usando o ID do grupo
    await client.send_message(GROUP_ID, cmd)
    print(f"Comando enviado: {cmd}")

    # Handler aguarda próxima mensagem do bot
    @client.on(events.NewMessage(chats=GROUP_ID))
    async def handler(event):
        print("Resposta do bot:", event.text)
        await client.disconnect()

    print("Aguardando resposta do bot...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
