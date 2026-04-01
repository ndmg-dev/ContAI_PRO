"""
Workflow Service
Manages the operational pipeline state machine:
Importação → Cruzamento → Resolução → Exceção → Finalização
"""
import os
from enum import Enum
from typing import Optional
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

# UUID sentinela para operações server-side (sem sessão de usuário ativa).
# Configure a variável SYSTEM_USER_ID no .env para um UUID válido da tabela auth.users,
# ou um UUID fixo caso sua RLS não faça join com auth.users.
_SYSTEM_USER_ID = os.environ.get('SYSTEM_USER_ID', '00000000-0000-0000-0000-000000000000')


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

    # Audit log é best-effort — não falha a operação se houver problema na tabela.
    # user_id é obrigatório (NOT NULL) — usamos o UUID do sistema para ops server-side.
    try:
        client.table('audit_logs').insert({
            'tp_origem': 'workflow',
            'acao': f'status_changed:{to_status.value}',
            'user_id': _SYSTEM_USER_ID,
            'detalhes': {
                'lancamento_id': lancamento_id,
                'novo_status': to_status.value,
                'notas': notas,
            },
        }).execute()
    except Exception as e:
        logger.warning(f"[Workflow] audit_log insert skipped: {e}")

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
