"""
Server-Sent Events (SSE) Streaming
Permite streaming de resultados em tempo real para o frontend
"""
import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ConsultaStream:
    """Gerenciador de streaming para uma consulta"""
    
    def __init__(self, tipo_consulta: str, identificador: str):
        self.tipo_consulta = tipo_consulta
        self.identificador = identificador
        self.inicio = datetime.now()
        self.etapas_completadas = []
        self.errors = []
    
    async def stream_eventos(self) -> AsyncGenerator[str, None]:
        """
        Gera eventos SSE conforme resultados chegam
        Padrão: data: {json}\n\n
        """
        try:
            # Evento 1: Iniciando
            yield await self._emitir_evento(
                tipo='status',
                dados={
                    'mensagem': 'Iniciando consulta...',
                    'etapa': 'init',
                    'timestamp': self._timestamp(),
                }
            )
            
            # Evento 2: Consultando Telegram (mais rápido)
            yield await self._emitir_evento(
                tipo='status',
                dados={
                    'mensagem': 'Consultando Telegram...',
                    'etapa': 'telegram',
                    'timestamp': self._timestamp(),
                }
            )
            
            # Aguardar um pouco (simulando processamento real)
            await asyncio.sleep(0.5)
            
            # Evento 3: Resultados Telegram chegaram
            yield await self._emitir_evento(
                tipo='telegram',
                dados={
                    'mensagem': 'Dados Telegram obtidos',
                    'dados': {},  # Aqui viriam os dados reais
                    'timestamp': self._timestamp(),
                },
                critico=True
            )
            
            self.etapas_completadas.append('telegram')
            
            # Evento 4: Enriquecendo com APIs
            yield await self._emitir_evento(
                tipo='status',
                dados={
                    'mensagem': 'Enriquecendo com APIs...',
                    'etapa': 'enrichment',
                    'timestamp': self._timestamp(),
                }
            )
            
            await asyncio.sleep(1)
            
            # Evento 5: Dados de Endereço
            yield await self._emitir_evento(
                tipo='endereco',
                dados={
                    'mensagem': 'Endereços encontrados',
                    'dados': {},  # Dados reais
                    'timestamp': self._timestamp(),
                },
                critico=True
            )
            
            self.etapas_completadas.append('endereco')
            
            # Evento 6: Dados de Telefone
            yield await self._emitir_evento(
                tipo='telefone',
                dados={
                    'mensagem': 'Informações telefônicas',
                    'dados': {},
                    'timestamp': self._timestamp(),
                },
                critico=False
            )
            
            self.etapas_completadas.append('telefone')
            
            # Evento 7: Análise (opcional)
            yield await self._emitir_evento(
                tipo='status',
                dados={
                    'mensagem': 'Gerando análise...',
                    'etapa': 'analysis',
                    'timestamp': self._timestamp(),
                }
            )
            
            await asyncio.sleep(0.5)
            
            yield await self._emitir_evento(
                tipo='analytics',
                dados={
                    'mensagem': 'Análise completa',
                    'dados': {},
                    'timestamp': self._timestamp(),
                },
                critico=False
            )
            
            self.etapas_completadas.append('analysis')
            
            # Evento 8: Conclusão
            tempo_total = (datetime.now() - self.inicio).total_seconds()
            
            yield await self._emitir_evento(
                tipo='completo',
                dados={
                    'mensagem': 'Consulta concluída',
                    'etapas': self.etapas_completadas,
                    'tempo_total_segundos': tempo_total,
                    'timestamp': self._timestamp(),
                },
                critico=True
            )
        
        except Exception as e:
            logger.error(f"❌ Erro durante stream: {e}")
            self.errors.append(str(e))
            
            yield await self._emitir_evento(
                tipo='erro',
                dados={
                    'mensagem': f'Erro durante processamento: {str(e)}',
                    'timestamp': self._timestamp(),
                },
                critico=True
            )
    
    async def _emitir_evento(
        self,
        tipo: str,
        dados: Dict[str, Any],
        critico: bool = False
    ) -> str:
        """Formata e retorna um evento SSE"""
        evento = {
            'tipo': tipo,
            'dados': dados,
            'critico': critico,
            'id': len(self.etapas_completadas),
        }
        
        # Formato SSE: data: {json}\n\n
        evento_json = json.dumps(evento, default=str, ensure_ascii=False)
        return f"data: {evento_json}\n\n"
    
    def _timestamp(self) -> str:
        """Retorna timestamp formatado"""
        return datetime.now().isoformat()


# Funções auxiliares para uso no app.py

async def stream_consulta_completa(
    tipo_consulta: str,
    identificador: str,
    funcoes_dados: Dict[str, callable]
) -> AsyncGenerator[str, None]:
    """
    Stream completo de uma consulta com dados reais
    
    Args:
        tipo_consulta: Tipo de consulta (cpf, cnpj, etc)
        identificador: CPF, CNPJ, etc
        funcoes_dados: Dict com funções async que retornam dados de cada etapa
            Exemplo: {
                'telegram': async_func_telegram,
                'endereco': async_func_endereco,
                'telefone': async_func_telefone,
                'analysis': async_func_analise,
            }
    """
    stream = ConsultaStream(tipo_consulta, identificador)
    
    try:
        # Status inicial
        yield f"data: {json.dumps({{'tipo': 'init', 'mensagem': 'Iniciando consulta...'}})}\n\n"
        
        # Executar cada função de dados e emitir evento conforme termina
        for chave, funcao in funcoes_dados.items():
            try:
                yield f"data: {json.dumps({{'tipo': 'status', 'etapa': chave}})}\n\n"
                
                # Chamar função de forma assíncrona
                dados = await funcao(identificador)
                
                # Emitir dados obtidos
                evento = {
                    'tipo': chave,
                    'dados': dados,
                    'timestamp': datetime.now().isoformat(),
                }
                yield f"data: {json.dumps(evento, default=str, ensure_ascii=False)}\n\n"
                
                stream.etapas_completadas.append(chave)
            
            except Exception as e:
                logger.warning(f"⚠️ Erro em {chave}: {e}")
                
                evento_erro = {
                    'tipo': 'erro_etapa',
                    'etapa': chave,
                    'erro': str(e),
                    'timestamp': datetime.now().isoformat(),
                }
                yield f"data: {json.dumps(evento_erro)}\n\n"
                # Continuar com próxima etapa ao invés de falhar tudo
        
        # Status final
        tempo_total = (datetime.now() - stream.inicio).total_seconds()
        evento_final = {
            'tipo': 'completo',
            'etapas': stream.etapas_completadas,
            'tempo_total_segundos': round(tempo_total, 2),
            'timestamp': datetime.now().isoformat(),
        }
        yield f"data: {json.dumps(evento_final)}\n\n"
    
    except Exception as e:
        logger.error(f"❌ Erro geral no stream: {e}")
        evento_erro = {
            'tipo': 'erro_fatal',
            'mensagem': str(e),
            'timestamp': datetime.now().isoformat(),
        }
        yield f"data: {json.dumps(evento_erro)}\n\n"


# Para FastAPI + Starlette
def criar_sse_response(generator: AsyncGenerator[str, None]):
    """Cria resposta SSE para FastAPI"""
    from sse_starlette.sse import EventSourceResponse
    return EventSourceResponse(generator)
