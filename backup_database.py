#!/usr/bin/env python3
"""
Script de Backup Criptografado do Database
Faz backup da database com criptografia AES
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
import json

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("⚠️ Instalando cryptography...")
    os.system("pip install cryptography")
    from cryptography.fernet import Fernet


def generate_encryption_key(key_file="backup.key"):
    """Gera ou carrega a chave de criptografia"""
    if os.path.exists(key_file):
        with open(key_file, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        print(f"✅ Chave de criptografia gerada: {key_file}")
        print("   ⚠️  GUARDE ESSA CHAVE EM SEGURANÇA - Sem ela, não pode restaurar backups!")
        return key


def backup_database(db_file="history.db", backup_dir="backups", key_file="backup.key"):
    """Faz backup criptografado do banco"""
    
    # Verificar se arquivo existe
    if not os.path.exists(db_file):
        print(f"❌ Arquivo {db_file} não encontrado!")
        return False
    
    # Criar diretório de backup
    os.makedirs(backup_dir, exist_ok=True)
    
    # Gerar timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Ler arquivo
    with open(db_file, 'rb') as f:
        db_content = f.read()
    
    # Criptografar
    key = generate_encryption_key(key_file)
    cipher = Fernet(key)
    encrypted_content = cipher.encrypt(db_content)
    
    # Salvar backup criptografado
    backup_filename = f"history_backup_{timestamp}.enc"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    with open(backup_path, 'wb') as f:
        f.write(encrypted_content)
    
    # Salvar metadata
    metadata = {
        "timestamp": timestamp,
        "original_file": db_file,
        "file_size": len(db_content),
        "backup_date": datetime.now().isoformat(),
        "encrypted_file": backup_filename
    }
    
    metadata_path = os.path.join(backup_dir, f"history_backup_{timestamp}.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Backup realizado com sucesso!")
    print(f"   📁 Arquivo: {backup_path}")
    print(f"   💾 Tamanho original: {len(db_content) / 1024 / 1024:.2f} MB")
    print(f"   🔒 Tamanho criptografado: {len(encrypted_content) / 1024 / 1024:.2f} MB")
    print(f"   📝 Metadata: {metadata_path}")
    
    return True


def restore_database(backup_file, db_file="history.db", key_file="backup.key"):
    """Restaura backup criptografado do banco"""
    
    if not os.path.exists(backup_file):
        print(f"❌ Arquivo de backup {backup_file} não encontrado!")
        return False
    
    if not os.path.exists(key_file):
        print(f"❌ Arquivo de chave {key_file} não encontrado!")
        return False
    
    # Carregar chave
    with open(key_file, 'rb') as f:
        key = f.read()
    
    # Ler backup criptografado
    with open(backup_file, 'rb') as f:
        encrypted_content = f.read()
    
    # Descriptografar
    try:
        cipher = Fernet(key)
        db_content = cipher.decrypt(encrypted_content)
    except Exception as e:
        print(f"❌ Erro ao descriptografar: {e}")
        return False
    
    # Criar backup do arquivo atual (segurança)
    if os.path.exists(db_file):
        backup_current = f"{db_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy(db_file, backup_current)
        print(f"✅ Arquivo atual salvo como: {backup_current}")
    
    # Restaurar
    with open(db_file, 'wb') as f:
        f.write(db_content)
    
    print(f"✅ Backup restaurado com sucesso!")
    print(f"   📁 Arquivo: {db_file}")
    print(f"   💾 Tamanho restaurado: {len(db_content) / 1024 / 1024:.2f} MB")
    
    return True


def list_backups(backup_dir="backups"):
    """Lista todos os backups disponíveis"""
    
    if not os.path.exists(backup_dir):
        print("❌ Diretório de backups não encontrado!")
        return
    
    backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.enc')])
    
    if not backups:
        print("❌ Nenhum backup encontrado!")
        return
    
    print(f"\n📋 Backups disponíveis ({len(backups)}):\n")
    for i, backup in enumerate(backups, 1):
        backup_path = os.path.join(backup_dir, backup)
        size = os.path.getsize(backup_path) / 1024 / 1024
        print(f"{i}. {backup} ({size:.2f} MB)")
        
        # Tentar ler metadata
        metadata_file = backup.replace('.enc', '.json')
        metadata_path = os.path.join(backup_dir, metadata_file)
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                print(f"   Data: {metadata.get('backup_date', 'N/A')}")
                print(f"   Tamanho original: {metadata.get('file_size', 0) / 1024 / 1024:.2f} MB")
    
    print()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
Backup Criptografado de Database

Uso:
  python backup_database.py backup           - Fazer backup
  python backup_database.py restore <arquivo> - Restaurar backup
  python backup_database.py list             - Listar backups
  python backup_database.py genkey            - Gerar nova chave

Exemplos:
  python backup_database.py backup
  python backup_database.py restore backups/history_backup_20250226_120000.enc
  python backup_database.py list
        """)
        sys.exit(0)
    
    action = sys.argv[1].lower()
    
    if action == "backup":
        backup_database()
    elif action == "restore":
        if len(sys.argv) < 3:
            print("❌ Especifique o arquivo de backup a restaurar")
            sys.exit(1)
        restore_database(sys.argv[2])
    elif action == "list":
        list_backups()
    elif action == "genkey":
        key = generate_encryption_key()
        print(f"\n🔐 Chave gerada: {key.decode()}")
    else:
        print(f"❌ Ação desconhecida: {action}")
        sys.exit(1)
