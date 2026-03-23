from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.web.routes.decorators import login_required
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

# Removido: /integracoes/onvio/sync-api
# Removido: /integracoes/save-onvio
