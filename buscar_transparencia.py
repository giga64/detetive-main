"""
Integração com Portal da Transparência - Endpoints que funcionam
Utiliza chave de API: chave-api-dados
Base URL: http://api.portaldatransparencia.gov.br/api-de-dados
"""

import requests
import time
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PortalTransparencia:
    """Cliente para consumir APIs do Portal da Transparência"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "http://api.portaldatransparencia.gov.br/api-de-dados"
        self.headers = {
            "Accept": "application/json",
            "chave-api-dados": api_key
        }
        self.rate_limit_delay = 0.5  # segundos entre requisições
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Fazer requisição com tratamento de erros e rate limiting"""
        try:
            url = f"{self.base_url}{endpoint}"
            logger.info(f"🔍 GET {endpoint}")
            
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                time.sleep(self.rate_limit_delay)
                # Verificar se response está vazio (válido para alguns endpoints)
                if len(response.text.strip()) == 0:
                    return None
                try:
                    return response.json()
                except:
                    return None
            elif response.status_code == 403:
                logger.warning(f"⚠️ HTTP 403: Sem permissão para este dados")
                return None
            elif response.status_code == 404:
                logger.warning(f"⚠️ HTTP 404: Dados não encontrados")
                return None
            else:
                logger.warning(f"⚠️ HTTP {response.status_code}: {response.text[:100]}")
                return None
        except Exception as e:
            logger.error(f"❌ Erro na requisição: {str(e)}")
            return None
    
    def buscar_servidor_por_cpf(self, cpf: str) -> Dict[str, Any]:
        """
        Busca informações de servidor público por CPF
        Retorna dados de remuneração, situação, órgão, etc.
        """
        # Limpar CPF
        cpf_limpo = ''.join(c for c in cpf if c.isdigit())
        
        logger.info(f"📋 Buscando servidor com CPF: {cpf_limpo}")
        
        response = self._make_request(
            '/servidores',
            params={'cpf': cpf_limpo, 'pagina': 1}
        )
        
        if not response:
            return None
        
        # A API retorna uma lista ou um objeto
        if isinstance(response, list):
            dados = response
        elif isinstance(response, dict) and 'data' in response:
            dados = response['data']
        else:
            dados = response if isinstance(response, (list, dict)) else None
        
        if not dados:
            return None
        
        # Processar primeiro resultado
        if isinstance(dados, list) and len(dados) > 0:
            servidor = dados[0].get('servidor', {})
        else:
            servidor = dados.get('servidor', {}) if isinstance(dados, dict) else {}
        
        # Extrair informações relevantes
        try:
            pessoa = servidor.get('pessoa', {})
            lotacao = servidor.get('orgaoServidorLotacao', {})
            situacao = servidor.get('situacao', '')
            
            return {
                'encontrado': True,
                'nome': pessoa.get('nome', 'N/A'),
                'cpf_formatado': pessoa.get('cpfFormatado', 'N/A'),
                'tipo_servidor': servidor.get('tipoServidor', 'N/A'),
                'situacao': situacao,
                'orgao': lotacao.get('nome', 'N/A'),
                'sigla_orgao': lotacao.get('sigla', 'N/A'),
                'origem': 'Portal da Transparência - Servidores',
                'raw_data': servidor
            }
        except Exception as e:
            logger.error(f"❌ Erro ao processar dados: {e}")
            return None
    
    def buscar_bolsa_familia_por_cpf(self, cpf: str) -> List[Dict[str, Any]]:
        """
        Busca benefícios de Bolsa Família para um CPF
        """
        cpf_limpo = ''.join(c for c in cpf if c.isdigit())
        
        logger.info(f"💰 Buscando Bolsa Família para CPF: {cpf_limpo}")
        
        response = self._make_request(
            '/bolsa-familia-por-cpf-ou-nis',
            params={'cpf': cpf_limpo, 'pagina': 1}
        )
        
        if not response:
            return None
        
        if isinstance(response, list):
            beneficios = response
        elif isinstance(response, dict) and 'data' in response:
            beneficios = response['data']
        else:
            beneficios = []
        
        if not beneficios:
            return None
        
        # Processar benefícios
        resultado = []
        for benef in beneficios[:20]:  # Limitar a 20 registros
            try:
                valor_str = benef.get('valor', '0')
                valor = float(valor_str.replace(',', '.')) if valor_str else 0.0
                
                resultado.append({
                    'mes_ano': benef.get('mesAno', 'N/A'),
                    'valor': valor,
                    'valor_formatado': f"R$ {valor:.2f}",
                    'fonte': 'Bolsa Família',
                    'data_processamento': benef.get('dataProcessamento', 'N/A')
                })
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar benefício: {e}")
        
        return resultado if resultado else None
    
    def buscar_convenios_por_cnpj(self, cnpj: str) -> List[Dict[str, Any]]:
        """
        Busca convênios federais associados a um CNPJ
        """
        cnpj_limpo = ''.join(c for c in cnpj if c.isdigit())
        
        logger.info(f"📄 Buscando convênios para CNPJ: {cnpj_limpo}")
        
        # Convênios requer período de até 30 dias
        hoje = datetime.now()
        data_inicio = (hoje - timedelta(days=30)).strftime('%d/%m/%Y')
        data_fim = hoje.strftime('%d/%m/%Y')
        
        response = self._make_request(
            '/convenios',
            params={
                'cnpjConvenente': cnpj_limpo,
                'dataInicioVigencia': data_inicio,
                'dataFimVigencia': data_fim,
                'pagina': 1
            }
        )
        
        if not response:
            return None
        
        if isinstance(response, list):
            convenios = response
        elif isinstance(response, dict) and 'data' in response:
            convenios = response['data']
        else:
            convenios = []
        
        if not convenios:
            return None
        
        # Processar convênios
        resultado = []
        for conv in convenios[:20]:
            try:
                valor = conv.get('valorConvenio', 0)
                try:
                    valor = float(valor)
                except:
                    valor = 0.0
                
                resultado.append({
                    'nome': conv.get('nomeConvenio', 'N/A'),
                    'objeto': conv.get('objeto', 'N/A'),
                    'valor': valor,
                    'valor_formatado': f"R$ {valor:,.2f}".replace(',', '.'),
                    'concedente': conv.get('nomeConvenente', 'N/A'),
                    'data_assinatura': conv.get('dataAssinatura', 'N/A'),
                    'situacao': conv.get('situacao', 'N/A')
                })
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar convênio: {e}")
        
        return resultado if resultado else None
    
    def buscar_licitacoes_por_cnpj(self, cnpj: str, dias: int = 30) -> List[Dict[str, Any]]:
        """
        Busca licitações associadas a um CNPJ nos últimos N dias
        """
        cnpj_limpo = ''.join(c for c in cnpj if c.isdigit())
        
        logger.info(f"🏛️ Buscando licitações para CNPJ: {cnpj_limpo}")
        
        hoje = datetime.now()
        data_inicio = (hoje - timedelta(days=dias)).strftime('%d/%m/%Y')
        data_fim = hoje.strftime('%d/%m/%Y')
        
        response = self._make_request(
            '/licitacoes',
            params={
                'cnpj': cnpj_limpo,
                'dataInicio': data_inicio,
                'dataFim': data_fim,
                'pagina': 1
            }
        )
        
        if not response:
            return None
        
        if isinstance(response, list):
            licitacoes = response
        elif isinstance(response, dict) and 'data' in response:
            licitacoes = response['data']
        else:
            licitacoes = []
        
        if not licitacoes:
            return None
        
        # Processar licitações
        resultado = []
        for lic in licitacoes[:20]:
            try:
                resultado.append({
                    'numero': lic.get('numero', 'N/A'),
                    'orgao': lic.get('nomeOrgao', 'N/A'),
                    'objeto': lic.get('objeto', 'N/A'),
                    'modalidade': lic.get('modalidade', 'N/A'),
                    'data_edital': lic.get('dataEdital', 'N/A'),
                    'data_resultado': lic.get('dataResultado', 'N/A'),
                    'situacao': lic.get('situacao', 'N/A')
                })
            except Exception as e:
                logger.warning(f"⚠️ Erro ao processar licitação: {e}")
        
        return resultado if resultado else None
    
    def buscar_dados_pessoa_fisica(self, cpf: str) -> Dict[str, Any]:
        """
        Busca informações gerais de uma pessoa física
        Retorna: se é servidor, beneficiário, sancionado, etc.
        Endpoint: /pessoa-fisica
        """
        cpf_limpo = ''.join(c for c in cpf if c.isdigit())
        
        logger.info(f"📊 Buscando informações de pessoa física: {cpf_limpo}")
        
        response = self._make_request(
            '/pessoa-fisica',
            params={'cpf': cpf_limpo}
        )
        
        if not response:
            return None
        
        try:
            # Compilar informações
            info = {
                'encontrado': True,
                'nome': response.get('nome', 'N/A'),
                'cpf': response.get('cpf', 'N/A'),
                'nis': response.get('nis', 'N/A'),
            }
            
            # Verificar diferentes tipos de envolvimento
            envolvimentos = []
            
            if response.get('servidor'):
                envolvimentos.append('✅ Servidor Público')
            if response.get('servidorInativo'):
                envolvimentos.append('✅ Servidor Inativo')
            if response.get('pensionistaOuRepresentanteLegal'):
                envolvimentos.append('✅ Pensionista/Representante Legal')
            if response.get('beneficiarioDiarias'):
                envolvimentos.append('✅ Beneficiário de Diárias')
            if response.get('contratado'):
                envolvimentos.append('✅ Contratado')
            if response.get('permissionario'):
                envolvimentos.append('✅ Permissionário')
            
            # Benefícios sociais
            beneficios = []
            if response.get('favorecidoBolsaFamilia'):
                beneficios.append('Bolsa Família')
            if response.get('favorecidoNovoBolsaFamilia'):
                beneficios.append('Novo Bolsa Família')
            if response.get('favorecidoPeti'):
                beneficios.append('PETI')
            if response.get('favorecidoSafra'):
                beneficios.append('Seguro Safra')
            if response.get('favorecidoSeguroDefeso'):
                beneficios.append('Seguro Defeso')
            if response.get('favorecidoBpc'):
                beneficios.append('BPC (Benefício de Prestação Continuada)')
            if response.get('auxilioEmergencial'):
                beneficios.append('Auxílio Emergencial')
            if response.get('favorecidoAuxilioBrasil'):
                beneficios.append('Auxílio Brasil')
            if response.get('favorecidoAuxilioReconstrucao'):
                beneficios.append('Auxílio Reconstrução')
            
            # Despesas e transferências
            atividades = []
            if response.get('favorecidoDespesas'):
                atividades.append('📊 Favorecido por Despesas')
            if response.get('favorecidoTransferencias'):
                atividades.append('💰 Favorecido por Transferências')
            
            # Sanções
            sancoes = []
            if response.get('sancionadoCEIS'):
                sancoes.append('⚠️ Sancionado CEIS')
            if response.get('sancionadoCNEP'):
                sancoes.append('⚠️ Sancionado CNEP')
            if response.get('sancionadoCEAF'):
                sancoes.append('⚠️ Sancionado CEAF')
            
            # Participação em licitações
            if response.get('participanteLicitacao'):
                atividades.append('🏛️ Participante de Licitação')
            
            # Outros
            if response.get('emitiuNFe'):
                atividades.append('🧾 Emitiu NF-e')
            if response.get('instituidorPensao'):
                atividades.append('👴 Instituidor de Pensão')
            
            info['envolvimentos'] = envolvimentos
            info['beneficios'] = beneficios
            info['atividades'] = atividades
            info['sancoes'] = sancoes
            
            return info
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar dados de pessoa física: {e}")
            return None
    
    def buscar_despesas_por_cpf(self, cpf: str, mes_ano: str = None) -> Dict[str, Any]:
        """
        Busca despesas associadas a um CPF em um período específico
        mes_ano: formato "202401" ou None para últimas
        """
        cpf_limpo = ''.join(c for c in cpf if c.isdigit())
        
        logger.info(f"💸 Buscando despesas para CPF: {cpf_limpo}")
        
        params = {'cpf': cpf_limpo, 'pagina': 1}
        if mes_ano:
            params['mesAno'] = mes_ano
        
        response = self._make_request(
            '/despesas-por-beneficiario',
            params=params
        )
        
        if not response:
            return None
        
        if isinstance(response, list):
            despesas = response
        elif isinstance(response, dict) and 'data' in response:
            despesas = response['data']
        else:
            despesas = []
        
        if not despesas:
            return None
        
        try:
            resultado = {
                'encontrado': True,
                'total': len(despesas),
                'despesas': []
            }
            
            valor_total = 0
            for desp in despesas[:10]:
                try:
                    valor = float(desp.get('valor', 0) or 0)
                    valor_total += valor
                    
                    resultado['despesas'].append({
                        'tipo': desp.get('tipo', 'N/A'),
                        'descricao': desp.get('descricao', 'N/A')[:100],
                        'valor': valor,
                        'valor_formatado': f"R$ {valor:,.2f}".replace(',', '.'),
                        'data': desp.get('data', 'N/A'),
                        'orgao': desp.get('orgao', 'N/A')
                    })
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao processar despesa: {e}")
            
            resultado['valor_total'] = valor_total
            resultado['valor_total_formatado'] = f"R$ {valor_total:,.2f}".replace(',', '.')
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar despesas: {e}")
            return None
    
    def buscar_dados_pessoa_juridica(self, cnpj: str) -> Dict[str, Any]:
        """
        Busca informações gerais de uma empresa (Pessoa Jurídica)
        Retorna: razão social, fantasia, sanções, participações, etc.
        Endpoint: /pessoa-juridica
        """
        cnpj_limpo = ''.join(c for c in cnpj if c.isdigit())
        
        logger.info(f"🏢 Buscando informações de pessoa jurídica: {cnpj_limpo}")
        
        response = self._make_request(
            '/pessoa-juridica',
            params={'cnpj': cnpj_limpo}
        )
        
        if not response:
            return None
        
        try:
            # Compilar informações
            info = {
                'encontrado': True,
                'cnpj': response.get('cnpj', 'N/A'),
                'razao_social': response.get('razaoSocial', 'N/A'),
                'nome_fantasia': response.get('nomeFantasia', 'N/A'),
            }
            
            # Atividades/Negócios
            atividades = []
            
            if response.get('favorecidoDespesas'):
                atividades.append('Favorecido por Despesas')
            if response.get('possuiContratacao'):
                atividades.append('Possui Contratação')
            if response.get('convenios'):
                atividades.append('Convênios Celebrados')
            if response.get('favorecidoTransferencias'):
                atividades.append('Favorecido por Transferências')
            if response.get('participanteLicitacao'):
                atividades.append('Participante de Licitação')
            if response.get('emitiuNFe'):
                atividades.append('Emitiu NF-e')
            
            # Sanções (Muito importante!)
            sancoes = []
            if response.get('sancionadoCEPIM'):
                sancoes.append('Sancionada CEPIM (Cadastro de Pessoas Impedidas)')
            if response.get('sancionadoCEIS'):
                sancoes.append('Sancionada CEIS (Empresas Inidôneas)')
            if response.get('sancionadoCNEP'):
                sancoes.append('Sancionada CNEP (Punidas)')
            if response.get('sancionadoCEAF'):
                sancoes.append('Sancionada CEAF (Entidades Admin. Punidas)')
            
            # Renúncias Fiscais
            renuncia_fiscal = []
            if response.get('beneficiadoRenunciaFiscal'):
                renuncia_fiscal.append('Beneficiada por Renúncia Fiscal')
            if response.get('isentoImuneRenunciaFiscal'):
                renuncia_fiscal.append('Isenta/Imune Renúncia Fiscal')
            if response.get('habilitadoRenunciaFiscal'):
                renuncia_fiscal.append('Habilitada para Renúncia Fiscal')
            
            info['atividades'] = atividades
            info['sancoes'] = sancoes
            info['renuncia_fiscal'] = renuncia_fiscal
            
            return info
            
        except Exception as e:
            logger.error(f"❌ Erro ao processar dados de pessoa jurídica: {e}")
            return None


# Para testes, use a variável de ambiente TRANSPARENCIA_API_KEY
# Exemplo: export TRANSPARENCIA_API_KEY="sua_chave_aqui"
