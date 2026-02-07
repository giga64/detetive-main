#!/usr/bin/env python3
"""
Script para gerar STRING_SESSION do Telegram (Telethon).
Execute este script localmente, faça login no Telegram e copie a string gerada.
"""
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(os.environ.get("TELEGRAM_API_ID", "17993467"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "684fdc620ac8ace6bc1ee15c219744a3")

async def generate_session():
    # Usar StringSession vazia para criar nova sessão
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    print("\n🔐 GERADOR DE SESSÃO TELEGRAM (OneSeek)\n")
    print("=" * 60)
    print("Conectando ao Telegram...")
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print("\n✅ Você será redirecionado para fazer login.")
        print("Siga as instruções abaixo:\n")
        
        # Fazer login
        await client.start()
    
    # Obter a string da sessão
    session_string = client.session.save()
    
    print("\n" + "=" * 60)
    print("🎉 SESSÃO GERADA COM SUCESSO!\n")
    print("Copie a string abaixo e defina como variável STRING_SESSION no Railway:\n")
    print(session_string)
    print("\n" + "=" * 60)
    print("\nPASSOS:")
    print("1. Copie a string acima (sem linhas extras)")
    print("2. No Railway → Variables → New Variable")
    print("3. Nome: STRING_SESSION")
    print("4. Valor: <cole a string aqui>")
    print("5. Click 'Redeploy' do projeto")
    print("=" * 60 + "\n")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(generate_session())
