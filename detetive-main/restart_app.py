#!/usr/bin/env python3
"""
Script para reiniciar a aplicação de forma limpa
"""

import os
import sys
import time
import signal
import subprocess
import psutil

def find_python_processes():
    """Encontra processos Python relacionados à aplicação"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('app.py' in arg for arg in cmdline):
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes

def stop_processes(processes):
    """Para os processos de forma segura"""
    if not processes:
        print("ℹ️ Nenhum processo Python da aplicação encontrado")
        return True
    
    print(f"🛑 Encontrados {len(processes)} processos para parar...")
    
    for proc in processes:
        try:
            print(f"   Parando processo {proc.pid}...")
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"   ⚠️ Erro ao parar processo {proc.pid}: {e}")
    
    # Aguarda os processos terminarem
    print("⏳ Aguardando processos terminarem...")
    time.sleep(3)
    
    # Força parada se necessário
    for proc in processes:
        try:
            if proc.is_running():
                print(f"   Forçando parada do processo {proc.pid}...")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    return True

def check_session_file():
    """Verifica se o arquivo de sessão está acessível"""
    session_file = "bot_session.session"
    
    if not os.path.exists(session_file):
        print("❌ Arquivo de sessão não encontrado!")
        return False
    
    try:
        import sqlite3
        conn = sqlite3.connect(session_file, timeout=5.0)
        conn.close()
        print("✅ Arquivo de sessão acessível")
        return True
    except Exception as e:
        print(f"❌ Problema com arquivo de sessão: {e}")
        return False

def start_application():
    """Inicia a aplicação"""
    print("🚀 Iniciando aplicação...")
    
    try:
        # Verifica se o arquivo app.py existe
        if not os.path.exists("app.py"):
            print("❌ Arquivo app.py não encontrado!")
            return False
        
        # Inicia a aplicação em background
        process = subprocess.Popen([
            sys.executable, "app.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"✅ Aplicação iniciada com PID: {process.pid}")
        print("🌐 Acesse: http://localhost:8000")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao iniciar aplicação: {e}")
        return False

def main():
    """Função principal"""
    print("🔄 Reiniciando aplicação...")
    print("=" * 40)
    
    # 1. Para processos existentes
    processes = find_python_processes()
    if not stop_processes(processes):
        print("❌ Erro ao parar processos")
        return
    
    # 2. Aguarda um pouco
    print("⏳ Aguardando 2 segundos...")
    time.sleep(2)
    
    # 3. Verifica arquivo de sessão
    print("\n🔍 Verificando arquivo de sessão...")
    if not check_session_file():
        print("⚠️ Problemas detectados no arquivo de sessão")
        print("💡 Execute: python fix_session.py")
        return
    
    # 4. Inicia a aplicação
    print("\n🚀 Iniciando nova instância...")
    if not start_application():
        print("❌ Erro ao iniciar aplicação")
        return
    
    print("\n✅ Reinicialização concluída!")

if __name__ == "__main__":
    main() 