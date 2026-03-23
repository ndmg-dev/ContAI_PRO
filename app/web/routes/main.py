from flask import Blueprint, render_template, redirect, url_for, session
from app.web.routes.decorators import login_required
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    if session.get('user'):
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    client = db_adapter.get_client()
    stats = {
        'pendentes': 0,
        'documentos_mes': 0,
        'lancamentos_total': 0,
    }

    active_empresa = session.get('active_empresa', {})
    active_id = active_empresa.get('id')

    # Se não há empresa selecionada, retorna o dashboard zerado
    if not active_id or not client:
        return render_template('dashboard.html', stats=stats, user=session.get('user'))

    try:
        pendentes_resp = client.table('lancamentos').select('id', count='exact')\
            .eq('status', 'pendente').eq('empresa_id', active_id).execute()
        stats['pendentes'] = pendentes_resp.count or 0

        docs_resp = client.table('documentos').select('id', count='exact')\
            .eq('empresa_id', active_id).execute()
        stats['documentos_mes'] = docs_resp.count or 0

        lanc_resp = client.table('lancamentos').select('id', count='exact')\
            .eq('empresa_id', active_id).execute()
        stats['lancamentos_total'] = lanc_resp.count or 0

    except Exception as e:
        logger.exception(f"[Dashboard] error fetching stats: {e}")

    return render_template('dashboard.html', stats=stats, user=session.get('user'))
