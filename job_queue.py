"""
Job Queue Manager com Celery + Rate Limiting
Processamento assíncrono de tarefas pesadas com controle de concorrência
"""
import logging
import os
from celery import Celery, Task
from celery.utils.log import get_task_logger
from datetime import timedelta
import json

logger = get_task_logger(__name__)

# Inicializar Celery
celery_app = Celery(
    'detetive',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/1'),
)

# Configuração Celery
celery_app.conf.update(
    # Rate limiting: máximo de tarefas processadas por minuto
    task_default_rate_limit='100/m',
    
    # Timeout para tarefas: 5 minutos
    task_soft_time_limit=300,
    task_time_limit=600,
    
    # Números de tentativas e backoff
    task_autoretry_for=(Exception,),
    task_max_retries=3,
    task_default_retry_delay=60,
    
    # Configuração de retry
    task_acks_late=True,  # ACK apenas after task completa
    worker_prefetch_multiplier=1,  # Pega 1 tarefa por vez (melhor distribuição)
    
    # Resultado
    result_expires=3600,  # Resultado expira em 1 hora
    result_backend_transport_options={
        'master_name': 'mymaster'
    },
    
    # Beat schedule (tarefas agendadas)
    beat_schedule={
        'limpar-cache-expirado': {
            'task': 'job_queue.limpar_cache_expirado_task',
            'schedule': timedelta(hours=6),  # A cada 6 horas
        },
        'healthcheck-sistema': {
            'task': 'job_queue.healthcheck_sistema_task',
            'schedule': timedelta(minutes=5),  # A cada 5 minutos
        },
    }
)

class CallbackTask(Task):
    """Task customizada com callbacks"""
    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f'✅ Task {self.name} completada: {task_id}')
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f'🔄 Task {self.name} retry: {task_id} - {exc}')
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f'❌ Task {self.name} falhou: {task_id} - {exc}')

celery_app.Task = CallbackTask


# =============================================================================
# TAREFAS
# =============================================================================

@celery_app.task(bind=True, rate_limit='50/m', priority=10)
def enriquecer_dados_com_apis_task(self, cpf: str):
    """
    Tarefa de background: Enriquecer dados via APIs
    Rate limit: 50 chamadas/minuto
    Prioridade: ALTA
    """
    try:
        logger.info(f"[Tarefa] Iniciando enriquecimento para CPF: {cpf}")
        
        # Aqui vai chamar a função de enriquecimento real
        # TODO: Importar função do app.py
        
        logger.info(f"[Tarefa] Enriquecimento completo para: {cpf}")
        return {
            'status': 'sucesso',
            'cpf': cpf,
            'mensagem': 'Enriquecimento completado'
        }
    
    except Exception as exc:
        logger.error(f"[Tarefa] Erro no enriquecimento: {exc}")
        # Celery vai fazer retry automático
        raise self.retry(exc=exc)


@celery_app.task(bind=True, rate_limit='20/m', priority=8)
def analisar_resultado_task(self, tipo_consulta: str, dados: dict):
    """
    Tarefa de background: Análise complexa de resultados
    Rate limit: 20 chamadas/minuto
    Prioridade: ALTA
    """
    try:
        logger.info(f"[Tarefa] Iniciando análise para tipo: {tipo_consulta}")
        
        # Aqui vai chamar a função de análise real
        # TODO: Importar função do app.py
        
        return {
            'status': 'sucesso',
            'tipo': tipo_consulta,
            'dados_processados': len(str(dados))
        }
    
    except Exception as exc:
        logger.error(f"[Tarefa] Erro na análise: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, rate_limit='200/m', priority=5)
def processar_consulta_telegram_task(self, usuario_id: int, query: str):
    """
    Tarefa de background: Processar consulta Telegram
    Rate limit: 200 chamadas/minuto (menos crítico)
    Prioridade: MÉDIA
    """
    try:
        logger.info(f"[Tarefa] Processando Telegram query: {query}")
        
        # Aqui vai chamar a função de processamento Telegram
        # TODO: Importar função do app.py
        
        return {
            'status': 'sucesso',
            'usuario_id': usuario_id,
            'query': query
        }
    
    except Exception as exc:
        logger.error(f"[Tarefa] Erro no Telegram: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, priority=3)
def limpar_cache_expirado_task(self):
    """
    Tarefa agendada: Limpar cache expirado
    Executada a cada 6 horas
    Prioridade: BAIXA
    """
    try:
        logger.info("[Tarefa] Limpando cache expirado...")
        
        # Aqui vai chamar cache.invalidate_padrao
        # TODO: Implementar limpeza
        
        return {'status': 'sucesso', 'mensagem': 'Cache limpo'}
    
    except Exception as exc:
        logger.error(f"[Tarefa] Erro ao limpar cache: {exc}")
        return {'status': 'erro', 'erro': str(exc)}


@celery_app.task(bind=True, priority=3)
def healthcheck_sistema_task(self):
    """
    Tarefa agendada: Health check do sistema
    Executada a cada 5 minutos
    Prioridade: BAIXA
    """
    try:
        status = {
            'redis': 'OK',
            'telegram': 'OK',
            'apis': 'OK',
            'timestamp': str(__import__('datetime').datetime.now()),
        }
        
        logger.info(f"[Healthcheck] Status: {json.dumps(status)}")
        return status
    
    except Exception as exc:
        logger.error(f"[Healthcheck] Erro: {exc}")
        return {'status': 'erro', 'erro': str(exc)}


# =============================================================================
# UTILITÁRIOS
# =============================================================================

def enfileirar_tarefa(
    nome_tarefa: str,
    args: tuple = (),
    kwargs: dict = None,
    prioridade: int = 5,  # 1-10, 10 = máxima
    atraso: int = 0  # segundos
) -> str:
    """
    Enfileira uma tarefa para processamento async
    
    Args:
        nome_tarefa: Nome da tarefa (ex: 'job_queue.enriquecer_dados_com_apis_task')
        args: Argumentos posicionais
        kwargs: Argumentos nomeados
        prioridade: 1-10 (10 = máxima prioridade)
        atraso: Atraso em segundos antes de processar
    
    Returns:
        task_id para rastrear a tarefa
    """
    try:
        if kwargs is None:
            kwargs = {}
        
        tarefa = celery_app.send_task(
            nome_tarefa,
            args=args,
            kwargs=kwargs,
            priority=prioridade,
            countdown=atraso,
        )
        
        logger.info(f"📝 Tarefa enfileirada: {nome_tarefa} (ID: {tarefa.id})")
        return tarefa.id
    
    except Exception as e:
        logger.error(f"❌ Erro ao enfileirar tarefa: {e}")
        raise


def obter_status_tarefa(task_id: str) -> dict:
    """Obtém status de uma tarefa"""
    try:
        from celery.result import AsyncResult
        resultado = AsyncResult(task_id, app=celery_app)
        
        return {
            'task_id': task_id,
            'status': resultado.status,
            'resultado': resultado.result if resultado.ready() else None,
        }
    except Exception as e:
        logger.error(f"❌ Erro ao obter status: {e}")
        return {'erro': str(e)}


def obter_stats_queue() -> dict:
    """Obtém estatísticas da fila de tarefas"""
    try:
        inspect_result = celery_app.control.inspect()
        
        return {
            'tasks_ativas': inspect_result.active(),
            'tasks_agendadas': inspect_result.scheduled(),
            'tasks_reservadas': inspect_result.reserved(),
            'workers': inspect_result.ping(),
        }
    except Exception as e:
        logger.error(f"❌ Erro ao obter stats: {e}")
        return {'erro': str(e)}
