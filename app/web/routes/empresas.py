from flask import Blueprint, session, redirect, url_for, request, jsonify
from app.web.routes.decorators import login_required
from app.web.routes.api_responses import ok, error
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

bp = Blueprint('empresas', __name__)

@bp.route('/empresas/selecionar/<empresa_id>', methods=['POST'])
@login_required
def selecionar(empresa_id):
    """Define a empresa ativa na sessão."""
    client = db_adapter.get_client()
    if not client:
        return error("Banco de dados indisponível.", status_code=503, code="DB_UNAVAILABLE")
    
    # Verifica se a empresa existe
    resp = client.table('empresas').select('id, nome').eq('id', empresa_id).execute()
    if not resp.data:
        return error("Empresa não encontrada.", status_code=404, code="NOT_FOUND")
    
    empresa = resp.data[0]
    session['active_empresa'] = {
        'id': empresa['id'],
        'nome': empresa['nome']
    }
    
    logger.info(f"Empresa selecionada: {empresa['nome']} (ID: {empresa['id']})")
    return ok(data={"nome": empresa["nome"]})

@bp.route('/empresas/limpar', methods=['POST'])
@login_required
def limpar():
    """Remove a empresa ativa da sessão (ex: se foi deletada)."""
    session.pop('active_empresa', None)
    logger.info("Sessão de empresa limpa.")
    return ok()

@bp.route('/empresas/lista')
@login_required
def lista():
    """Retorna lista de empresas para o seletor."""
    client = db_adapter.get_client()
    if not client:
        return ok(data=[])
    
    resp = client.table('empresas').select('id, nome').order('nome').execute()
    return ok(data=resp.data or [])
