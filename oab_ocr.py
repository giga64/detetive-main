"""
Módulo para extração de dados OAB via OCR da imagem da ficha
Extrai: nome, inscrição, tipo, seccional, subseccao, endereço, telefone
"""
import re
import io
from typing import Dict, Optional

def extrair_dados_ficha_ocr(imagem_bytes: bytes) -> Dict[str, str]:
    """
    Extrai dados da ficha OAB usando OCR via Tesseract.
    
    Args:
        imagem_bytes: Bytes da imagem JPEG da ficha
        
    Returns:
        Dict com campos: nome, inscrição, seccional, subseccao, endereco, telefone, tipo
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise ImportError("Instale pytesseract e pillow com: pip install pytesseract pillow")
    
    # Configurar caminho do Tesseract para Railway/Linux
    import sys
    import os
    if sys.platform != "win32":
        # No Railway (Linux), o tesseract fica em /usr/bin
        if os.path.exists("/usr/bin/tesseract"):
            pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
        # Configurar caminho de dados de idioma
        if not os.environ.get('TESSDATA_PREFIX'):
            if os.path.exists("/usr/share/tesseract-ocr/"):
                os.environ['TESSDATA_PREFIX'] = "/usr/share/tesseract-ocr/"
            elif os.path.exists("/usr/share/tessdata/"):
                os.environ['TESSDATA_PREFIX'] = "/usr/share/tessdata/"
    else:
        # No Windows, procurar em Program Files
        if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    
    # Converter bytes para imagem PIL
    img = Image.open(io.BytesIO(imagem_bytes))
    
    # Fazer OCR com Tesseract (português)
    texto_completo = pytesseract.image_to_string(img, lang='por')
    
    # Inicializar dados
    dados = {
        "nome": None,
        "inscricao": None,
        "tipo": None,
        "seccional": None,
        "subseccao": None,
        "endereco": None,
        "telefone": None,
        "cep": None,
    }
    
    # ========== EXTRAÇÃO DE CAMPOS ==========
    
    linhas_texto = texto_completo.split("\n")
    
    # 1. NOME - primeira linha que começa com maiúscula
    for linha in linhas_texto:
        if re.match(r'^[A-Z].*[A-Z].*', linha) and 'Inscrição' not in linha and len(linha) > 5:
            dados['nome'] = linha.strip()
            break
    
    # 2. INSCRIÇÃO - linha que é apenas 4 dígitos
    for i, linha in enumerate(linhas_texto):
        if re.match(r'^\d{4}$', linha.strip()):
            dados['inscricao'] = linha.strip()
            break
    
    # 3. TIPO - procura por palavras-chave
    if 'ADVOGADO' in texto_completo.upper():
        dados['tipo'] = 'Advogado'
    elif 'ESTAGIÁRIO' in texto_completo.upper():
        dados['tipo'] = 'Estagiário'
    elif 'SUPLEMENTAR' in texto_completo.upper():
        dados['tipo'] = 'Suplementar'
    
    # 4. SECCIONAL - UF específica
    uf_pattern = r'\b([A-Z]{2})\b'
    matches_uf = re.finditer(uf_pattern, texto_completo)
    
    estados_validos = {
        'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
        'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
        'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    }
    
    for match in matches_uf:
        uf = match.group(1)
        if uf in estados_validos:
            contexto_ante = texto_completo[max(0, match.start()-20):match.start()]
            if 'Seccional' in contexto_ante or re.search(r'\d', contexto_ante):
                dados['seccional'] = uf
                break
    
    if not dados['seccional']:
        for match in matches_uf:
            if match.group(1) in estados_validos:
                dados['seccional'] = match.group(1)
                break
    
    # 5. SUBSEÇÃO - procura por "CONSELHO"
    subsec_match = re.search(
        r'(CONSELHO\s+SECCIONAL[^\n]*(?:RN|RIO\s+GRANDE\s+DO\s+NORTE)?)',
        texto_completo,
        re.IGNORECASE
    )
    if subsec_match:
        subsec_raw = subsec_match.group(1).replace('\n', ' ').strip()
        subsec_clean = re.sub(r'\s+(Endereço|Telefone|situacao|E-mail).*', '', subsec_raw, flags=re.IGNORECASE)
        dados['subseccao'] = subsec_clean.strip()
    
    # 6. ENDEREÇO - procura por RUA, AV, etc
    endereco_pattern = r'(RUA|AV(?:ENIDA)?|PRAÇA|TRAVESSA|TV|R\.)\s+[^,\n]*'
    endereco_match = re.search(endereco_pattern, texto_completo, re.IGNORECASE)
    
    if endereco_match:
        start = endereco_match.start()
        resto_texto = texto_completo[start:]
        
        fim = len(resto_texto)
        match_fim = re.search(r'\b(RN|59020|NATAL|Telefone|situacao)', resto_texto, re.IGNORECASE)
        if match_fim:
            fim = match_fim.start()
        
        endereco_bruto = resto_texto[:fim].strip()
        endereco_limpo = ' '.join(endereco_bruto.split())
        dados['endereco'] = endereco_limpo
    
    # 7. TELEFONE - padrão (XX) XXXX-XXXX
    tel_pattern = r'\(?(\d{2})\)?\s*(\d{4,5})-?(\d{4})'
    tel_match = re.search(tel_pattern, texto_completo)
    
    if tel_match:
        dados['telefone'] = f"({tel_match.group(1)}) {tel_match.group(2)}-{tel_match.group(3)}"
    
    # 8. CEP - extras para complementar endereço
    cep_pattern = r'(\d{5})-?(\d{3,4})'
    cep_match = re.search(cep_pattern, texto_completo)
    if cep_match:
        dados['cep'] = f"{cep_match.group(1)}-{cep_match.group(2)}"
    
    # Limpar valores None e vazios
    dados = {k: v for k, v in dados.items() if v}
    
    return dados
    
    # Inicializar dados
    dados = {
        "nome": None,
        "inscricao": None,
        "tipo": None,
        "seccional": None,
        "subseccao": None,
        "endereco": None,
        "telefone": None,
        "cep": None,
    }
    
    # ========== EXTRAÇÃO DE CAMPOS ==========
    
    # 1. NOME - primeira linha que começa com maiúscula
    for linha in linhas_texto:
        if re.match(r'^[A-Z].*[A-Z].*', linha) and 'Inscrição' not in linha and len(linha) > 5:
            dados['nome'] = linha.strip()
            break
    
    # 2. INSCRIÇÃO - linha que é apenas 4 dígitos
    for i, linha in enumerate(linhas_texto):
        if re.match(r'^\d{4}$', linha.strip()):
            dados['inscricao'] = linha.strip()
            break
    
    # 3. TIPO - procura por palavras-chave
    if 'ADVOGADO' in texto_completo.upper():
        dados['tipo'] = 'Advogado'
    elif 'ESTAGIÁRIO' in texto_completo.upper():
        dados['tipo'] = 'Estagiário'
    elif 'SUPLEMENTAR' in texto_completo.upper():
        dados['tipo'] = 'Suplementar'
    
    # 4. SECCIONAL - UF específica que aparece logo após a inscrição
    # Procura pelos estados brasileiros conhecidos
    uf_pattern = r'\b([A-Z]{2})\b'
    matches_uf = re.finditer(uf_pattern, texto_completo)
    
    # Estados válidos BR
    estados_validos = {
        'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
        'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
        'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
    }
    
    for match in matches_uf:
        uf = match.group(1)
        if uf in estados_validos:
            # Preferir o que aparece logo depois de um número (inscrição) ou depois de "Seccional"
            contexto_ante = texto_completo[max(0, match.start()-20):match.start()]
            if 'Seccional' in contexto_ante or re.search(r'\d', contexto_ante):
                dados['seccional'] = uf
                break
    
    # Se não encontrou, tenta o primeiro estado válido encontrado
    if not dados['seccional']:
        for match in matches_uf:
            if match.group(1) in estados_validos:
                dados['seccional'] = match.group(1)
                break
    
    # 5. SUBSEÇÃO - procura por "CONSELHO" + estado
    subsec_match = re.search(
        r'(CONSELHO\s+SECCIONAL[^\n]*(?:RN|RIO\s+GRANDE\s+DO\s+NORTE)?)',
        texto_completo,
        re.IGNORECASE
    )
    if subsec_match:
        # Limpar: remover "Endereço Profissional" se estiver appendado
        subsec_raw = subsec_match.group(1).replace('\n', ' ').strip()
        # Cortar quando encontrar a próxima seção
        subsec_clean = re.sub(r'\s+(Endereço|Telefone|situacao|E-mail).*', '', subsec_raw, flags=re.IGNORECASE)
        dados['subseccao'] = subsec_clean.strip()
    
    # 6. ENDEREÇO - procura por RUA, AV, etc
    endereco_pattern = r'(RUA|AV(?:ENIDA)?|PRAÇA|TRAVESSA|TV|R\.)\s+[^,\n]*'
    endereco_match = re.search(endereco_pattern, texto_completo, re.IGNORECASE)
    
    if endereco_match:
        # Ampliar contexto para pegar rua + número + bairro + cidade
        start = endereco_match.start()
        # Pegar até encontrar RN ou CEP
        resto_texto = texto_completo[start:]
        
        # Procurar limite (encontra RN, 59020, ou quebra de linha significativa)
        fim = len(resto_texto)
        
        # Procurar por RN, CEP ou outras quebras
        match_fim = re.search(r'\b(RN|59020|NATAL|Telefone|situacao)', resto_texto, re.IGNORECASE)
        if match_fim:
            fim = match_fim.start()
        
        endereco_bruto = resto_texto[:fim].strip()
        
        # Limpar quebras de linha e espaços múltiplos
        endereco_limpo = ' '.join(endereco_bruto.split())
        dados['endereco'] = endereco_limpo
    
    # 7. TELEFONE - padrão (XX) XXXX-XXXX
    tel_pattern = r'\(?(\d{2})\)?\s*(\d{4,5})-?(\d{4})'
    tel_match = re.search(tel_pattern, texto_completo)
    
    if tel_match:
        dados['telefone'] = f"({tel_match.group(1)}) {tel_match.group(2)}-{tel_match.group(3)}"
    
    # 8. CEP - extras para complementar endereço
    cep_pattern = r'(\d{5})-?(\d{3,4})'
    cep_match = re.search(cep_pattern, texto_completo)
    if cep_match:
        dados['cep'] = f"{cep_match.group(1)}-{cep_match.group(2)}"
    
    # Limpar valores None e vazios
    dados = {k: v for k, v in dados.items() if v}
    
    return dados


def buscar_dados_completos_oab_com_ocr(
    numero: str,
    estado: str,
    session,
    url_base: str = "https://cna.oab.org.br"
):
    """
    Busca dados completos de um advogado OAB incluindo OCR da ficha.
    
    Retorna dict com todos os 7+ campos principais
    """
    import re
    import requests
    
    # Step 1: Obter CSRF
    resp = session.get(url_base + "/", timeout=15, headers={
        'User-Agent': 'Mozilla/5.0'
    })
    csrf_match = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', resp.text)
    if not csrf_match:
        return {"encontrado": False, "erro": "CSRF token não obtido"}
    csrf_token = csrf_match.group(1)
    
    # Step 2: Buscar
    payload = {
        "NomeAdvo": "",
        "Insc": numero,
        "Uf": estado.upper(),
        "TipoInsc": "1",
        "__RequestVerificationToken": csrf_token,
        "IsMobile": ""
    }
    
    resp_search = session.post(url_base + "/Home/Search", data=payload, timeout=15)
    
    try:
        search_data = resp_search.json()
    except:
        return {"encontrado": False, "erro": "Resposta inválida"}
    
    if not search_data.get('Data'):
        return {"encontrado": False, "erro": "Não encontrado"}
    
    resultado = search_data['Data'][0]
    detail_url = resultado.get('DetailUrl', '')
    
    # Step 3: Get detail
    detail_url_full = url_base + detail_url
    resp_detail = session.get(detail_url_full, timeout=15)
    
    try:
        detail_data = resp_detail.json()
    except:
        return {"encontrado": False, "erro": "Erro ao obter detalhes"}
    
    render_url = detail_data['Data'].get('DetailUrl', '')
    
    # Step 4: Get ficha image
    render_full = url_base + render_url
    resp_render = session.get(render_full, timeout=15)
    
    if resp_render.status_code != 200:
        return {"encontrado": False, "erro": "Não conseguiu obter imagem"}
    
    # Step 5: OCR na imagem
    try:
        dados_ocr = extrair_dados_ficha_ocr(resp_render.content)
    except Exception as e:
        return {"encontrado": False, "erro": f"Erro no OCR: {str(e)}"}
    
    # Mesclar dados
    resultado_final = {
        "encontrado": True,
        "numero_inscricao": numero,
        "estado": estado.upper(),
        "tipo_inscricao": "Advogado",
        "fonte": "OAB-OCR",
    }
    
    resultado_final.update(dados_ocr)
    
    return resultado_final

