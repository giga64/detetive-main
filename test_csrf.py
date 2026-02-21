#!/usr/bin/env python3
"""
Script para simular a requisição de limpeza de histórico
"""
import sqlite3
import secrets

# Simular o que o app.py faria
csrf_tokens = {}

def generate_csrf_token():
    return secrets.token_urlsafe(32)

def get_or_create_csrf_token(session_id):
    if session_id not in csrf_tokens:
        csrf_tokens[session_id] = {
            "token": generate_csrf_token(),
            "created": 123456789
        }
    return csrf_tokens[session_id]["token"]

def validate_csrf_token(session_id, token):
    if not session_id or session_id not in csrf_tokens:
        return False
    return csrf_tokens[session_id]["token"] == token

# Simulando autenticação
username = "pedro.lima"
session_id = username

# Criar token
token = get_or_create_csrf_token(session_id)
print(f"[1] Token gerado: {token[:20]}...")

# Validar token
is_valid = validate_csrf_token(session_id, token)
print(f"[2] Token válido: {is_valid}")

# Tentar com token inválido
is_invalid = validate_csrf_token(session_id, "token_errado")
print(f"[3] Token inválido (esperado False): {is_invalid}")

# Simular requisição POST
print("\n[Simulando requisição POST]")
# O que deveria acontecer:
# 1. Usuário acessa /historico (GET) -> token gerado e enviado no formulário
# 2. Usuário clica em "Limpar Histórico" -> formulário POST com o token
# 3. Servidor valida o token
# 4. Se válido, limpa o histórico

print(f"Token que será enviado: {token[:20]}...")
print(f"Validação do token: {validate_csrf_token(session_id, token)}")
