"""
Circuit Breaker Manager
Implementa proteção contra falhas em cascata com fallback automático
"""
import logging
from pybreaker import CircuitBreaker
from typing import Callable, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

class CircuitBreakerManager:
    """Gerenciador centralizado de circuit breakers"""
    
    def __init__(self):
        self.breakers = {}
    
    def criar_breaker(
        self,
        nome: str,
        fail_max: int = 5,
        reset_timeout: int = 60,
        listeners: list = None
    ) -> CircuitBreaker:
        """Cria um novo circuit breaker"""
        
        def listener_abrir():
            logger.warning(f"🔴 CIRCUIT BREAKER ABERTO: {nome}")
        
        def listener_fechar():
            logger.info(f"🟢 CIRCUIT BREAKER FECHADO: {nome}")
        
        def listener_meia_abertura():
            logger.info(f"🟡 CIRCUIT BREAKER MEIA-ABERTURA: {nome}")
        
        listeners_padrao = [
            listener_abrir,
            listener_fechar,
            listener_meia_abertura,
        ]
        
        if listeners:
            listeners_padrao.extend(listeners)
        
        breaker = CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            listeners=listeners_padrao
        )
        
        self.breakers[nome] = breaker
        logger.info(f"✅ Circuit Breaker criado: {nome}")
        
        return breaker
    
    def obter_breaker(self, nome: str) -> Optional[CircuitBreaker]:
        """Obtém circuit breaker existente"""
        return self.breakers.get(nome)
    
    async def chamar_com_fallback(
        self,
        nome: str,
        funcao_principal: Callable,
        fallback: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Chama função com circuit breaker e fallback automático
        
        Args:
            nome: Nome do circuit breaker
            funcao_principal: Função a chamar normalmente
            fallback: Função de fallback se circuit abrir
            *args, **kwargs: Argumentos para funcao_principal
        """
        breaker = self.obter_breaker(nome)
        if not breaker:
            logger.warning(f"⚠️ Circuit breaker não encontrado: {nome}")
            return await funcao_principal(*args, **kwargs)
        
        try:
            # Se é função async
            if asyncio.iscoroutinefunction(funcao_principal):
                resultado = await breaker.call(
                    lambda: asyncio.run(funcao_principal(*args, **kwargs))
                )
            else:
                resultado = breaker.call(funcao_principal, *args, **kwargs)
            
            return resultado
        
        except Exception as e:
            logger.error(f"❌ Erro na função principal ({nome}): {str(e)}")
            
            try:
                # Chamar fallback
                if asyncio.iscoroutinefunction(fallback):
                    resultado_fallback = await fallback(*args, **kwargs)
                else:
                    resultado_fallback = fallback(*args, **kwargs)
                
                logger.info(f"🔄 Usando fallback para: {nome}")
                return resultado_fallback
            
            except Exception as e_fallback:
                logger.error(f"❌ Erro no fallback ({nome}): {str(e_fallback)}")
                raise
    
    def status_todos(self) -> dict:
        """Retorna status de todos os circuit breakers"""
        return {
            nome: {
                'estado': 'ABERTO' if breaker.opened else ('MEIA-ABERTURA' if breaker.half_open else 'FECHADO'),
                'falhas': breaker.fail_counter,
                'sucesso': breaker.success_counter,
            }
            for nome, breaker in self.breakers.items()
        }


# Instância global
circuit_breaker_manager = CircuitBreakerManager()

# Criar circuit breakers para APIs principais
def inicializar_circuit_breakers():
    """Inicializa circuit breakers para as APIs principais"""
    
    # Telegram API
    circuit_breaker_manager.criar_breaker(
        'telegram_api',
        fail_max=5,
        reset_timeout=120
    )
    
    # Enrichment APIs
    circuit_breaker_manager.criar_breaker(
        'enrichment_api',
        fail_max=5,
        reset_timeout=180
    )
    
    # Telefonica/Vivo
    circuit_breaker_manager.criar_breaker(
        'telefonica_api',
        fail_max=3,
        reset_timeout=300
    )
    
    # Serasa
    circuit_breaker_manager.criar_breaker(
        'serasa_api',
        fail_max=3,
        reset_timeout=300
    )
    
    logger.info("✅ Todos os circuit breakers inicializados")
