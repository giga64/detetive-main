#!/usr/bin/env python3
"""
Script para testar o endpoint de limpeza de histórico
"""
import sqlite3
import sys

# Conectar ao banco de dados
conn = sqlite3.connect('detetive.db')
cursor = conn.cursor()

# Ver se tem dados no histórico
cursor.execute("SELECT COUNT(*) FROM searches WHERE username = 'test_user'")
count_before = cursor.fetchone()[0]
print(f"[ANTES] Número de buscas para teste: {count_before}")

# Ver dados
if count_before > 0:
    cursor.execute("SELECT id, identifier, searched_at FROM searches WHERE username = 'test_user' LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(f"  - ID: {row[0]}, Identificador: {row[1]}, Data: {row[2]}")

# Tentar simular o que o endpoint faz
try:
    cursor.execute("DELETE FROM searches WHERE username = 'test_user'")
    conn.commit()
    print(f"\n[DELETE] Executado com sucesso")
    
    cursor.execute("SELECT COUNT(*) FROM searches WHERE username = 'test_user'")
    count_after = cursor.fetchone()[0]
    print(f"[DEPOIS] Número de buscas para teste: {count_after}")
except Exception as e:
    print(f"[ERRO] {e}")
    conn.rollback()

conn.close()
