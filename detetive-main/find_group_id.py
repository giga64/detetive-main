#!/usr/bin/env python3
"""
Script para descobrir o ID correto do grupo no Telegram
Execute após fazer login com setup_login.py
"""
import os
import asyncio
from telethon import TelegramClient

API_ID = int(os.environ.get("TELEGRAM_API_ID", "17993467"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "684fdc620ac8ace6bc1ee15c219744a3")
SESSION_NAME = 'bot_session_novo'

async def find_groups():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ Você não está logado. Execute setup_login.py primeiro.")
        await client.disconnect()
        return
    
    print("📊 Buscando grupos e canais...\n")
    
    # Busca todos os diálogos (chats)
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            entity = dialog.entity
            print(f"📌 Nome: {dialog.name}")
            print(f"   ID: {entity.id}")
            print(f"   Tipo: {'Canal' if dialog.is_channel else 'Grupo'}")
            if hasattr(entity, 'username') and entity.username:
                print(f"   Username: @{entity.username}")
            print()
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(find_groups())
