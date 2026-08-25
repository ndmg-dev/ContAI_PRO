from flask import Blueprint, render_template, session, jsonify
from app.web.routes.decorators import login_required

bp = Blueprint('configuracoes', __name__)


@bp.route('/configuracoes')
@login_required
def index():
    return render_template('configuracoes.html', user=session.get('user'))


@bp.route('/api/configuracoes')
@login_required
def api_index():
    """JSON: { ok, data: { user: { id, email, name, avatar } } }"""
    return jsonify({'ok': True, 'data': {'user': session.get('user')}})
