from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from app.web.routes.decorators import login_required
from app.web.routes.request_context import get_active_empresa_id
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

bp = Blueprint('regras', __name__)


def _compute_regras(active_id: str) -> dict:
    client = db_adapter.get_client()
    regras = []
    contas = []
    if client:
        # Buscar contas contábeis para o dropdown
        resp_c = client.table('plano_contas') \
                       .select('id, codigo, descricao') \
                       .eq('empresa_id', active_id) \
                       .order('codigo') \
                       .execute()
        contas = resp_c.data or []

        # Buscar regras existentes
        resp_r = client.table('regras_classificacao') \
                       .select('*, plano_contas!conta_id(codigo, descricao)') \
                       .eq('empresa_id', active_id) \
                       .order('prioridade', desc=True) \
                       .execute()
        regras = resp_r.data or []
    return {'regras': regras, 'contas': contas}


@bp.route('/regras')
@login_required
def index():
    active_id = get_active_empresa_id()

    if not active_id:
        return redirect(url_for('documentos.index'))

    regras, contas = [], []
    try:
        data = _compute_regras(active_id)
        regras, contas = data['regras'], data['contas']
    except Exception as e:
        logger.error(f"Erro ao buscar regras ou contas: {e}")
        flash("Erro ao carregar as regras. Tente novamente.", "error")

    return render_template('regras.html', regras=regras, contas=contas)


@bp.route('/api/regras')
@login_required
def api_index():
    """JSON: { ok, data: { regras: [...], contas: [ { id, codigo, descricao } ] } }"""
    active_id = get_active_empresa_id()
    if not active_id:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada', 'code': 'NO_EMPRESA'}), 400
    try:
        data = _compute_regras(active_id)
    except Exception as e:
        logger.error(f"Erro ao buscar regras ou contas: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500
    return jsonify({'ok': True, 'data': data})


@bp.route('/regras', methods=['POST'])
@login_required
def save_regra():
    """Adiciona ou atualiza uma regra de classificação."""
    active_id = get_active_empresa_id()
    if not active_id:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada'}), 400

    data = request.get_json(silent=True) or {}
    tipo_regra = data.get('tipo_regra', '').strip().upper()
    padrao = data.get('padrao', '').strip()
    conta_id = data.get('conta_id', '').strip()
    prioridade = data.get('prioridade', 0)

    if not tipo_regra or not padrao or not conta_id:
        return jsonify({'ok': False, 'message': 'Tipo, Padrão e Conta Contábil são obrigatórios'}), 400

    client = db_adapter.get_client()
    if not client:
         return jsonify({'ok': False, 'message': 'Erro de conexão BD'}), 500

    payload = {
        'empresa_id': active_id,
        'tipo_regra': tipo_regra,
        'padrao': padrao,
        'conta_id': conta_id,
        'prioridade': int(prioridade)
    }
    
    regra_id = data.get('id')
    try:
        if regra_id:
            client.table('regras_classificacao').update(payload).eq('id', regra_id).execute()
        else:
            client.table('regras_classificacao').insert(payload).execute()
            
        return jsonify({'ok': True, 'message': 'Regra salva com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao salvar regra: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500

@bp.route('/regras/<regra_id>', methods=['DELETE'])
@login_required
def delete_regra(regra_id):
    active_id = get_active_empresa_id()
    if not active_id:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada'}), 400

    client = db_adapter.get_client()
    try:
        client.table('regras_classificacao').delete().eq('id', regra_id).eq('empresa_id', active_id).execute()
        return jsonify({'ok': True, 'message': 'Regra excluída.'})
    except Exception as e:
        logger.error(f"Erro ao excluir regra: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500
