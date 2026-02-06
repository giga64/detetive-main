from telethon import TelegramClient

# Substitua pelos seus valores
API_ID    = 123456
API_HASH  = 'abcdef1234567890abcdef1234567890'
SESSION   = 'bot_session'

client = TelegramClient(SESSION, API_ID, API_HASH)

async def main():
    async for dialog in client.iter_dialogs():
        # imprime ID e nome de cada chat/grupo que você participa
        print(dialog.id, dialog.name)

with client:
    client.loop.run_until_complete(main())