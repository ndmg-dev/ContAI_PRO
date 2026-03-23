"""
Workflow Service
Manages the operational pipeline state machine:
Importação → Cruzamento → Resolução → Exceção → Finalização
"""
from enum import Enum
from typing import Optional
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger


class WorkflowStatus(str, Enum):
    """Must match the DB enum: status_processamento ('pendente','processando','concluido','erro','excecao')"""
    PENDENTE    = 'pendente'
    PROCESSANDO = 'processando'
    CONCLUIDO   = 'concluido'   # was 'finalizado' — fixed to match DB enum
    EXCECAO     = 'excecao'
    ERRO        = 'erro'


PIPELINE_STAGES = [
    ('importacao', 'Importação',  WorkflowStatus.PENDENTE),
    ('cruzamento', 'Cruzamento',  WorkflowStatus.PROCESSANDO),
    ('resolucao',  'Resolução',   WorkflowStatus.PROCESSANDO),
    ('excecao',    'Exceção',     WorkflowStatus.EXCECAO),
    ('finalizacao','Finalização', WorkflowStatus.CONCLUIDO),
]


def advance_lancamento(lancamento_id: str, to_status: WorkflowStatus, notas: str = '') -> bool:
    """Advances a lancamento to the next workflow stage, logging the transition."""
    client = db_adapter.get_client()
    if not client:
        return False

    try:
        client.table('lancamentos').update({
            'status': to_status.value,
        }).eq('id', lancamento_id).execute()
    except Exception as e:
        logger.exception(f"[Workflow] error updating lancamento {lancamento_id}: {e}")
        return False

    # Audit log is best-effort — don't fail the whole operation if table is missing
    try:
        client.table('audit_logs').insert({
            'tp_origem': 'workflow',
            'acao': f'status_changed:{to_status.value}',
            'detalhes': {
                'lancamento_id': lancamento_id,
                'novo_status': to_status.value,
                'notas': notas,
            },
        }).execute()
    except Exception as e:
        logger.warning(f"[Workflow] audit_log insert skipped (table may not exist): {e}")

    return True


def get_pipeline_counts() -> dict:
    """Returns count of lancamentos per pipeline stage."""
    client = db_adapter.get_client()
    if not client:
        return {}

    counts = {}
    for status in WorkflowStatus:
        try:
            resp = (
                client.table('lancamentos')
                .select('id', count='exact')
                .eq('status', status.value)
                .execute()
            )
            counts[status.value] = resp.count or 0
        except Exception:
            counts[status.value] = 0
    return counts


def marcar_excecao(lancamento_id: str, motivo: str) -> bool:
    """Marca um lançamento como exceção com um motivo."""
    return advance_lancamento(lancamento_id, WorkflowStatus.EXCECAO, motivo)


def finalizar_lancamento(lancamento_id: str) -> bool:
    """Marca um lançamento como concluído/conciliado."""
    return advance_lancamento(lancamento_id, WorkflowStatus.CONCLUIDO)
