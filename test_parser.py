#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import json

def parse_resultado_consulta(resultado_texto: str) -> dict:
    """Faz parsing do resultado textual e retorna dados estruturados"""
    
    data = {
        "dados_pessoais": {},
        "emails": [],
        "enderecos": [],
        "telefones": [],
        "parentes": [],
        "vizinhos": [],
        "empresas": [],
        "vinculos": [],
        "score": None,
        "risco": None
    }
    
    # Helper para extrair valor após label
    def get_value(label, text=resultado_texto):
        match = re.search(rf'{label}:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        return match.group(1).strip() if match else None
    
    # Dados pessoais
    data["dados_pessoais"]["cpf"] = get_value("CPF")
    data["dados_pessoais"]["pis"] = get_value("PIS")
    data["dados_pessoais"]["titulo"] = get_value("TÍTULO ELEITORAL")
    data["dados_pessoais"]["rg"] = get_value("RG")
    data["dados_pessoais"]["nome"] = get_value("NOME")
    data["dados_pessoais"]["nascimento"] = get_value("NASCIMENTO")
    data["dados_pessoais"]["idade"] = get_value("IDADE")
    data["dados_pessoais"]["signo"] = get_value("SIGNO")
    data["dados_pessoais"]["mae"] = get_value("MÃE")
    data["dados_pessoais"]["pai"] = get_value("PAI")
    data["dados_pessoais"]["nacionalidade"] = get_value("NACIONALIDADE")
    data["dados_pessoais"]["escolaridade"] = get_value("ESCOLARIDADE")
    data["dados_pessoais"]["estado_civil"] = get_value("ESTADO CIVIL")
    data["dados_pessoais"]["profissao"] = get_value("PROFISSÃO")
    data["dados_pessoais"]["renda"] = get_value("RENDA PRESUMIDA")
    data["dados_pessoais"]["status_rf"] = get_value("STATUS RECEITA FEDERAL")
    
    # Score e Risco
    score_val = get_value("SCORE")
    if score_val:
        try:
            data["score"] = int(score_val)
        except:
            pass
    data["risco"] = get_value("FAIXA DE RISCO")
    
    # ==================== E-MAILS ====================
    emails_match = re.search(r'E-MAILS?:\s*\n(.+?)(?:\n\s*•|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if emails_match:
        emails_text = emails_match.group(1)
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', emails_text)
        data["emails"] = list(set(emails))
    
    # ==================== ENDEREÇOS ====================
    enderecos_match = re.search(r'ENDEREÇO[S]?:\s*\n(.+?)(?=\n\s*•\s*TELEFONE|\n\s*•\s*POSSÍVEL|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if enderecos_match:
        enderecos_text = enderecos_match.group(1)
        linhas = enderecos_text.split('\n')
        for linha in linhas:
            linha = linha.strip()
            if len(linha) > 15 and re.search(r'[A-Z]{2}\s+\d{8}', linha):
                linha = re.sub(r'\s+', ' ', linha)
                if linha not in data["enderecos"]:
                    data["enderecos"].append(linha)
    
    # ==================== TELEFONES ====================
    telefones_match = re.search(r'TELEFONE[S]?\s+PROPRIETÁRIO[S]?:\s*\n(.+?)(?:\n\s*•|\nTELEFONE|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if telefones_match:
        telefones_text = telefones_match.group(1)
        if "SEM INFORMAÇÃO" not in telefones_text.upper() or len(telefones_text) > 30:
            linhas = telefones_text.split('\n')
            for linha in linhas:
                linha = linha.strip()
                linha = re.sub(r'\s+-\s+(NÃO INFORMADO|TELEFONIA|.*?)$', '', linha, flags=re.IGNORECASE)
                if re.match(r'^\d{8,11}$', linha):
                    if len(linha) == 8:
                        tel = f"{linha[:4]}-{linha[4:]}"
                    elif len(linha) == 10:
                        tel = f"({linha[:2]}) {linha[2:6]}-{linha[6:]}"
                    elif len(linha) == 11:
                        tel = f"({linha[:2]}) {linha[2:7]}-{linha[7:]}"
                    else:
                        tel = linha
                    
                    if tel not in data["telefones"] and len(tel) > 0:
                        data["telefones"].append(tel)
    
    # ==================== POSSÍVEIS PARENTES ====================
    parentes_match = re.search(r'POSSÍVEIS PARENTES:\s*\n([\s\S]+?)(?=\n•\s*POSSÍVEL|POSSÍVEIS VIZINHOS|PARTICIPAÇÃO|$)', resultado_texto, re.IGNORECASE)
    if parentes_match:
        parentes_text = parentes_match.group(1)
        # Encontrar todos os blocos de NOME...CPF...PARENTESCO
        blocos = re.findall(r'NOME:\s*(.+?)\nCPF:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nPARENTESCO:\s*(.+?)(?=\n\n|\nNOME:|$)', parentes_text, re.IGNORECASE)
        for nome, cpf, parentesco in blocos:
            if cpf.strip():
                data["parentes"].append({
                    "nome": nome.strip(),
                    "cpf": cpf.strip(),
                    "parentesco": parentesco.strip()
                })
    
    # ==================== POSSÍVEIS VIZINHOS ====================
    vizinhos_match = re.search(r'POSSÍVEIS VIZINHOS:\s*\n([\s\S]+?)(?=\n•|PARTICIPAÇÃO|VÍNCULO|$)', resultado_texto, re.IGNORECASE)
    if vizinhos_match:
        vizinhos_text = vizinhos_match.group(1)
        # Encontrar todos os blocos de NOME...CPF
        blocos = re.findall(r'NOME:\s*(.+?)\nCPF:\s*(\d+(?:\.\d+)*(?:\-\d+)?)', vizinhos_text, re.IGNORECASE)
        for nome, cpf in blocos:
            if cpf.strip():
                data["vizinhos"].append({
                    "nome": nome.strip(),
                    "cpf": cpf.strip()
                })
    
    # ==================== PARTICIPAÇÃO SOCIETÁRIA ====================
    empresas_match = re.search(r'PARTICIPAÇÃO\s+SOCIETÁRIA:\s*\n(.+?)(?:\n\s*•\s*VÍNCULO|\n\s*•\s*USUÁRIO|\Z)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if empresas_match:
        empresas_text = empresas_match.group(1)
        blocos = re.findall(r'CNPJ:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nCARGO:\s*(.+?)(?=\nCNPJ:|$)', empresas_text, re.IGNORECASE | re.DOTALL)
        for cnpj, cargo in blocos:
            if cnpj.strip():
                empresa = {"cnpj": cnpj.strip()}
                cargo_clean = cargo.strip()
                if cargo_clean and "SEM INFORMAÇÃO" not in cargo_clean:
                    empresa["cargo"] = cargo_clean
                data["empresas"].append(empresa)
    
    # ==================== VÍNCULOS EMPREGATÍCIOS ====================
    vinculos_match = re.search(r'VÍNCULO[S]?\s+EMPREGATÍCIO[S]?:\s*\n(.+?)(?:\n\s*•\s*USUÁRIO|$)', resultado_texto, re.IGNORECASE | re.DOTALL)
    if vinculos_match:
        vinculos_text = vinculos_match.group(1)
        blocos = re.findall(r'CNPJ:\s*(\d+(?:\.\d+)*(?:\-\d+)?)\nADMISSÃO:\s*(.+?)(?=\nCNPJ:|$)', vinculos_text, re.IGNORECASE | re.DOTALL)
        for cnpj, admissao in blocos:
            if cnpj.strip():
                vem = f"CNPJ: {cnpj.strip()}"
                admissao_clean = admissao.strip()
                if admissao_clean and "USUÁRIO" not in admissao_clean:
                    vem += f" | Admissão: {admissao_clean}"
                data["vinculos"].append(vem)
    
    data["usuario"] = get_value("USUÁRIO")
    
    return data


# Teste com dados do usuário
test_data = """• CONSULTA DE CPF 🔍

• CPF: 00964153475

• PIS: 12807448641

• TÍTULO ELEITORAL: 020221591627 

• RG: SEM INFORMAÇÃO
• DATA DE EXPEDIÇÃO: SEM INFORMAÇÃO
• ORGÃO EXPEDIDOR: SEM INFORMAÇÃO
• UF - RG: SEM INFORMAÇÃO

• NOME: SHARLENE MARIA KATIUSSIA FERNANDES DE PAIVA
• NASCIMENTO: 29/12/1980
• IDADE: 45
• SIGNO: CAPRICÓRNIO

• MÃE: MARIA EDNA FERNANDES DE PAIVA
• PAI: SEM INFORMAÇÃO

• NACIONALIDADE: BRASILEIRA
• ESCOLARIDADE: ENSINO SUPERIOR COMPLETO

• ESTADO CIVIL: SEM INFORMAÇÃO

• PROFISSÃO: AUXILIAR DE ESCRITÓRIO
• RENDA PRESUMIDA: 2101,69

• STATUS RECEITA FEDERAL: REGULAR

• SCORE: 15
• FAIXA DE RISCO: ALTISSIMO

• E-MAILS: 

shakety@hotmail.com
vinicius.marcus2003@gmail.com
shaakety@hotmail.com
charlenepaiva@oi.com.br

• ENDEREÇOS: 

R DAS AMAPOLAS, 594 - C MACIO - CAPIM MACIO, NATAL-RN 59078150

AV XAVIER DA SILVEIRA, 1713 -  - LGA NOVA, NATAL-RN 59056700

AV XAVIER DA SILVEIRA, 1713 - BL C AP 202 BL C AP 202 - TIROL, NATAL-RN 59015430

R AMARILES, 1413 -  - NOSSA SENHORA DA APRESENTACAO, NATAL-RN 59115430

• TELEFONES PROPRIETÁRIO: 

8432213230 - NÃO INFORMADO
8432015992 - NÃO INFORMADO
84988020705 - NÃO INFORMADO
84999340022 - NÃO INFORMADO

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

CNPJ: 43959951000103
CARGO: SOCIO-ADMINISTRADOR

• VÍNCULOS EMPREGATÍCIOS: 

CNPJ: 10772751000180
ADMISSÃO: 01/05/2011

• USUÁRIO: mv mv
"""

resultado = parse_resultado_consulta(test_data)
print(json.dumps(resultado, indent=2, ensure_ascii=False))
