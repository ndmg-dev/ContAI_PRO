from flask import Blueprint, render_template, session
from app.web.routes.decorators import login_required

bp = Blueprint('configuracoes', __name__)


@bp.route('/configuracoes')
@login_required
def index():
    return render_template('configuracoes.html', user=session.get('user'))
