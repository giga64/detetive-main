"""
Script robusto para extrair dados do Portal da Transparência
- Remuneração de servidores (CPF)
- Pagamentos por CNPJ favorecido
"""

import requests
import pandas as pd
import time
from typing import List, Dict, Optional
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PortalTransparenciaAPI:
    """Cliente para Portal da Transparência com tratamento de paginação e dados"""
    
    def __init__(self, api_token: str, base_url: str = "https://api.portaldatransparencia.gov.br"):
        """
        Inicializar cliente da API
        
        Args:
            api_token: Token/chave de autenticação da API
            base_url: URL base da API (padrão: Portal da Transparência oficial)
        """
        self.api_token = api_token
        self.base_url = base_url
        self.headers = {
            "Accept": "application/json",
            "api-token": api_token
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.rate_limit_delay = 0.5  # segundos entre requisições
    
    def _converter_valor_monetario(self, valor: any) -> float:
        """
        Converter valor monetário (string ou número) para float
        
        Suporta formatos:
        - "1.250,50" → 1250.50
        - "1250.50" → 1250.50
        - "1250,50" → 1250.50
        - 1250.50 → 1250.50
        - None → 0.0
        
        Args:
            valor: Valor em qualquer formato
            
        Returns:
            float: Valor convertido
        """
        if valor is None or valor == "":
            return 0.0
        
        if isinstance(valor, (int, float)):
            return float(valor)
        
        # Converter para string e limpar
        valor_str = str(valor).strip()
        
        # Remover espaços e símbolo de moeda
        valor_str = valor_str.replace("R$", "").replace(" ", "")
        
        # Detectar formato: brasileiro (1.250,50) ou americano (1250.50)
        if "," in valor_str:
            # Formato brasileiro: remover pontos, substituir vírgula por ponto
            valor_str = valor_str.replace(".", "").replace(",", ".")
        
        try:
            return float(valor_str)
        except ValueError:
            logger.warning(f"Não foi possível converter valor: {valor}")
            return 0.0
    
    def _normalizar_dataframe(self, df: pd.DataFrame, colunas_monetarias: List[str] = None) -> pd.DataFrame:
        """
        Normalizar DataFrame com tratamento de colunas monetárias
        
        Args:
            df: DataFrame original
            colunas_monetarias: Lista de nomes de colunas que contêm valores monetários
            
        Returns:
            pd.DataFrame: DataFrame normalizado
        """
        if df.empty:
            return df
        
        # Converter colunas monetárias para float
        if colunas_monetarias:
            for coluna in colunas_monetarias:
                if coluna in df.columns:
                    df[coluna] = df[coluna].apply(self._converter_valor_monetario)
        else:
            # Auto-detectar colunas monetárias (contêm "valor", "remuner", "pagamento", etc)
            colunas_suspeitas = [col for col in df.columns if any(
                palavra in col.lower() for palavra in 
                ["valor", "remuner", "pagamento", "salario", "bonus", "auxilio"]
            )]
            for coluna in colunas_suspeitas:
                try:
                    df[coluna] = df[coluna].apply(self._converter_valor_monetario)
                except:
                    pass
        
        return df
    
    def buscar_remuneracao_cpf(
        self, 
        cpfs: List[str], 
        mes_ano: str,
        timeout: int = 15
    ) -> pd.DataFrame:
        """
        Extrair dados de remuneração de servidor público por CPF
        
        Paginação automática até lista vazia
        
        Args:
            cpfs: Lista de CPFs (ex: ["11122233344", "55566677788"])
            mes_ano: Mês e ano (ex: "202401" para janeiro 2024)
            timeout: Tempo limite para requisição em segundos
            
        Returns:
            pd.DataFrame: Dados consolidados de todos os CPFs
        """
        logger.info(f"Iniciando busca de remuneração para {len(cpfs)} CPF(s) - {mes_ano}")
        
        todos_dados = []
        
        for cpf in cpfs:
            logger.info(f"Processando CPF: {cpf}")
            
            # Limpar CPF (remover caracteres especiais)
            cpf_limpo = ''.join(c for c in cpf if c.isdigit())
            
            pagina = 1
            tempo_inicio = time.time()
            
            while True:
                try:
                    # Construir URL
                    url = f"{self.base_url}/api-v1/servidores/remuneracao"
                    params = {
                        "cpf": cpf_limpo,
                        "mesAno": mes_ano,
                        "pagina": pagina
                    }
                    
                    logger.debug(f"Requisição: {url} | Parâmetros: {params}")
                    
                    # Fazer requisição
                    response = self.session.get(
                        url,
                        params=params,
                        timeout=timeout
                    )
                    response.raise_for_status()
                    
                    # Parsear resposta
                    dados_pagina = response.json()
                    
                    # Verificar se é lista vazia (final da paginação)
                    if isinstance(dados_pagina, list):
                        if len(dados_pagina) == 0:
                            logger.info(f"CPF {cpf}: Fim da paginação na página {pagina - 1}")
                            break
                        todos_dados.extend(dados_pagina)
                    elif isinstance(dados_pagina, dict):
                        # Se retornar dict com 'data' ou 'items'
                        items = dados_pagina.get('data', dados_pagina.get('items', []))
                        if not items:
                            logger.info(f"CPF {cpf}: Fim da paginação na página {pagina - 1}")
                            break
                        todos_dados.extend(items if isinstance(items, list) else [items])
                    
                    logger.info(f"CPF {cpf}: Página {pagina} - {len(dados_pagina) if isinstance(dados_pagina, list) else 'dict'} registros")
                    
                    pagina += 1
                    
                    # Rate limiting
                    time.sleep(self.rate_limit_delay)
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Erro na requisição (CPF {cpf}, página {pagina}): {str(e)}")
                    break
                except Exception as e:
                    logger.error(f"Erro ao processar dados (CPF {cpf}, página {pagina}): {str(e)}")
                    break
            
            tempo_total = time.time() - tempo_inicio
            logger.info(f"CPF {cpf}: {len([d for d in todos_dados if d.get('cpf') == cpf_limpo])} registros obtidos em {tempo_total:.2f}s")
        
        # Converter para DataFrame
        if not todos_dados:
            logger.warning("Nenhum dado obtido")
            return pd.DataFrame()
        
        df = pd.DataFrame(todos_dados)
        
        # Colunas monetárias comuns em remuneração
        colunas_monetarias = [
            'salario', 'valor', 'remuneracao', 'bonus', 
            'auxilio', 'gratificacao', 'abono', 'deducao',
            'vale_refeicao', 'vale_transporte', 'insalubridade'
        ]
        
        df = self._normalizar_dataframe(df, colunas_monetarias)
        
        logger.info(f"DataFrame final: {len(df)} linhas, {len(df.columns)} colunas")
        
        return df
    
    def buscar_pagamentos_cnpj(
        self,
        cnpj: str,
        ano: str = None,
        timeout: int = 15
    ) -> pd.DataFrame:
        """
        Extrair dados de pagamentos recebidos por CNPJ favorecido
        
        Paginação automática até lista vazia
        
        Args:
            cnpj: CNPJ favorecido (ex: "09464032000112")
            ano: Ano opcional (ex: "2024")
            timeout: Tempo limite para requisição em segundos
            
        Returns:
            pd.DataFrame: Dados consolidados de pagamentos
        """
        logger.info(f"Iniciando busca de pagamentos para CNPJ: {cnpj}")
        
        # Limpar CNPJ
        cnpj_limpo = ''.join(c for c in cnpj if c.isdigit())
        
        todos_dados = []
        pagina = 1
        tempo_inicio = time.time()
        
        while True:
            try:
                # Construir URL
                url = f"{self.base_url}/api-v1/despesas/documentos-por-favorecido"
                params = {
                    "codigo": cnpj_limpo,
                    "pagina": pagina
                }
                
                # Adicionar ano se fornecido
                if ano:
                    params["ano"] = ano
                
                logger.debug(f"Requisição: {url} | Parâmetros: {params}")
                
                # Fazer requisição
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout
                )
                response.raise_for_status()
                
                # Parsear resposta
                dados_pagina = response.json()
                
                # Verificar se é lista vazia (final da paginação)
                if isinstance(dados_pagina, list):
                    if len(dados_pagina) == 0:
                        logger.info(f"CNPJ {cnpj}: Fim da paginação na página {pagina - 1}")
                        break
                    todos_dados.extend(dados_pagina)
                elif isinstance(dados_pagina, dict):
                    # Se retornar dict com 'data' ou 'items'
                    items = dados_pagina.get('data', dados_pagina.get('items', []))
                    if not items:
                        logger.info(f"CNPJ {cnpj}: Fim da paginação na página {pagina - 1}")
                        break
                    todos_dados.extend(items if isinstance(items, list) else [items])
                
                logger.info(f"CNPJ {cnpj}: Página {pagina} - {len(dados_pagina) if isinstance(dados_pagina, list) else 'dict'} registros")
                
                pagina += 1
                
                # Rate limiting
                time.sleep(self.rate_limit_delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Erro na requisição (CNPJ {cnpj}, página {pagina}): {str(e)}")
                break
            except Exception as e:
                logger.error(f"Erro ao processar dados (CNPJ {cnpj}, página {pagina}): {str(e)}")
                break
        
        tempo_total = time.time() - tempo_inicio
        logger.info(f"CNPJ {cnpj}: {len(todos_dados)} registros obtidos em {tempo_total:.2f}s")
        
        # Converter para DataFrame
        if not todos_dados:
            logger.warning("Nenhum dado obtido")
            return pd.DataFrame()
        
        df = pd.DataFrame(todos_dados)
        
        # Colunas monetárias comuns em despesas/pagamentos
        colunas_monetarias = [
            'valor', 'valor_liquido', 'valor_bruto', 'valor_documento',
            'valor_pagamento', 'valor_desconto', 'valor_diaria',
            'valor_empenho', 'valor_liquidacao'
        ]
        
        df = self._normalizar_dataframe(df, colunas_monetarias)
        
        logger.info(f"DataFrame final: {len(df)} linhas, {len(df.columns)} colunas")
        
        return df
    
    def salvar_dados(self, df: pd.DataFrame, caminho_arquivo: str, formato: str = 'csv') -> bool:
        """
        Salvar DataFrame em arquivo
        
        Args:
            df: DataFrame a salvar
            caminho_arquivo: Caminho do arquivo (ex: "dados.csv")
            formato: Formato ('csv', 'excel', 'json', 'parquet')
            
        Returns:
            bool: Sucesso da operação
        """
        try:
            if formato == 'csv':
                df.to_csv(caminho_arquivo, index=False, encoding='utf-8')
            elif formato == 'excel':
                df.to_excel(caminho_arquivo, index=False)
            elif formato == 'json':
                df.to_json(caminho_arquivo, orient='records', force_ascii=False)
            elif formato == 'parquet':
                df.to_parquet(caminho_arquivo, index=False)
            
            logger.info(f"Dados salvos em: {caminho_arquivo}")
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar arquivo: {str(e)}")
            return False
    
    def obter_estatisticas(self, df: pd.DataFrame) -> Dict:
        """
        Gerar estatísticas do DataFrame
        
        Args:
            df: DataFrame para análise
            
        Returns:
            dict: Dicionário com estatísticas
        """
        if df.empty:
            return {"erro": "DataFrame vazio"}
        
        stats = {
            "total_registros": len(df),
            "colunas": list(df.columns),
            "tipos_dados": df.dtypes.to_dict(),
        }
        
        # Estatísticas para colunas numéricas
        for coluna in df.select_dtypes(include=['float64', 'int64']).columns:
            stats[f"{coluna}_stats"] = {
                "minimo": float(df[coluna].min()),
                "maximo": float(df[coluna].max()),
                "media": float(df[coluna].mean()),
                "mediana": float(df[coluna].median()),
                "soma": float(df[coluna].sum()),
            }
        
        return stats


# ============================================================================
# EXEMPLOS DE USO
# ============================================================================

if __name__ == "__main__":
    # Configurar chave de API
    API_TOKEN = "876beb4baf6996f08b5149caa7fe5a7d"  # ← Chave do Portal da Transparência
    
    # Criar cliente
    cliente = PortalTransparenciaAPI(api_token=API_TOKEN)
    
    # EXEMPLO 1: Extrair remuneração de CPFs
    print("\n" + "="*80)
    print("EXEMPLO 1: Remuneração de Servidores (CPF)")
    print("="*80)
    
    cpfs = [
        "45317828791",  # CPF exemplo
        # "11122233344",  # Adicionar mais CPFs conforme necessário
    ]
    mes_ano = "202401"  # Janeiro 2024
    
    df_remuneracao = cliente.buscar_remuneracao_cpf(cpfs, mes_ano)
    
    if not df_remuneracao.empty:
        print("\nPrimeiras linhas:")
        print(df_remuneracao.head())
        
        print("\nInfo do DataFrame:")
        print(df_remuneracao.info())
        
        print("\nEstatísticas:")
        stats = cliente.obter_estatisticas(df_remuneracao)
        for chave, valor in stats.items():
            if not chave.startswith('t'):  # Skip 'tipos_dados'
                print(f"  {chave}: {valor}")
        
        # Salvar dados
        cliente.salvar_dados(df_remuneracao, "remuneracao_output.csv", formato='csv')
    else:
        print("Nenhum dado obtido para remuneração")
    
    # EXEMPLO 2: Extrair pagamentos por CNPJ
    print("\n" + "="*80)
    print("EXEMPLO 2: Pagamentos Recebidos (CNPJ)")
    print("="*80)
    
    cnpj = "09464032000112"
    ano = "2024"
    
    df_pagamentos = cliente.buscar_pagamentos_cnpj(cnpj, ano)
    
    if not df_pagamentos.empty:
        print("\nPrimeiras linhas:")
        print(df_pagamentos.head())
        
        print("\nInfo do DataFrame:")
        print(df_pagamentos.info())
        
        print("\nEstatísticas:")
        stats = cliente.obter_estatisticas(df_pagamentos)
        for chave, valor in stats.items():
            if not chave.startswith('t'):  # Skip 'tipos_dados'
                print(f"  {chave}: {valor}")
        
        # Salvar dados
        cliente.salvar_dados(df_pagamentos, "pagamentos_output.csv", formato='csv')
    else:
        print("Nenhum dado obtido para pagamentos")
