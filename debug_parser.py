#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re

test_data = """• CONSULTA DE CPF 🔍

• CPF: 00964153475

• PIS: 12807448641

• POSSÍVEIS PARENTES: 

NOME: MARCUS VINICIUS FERNANDES GOMES
CPF: 07043075459
PARENTESCO: FILHA(O)

NOME: MARIA EDNA FERNANDES DE PAIVA
CPF: 07607130497
PARENTESCO: MAE

• POSSÍVEIS VIZINHOS: 

NOME: VALDOMIRO COSME DE OLIVEIRA
CPF: 26064103434

NOME: CARLOS ROMULO LEITE PINTO
CPF: 07132131400

• PARTICIPAÇÃO SOCIETÁRIA: 

CNPJ: 11712147000120
CARGO: SEM INFORMAÇÃO
"""

# Debug parentes
print("=== DEBUG PARENTES ===")

# Primeiro, encontrar onde começam os parentes
parente_idx = test_data.upper().find("POSSÍVEL")
print(f"Índice de POSSÍVEL: {parente_idx}")
print(f"Contexto (100 chars após): {repr(test_data[parente_idx:parente_idx+100])}\n")

# Procurar especificamente por "POSSÍVEIS PARENTES"
if "POSSÍVEIS PARENTES" in test_data:
    print("Encontrou 'POSSÍVEIS PARENTES'")
    idx = test_data.index("POSSÍVEIS PARENTES")
    print(f"Contexto: {repr(test_data[idx:idx+150])}\n")
    
    # Agora extrair texto após isso até próxima seção
    resto = test_data[idx:]
    match = re.search(r'POSSÍVEIS PARENTES:\s*\n([\s\S]+?)(?=\n• |POSSÍVEIS VIZINHOS|$)', resto)
    if match:
        print(f"Encontrou com novo regex!")
        print(f"Texto: {repr(match.group(1)[:200])}")
    else:
        print("Ainda não achou")
