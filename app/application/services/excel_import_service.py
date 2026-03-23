"""
Excel Import Pipeline
Ingests Excel spreadsheet (.xlsx/.xls) into the lancamentos table.
Does NOT attempt to auto-detect company — empresa_id is required.
"""
from app.infrastructure.supabase.client import db_adapter
from app.application.services.excel_parser import parse_excel
from app.application.services.regras_service import apply_classification_rules
from app.infrastructure.logger import logger


def import_excel(content: bytes, filename: str, empresa_id: str) -> dict:
    """
    Parse and insert an Excel spreadsheet into lancamentos.
    empresa_id is MANDATORY — no auto-registration here.
    """
    if not empresa_id:
        return {'status': 'erro', 'mensagem': 'Selecione uma empresa antes de importar a planilha.', 'inseridos': 0}

    client = db_adapter.get_client()
    if not client:
        return {'status': 'erro', 'mensagem': 'Banco de dados indisponível.', 'inseridos': 0}

    result = parse_excel(content)

    if result.get('error'):
        return {'status': 'erro', 'mensagem': result['error'], 'inseridos': 0}

    transactions = result.get('transactions', [])
    if not transactions:
        return {'status': 'aviso', 'mensagem': 'Nenhuma transação válida encontrada na planilha.', 'inseridos': 0}

    # Apply classification rules
    transactions = apply_classification_rules(client, transactions, empresa_id)

    inserted = 0
    for txn in transactions:
        txn['empresa_id'] = empresa_id
        try:
            client.table('lancamentos').insert(txn).execute()
            inserted += 1
        except Exception as e:
            logger.exception(f"[Import Excel] erro ao inserir: {e}")

    return {
        'status': 'ok',
        'arquivo': filename,
        'inseridos': inserted,
        'empresa_id': empresa_id,
        'origem': 'Excel',
    }
