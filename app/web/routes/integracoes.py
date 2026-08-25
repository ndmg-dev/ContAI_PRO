from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from app.web.routes.decorators import login_required
from app.web.routes.request_context import get_active_empresa
from app.infrastructure.supabase.client import db_adapter

bp = Blueprint('integracoes', __name__)

@bp.route('/integracoes')
@login_required
def index():
    """Exibe apenas a página de informações de integrações."""
    active_empresa = session.get('active_empresa', {})
    if not active_empresa:
        return render_template('integracoes.html', empresa={})

    return render_template('integracoes.html', empresa=active_empresa)


@bp.route('/api/integracoes')
@login_required
def api_index():
    """JSON: { ok, data: { empresa: { id, nome } } }"""
    empresa = get_active_empresa()
    return jsonify({'ok': True, 'data': {'empresa': empresa}})

# Removido: /integracoes/onvio/sync-api
# Removido: /integracoes/save-onvio
