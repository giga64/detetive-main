"""
Cache Manager com Redis
Implementa cache inteligente com TTL dinâmico baseado no tipo de dado
"""
import json
import hashlib
import redis
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

class CacheManager:
    """Gerenciador de cache com Redis"""
    
    # TTL (Time To Live) por tipo de consulta em horas
    CACHE_TTL = {
        'cpf': 168,        # 7 dias
        'cnpj': 168,       # 7 dias
        'nome': 72,        # 3 dias
        'placa': 24,       # 1 dia
        'oab': 168,        # 7 dias
        'endereco': 24,    # 1 dia
        'telefone': 48,    # 2 dias
    }
    
    # Versão do schema - incrementar quando mudança incompatível ocorrer
    CACHE_VERSION = 2
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info(f"✅ Cache Redis conectado: {redis_url}")
        except Exception as e:
            logger.error(f"❌ Falha ao conectar Redis: {e}")
            self.redis_client = None
    
    def _gerar_chave_cache(self, tipo_consulta: str, identificador: str) -> str:
        """Gera chave uniforme para cache"""
        # Hash do identificador para normalizar (CPF com/sem dígitos, etc)
        hash_id = hashlib.md5(str(identificador).encode()).hexdigest()[:8]
        chave = f"consulta:v{self.CACHE_VERSION}:{tipo_consulta}:{hash_id}"
        return chave
    
    def _obter_ttl(self, tipo_consulta: str) -> int:
        """Retorna TTL em segundos baseado no tipo"""
        horas = self.CACHE_TTL.get(tipo_consulta, 24)
        return horas * 3600
    
    async def get(self, tipo_consulta: str, identificador: str) -> Optional[dict]:
        """Obtém resultado do cache"""
        if not self.redis_client:
            return None
        
        try:
            chave = self._gerar_chave_cache(tipo_consulta, identificador)
            valor = self.redis_client.get(chave)
            
            if valor:
                logger.debug(f"🔄 Cache HIT: {chave}")
                return json.loads(valor)
            
            logger.debug(f"🔄 Cache MISS: {chave}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Erro ao ler cache: {e}")
            return None
    
    async def set(
        self, 
        tipo_consulta: str, 
        identificador: str, 
        dados: dict,
        ttl_override: Optional[int] = None
    ) -> bool:
        """Salva resultado no cache"""
        if not self.redis_client:
            return False
        
        try:
            chave = self._gerar_chave_cache(tipo_consulta, identificador)
            ttl = ttl_override or self._obter_ttl(tipo_consulta)
            
            valor_json = json.dumps(dados, default=str, ensure_ascii=False)
            self.redis_client.setex(
                chave,
                ttl,
                valor_json
            )
            
            logger.debug(f"💾 Cache SET: {chave} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao salvar cache: {e}")
            return False
    
    async def invalidate(self, tipo_consulta: str, identificador: str) -> bool:
        """Invalida cache específico"""
        if not self.redis_client:
            return False
        
        try:
            chave = self._gerar_chave_cache(tipo_consulta, identificador)
            self.redis_client.delete(chave)
            logger.info(f"🗑️ Cache INVALIDADO: {chave}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao invalidar cache: {e}")
            return False
    
    async def invalidate_padrao(self, padrao: str) -> int:
        """Invalida múltiplas chaves por padrão (ex: 'consulta:v2:cpf:*')"""
        if not self.redis_client:
            return 0
        
        try:
            chaves = self.redis_client.keys(padrao)
            if chaves:
                deletados = self.redis_client.delete(*chaves)
                logger.info(f"🗑️ Cache INVALIDADO ({deletados}): {padrao}")
                return deletados
            return 0
        except Exception as e:
            logger.warning(f"⚠️ Erro ao invalidar padrão: {e}")
            return 0
    
    async def clear_all(self) -> bool:
        """Limpa TODO o cache (usar com cuidado!)"""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.flushdb()
            logger.warning("🗑️ Cache COMPLETAMENTE LIMPO")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Erro ao limpar cache: {e}")
            return False
    
    async def get_stats(self) -> dict:
        """Retorna estatísticas do cache"""
        if not self.redis_client:
            return {}
        
        try:
            info = self.redis_client.info('stats')
            keys_consulta = len(self.redis_client.keys('consulta:*'))
            
            return {
                'total_keys': keys_consulta,
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
                'memory_used': info.get('used_memory_human', 'N/A'),
            }
        except Exception as e:
            logger.warning(f"⚠️ Erro ao obter stats: {e}")
            return {}


# Instância global
cache_manager = None

def init_cache(redis_url: str = "redis://localhost:6379/0") -> CacheManager:
    """Inicializa o cache manager"""
    global cache_manager
    cache_manager = CacheManager(redis_url)
    return cache_manager

def decorator_cache(tipo_consulta: str):
    """Decorator para cachear automaticamente chamadas de função"""
    def decorator(func):
        @wraps(func)
        async def wrapper(identificador: str, *args, **kwargs):
            # Tentar obter do cache
            resultado_cache = await cache_manager.get(tipo_consulta, identificador)
            if resultado_cache:
                return resultado_cache
            
            # Se não estiver em cache, chamar função
            resultado = await func(identificador, *args, **kwargs)
            
            # Salvar em cache
            if resultado:
                await cache_manager.set(tipo_consulta, identificador, resultado)
            
            return resultado
        
        return wrapper
    return decorator
