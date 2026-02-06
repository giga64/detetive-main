#!/usr/bin/env python3
"""
Script para verificar e corrigir problemas com o arquivo de sessão do Telethon
"""

import os
import sqlite3
import shutil
from datetime import datetime

def check_session_file():
    """Verifica o arquivo de sessão do Telethon"""
    session_file = "bot_session.session"
    
    if not os.path.exists(session_file):
        print("❌ Arquivo de sessão não encontrado!")
        return False
    
    print(f"📁 Arquivo de sessão encontrado: {session_file}")
    print(f"📊 Tamanho: {os.path.getsize(session_file)} bytes")
    print(f"🕒 Última modificação: {datetime.fromtimestamp(os.path.getmtime(session_file))}")
    
    return True

def backup_session():
    """Faz backup do arquivo de sessão"""
    session_file = "bot_session.session"
    backup_file = f"bot_session_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.session"
    
    if os.path.exists(session_file):
        shutil.copy2(session_file, backup_file)
        print(f"💾 Backup criado: {backup_file}")
        return backup_file
    return None

def check_sqlite_integrity():
    """Verifica a integridade do arquivo SQLite da sessão"""
    session_file = "bot_session.session"
    
    if not os.path.exists(session_file):
        print("❌ Arquivo de sessão não encontrado!")
        return False
    
    try:
        conn = sqlite3.connect(session_file)
        cursor = conn.cursor()
        
        # Verifica integridade
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        if result[0] == "ok":
            print("✅ Integridade do banco de dados: OK")
            return True
        else:
            print(f"❌ Problemas de integridade: {result[0]}")
            return False
            
    except sqlite3.Error as e:
        print(f"❌ Erro ao verificar integridade: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def clear_session_locks():
    """Tenta limpar locks do arquivo de sessão"""
    session_file = "bot_session.session"
    
    if not os.path.exists(session_file):
        print("❌ Arquivo de sessão não encontrado!")
        return False
    
    try:
        # Tenta conectar com timeout reduzido
        conn = sqlite3.connect(session_file, timeout=1.0)
        cursor = conn.cursor()
        
        # Executa uma query simples para verificar se está acessível
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print(f"✅ Arquivo de sessão acessível. Tabelas encontradas: {len(tables)}")
        conn.close()
        return True
        
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print("🔒 Arquivo de sessão está bloqueado!")
            print("💡 Tentando resolver...")
            
            # Tenta fazer backup e recriar
            backup_file = backup_session()
            if backup_file:
                try:
                    os.remove(session_file)
                    print("🗑️ Arquivo de sessão removido")
                    print("⚠️ Você precisará executar setup_login.py novamente")
                    return True
                except Exception as e:
                    print(f"❌ Erro ao remover arquivo: {e}")
                    return False
        else:
            print(f"❌ Erro de banco de dados: {e}")
            return False
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False

def main():
    """Função principal"""
    print("🔍 Verificando arquivo de sessão do Telethon...")
    print("=" * 50)
    
    # Verifica se o arquivo existe
    if not check_session_file():
        print("\n💡 Execute setup_login.py para criar o arquivo de sessão")
        return
    
    print("\n🔧 Verificando integridade...")
    if not check_sqlite_integrity():
        print("\n⚠️ Problemas detectados na integridade do arquivo")
    
    print("\n🔓 Verificando locks...")
    if not clear_session_locks():
        print("\n❌ Não foi possível resolver os problemas automaticamente")
        print("💡 Tente:")
        print("   1. Parar todos os processos Python")
        print("   2. Executar este script novamente")
        print("   3. Se persistir, execute setup_login.py")
    else:
        print("\n✅ Verificação concluída com sucesso!")

if __name__ == "__main__":
    main() 