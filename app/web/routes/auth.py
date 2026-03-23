"""
Auth Blueprint — Direct Google OAuth via requests_oauthlib
(Sem PKCE — compatível com qualquer configuração do Google Cloud Console)
"""
import os
import requests as http
from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from requests_oauthlib import OAuth2Session
from app.infrastructure.supabase.auth import validate_user_domain

bp = Blueprint('auth', __name__)

ALLOWED_DOMAIN = os.environ.get('ALLOWED_DOMAIN', 'mendoncagalvao.com.br')
AUTHORIZATION_BASE_URL = 'https://accounts.google.com/o/oauth2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
USERINFO_URL = 'https://www.googleapis.com/oauth2/v3/userinfo'
SCOPES = ['openid', 'email', 'profile']

# Allow HTTP only in development (avoid weakening production defaults)
if os.environ.get('APP_ENV', '').strip().lower() != 'production':
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')


def _redirect_uri():
    app_url = os.environ.get('APP_URL', 'http://localhost:5000').rstrip('/')
    return f'{app_url}/auth/google-callback'


@bp.route('/login')
def login():
    if session.get('user'):
        return redirect(url_for('main.dashboard'))
    has_google = bool(os.environ.get('GOOGLE_CLIENT_ID', '').strip())
    return render_template('auth/login.html', has_google=has_google)


@bp.route('/google')
def google_oauth():
    """Gera URL OAuth do Google e redireciona."""
    client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    if not client_id:
        flash('GOOGLE_CLIENT_ID não configurado no .env', 'error')
        return redirect(url_for('auth.login'))

    google = OAuth2Session(
        client_id=client_id,
        scope=SCOPES,
        redirect_uri=_redirect_uri(),
    )
    auth_url, state = google.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type='offline',
        prompt='select_account',
        hd=ALLOWED_DOMAIN,
    )
    session['oauth_state'] = state
    return redirect(auth_url)


@bp.route('/google-callback')
def google_callback():
    """Recebe o code do Google, troca por token, valida domínio e cria sessão."""
    error = request.args.get('error')
    if error:
        flash(f'Acesso negado pelo Google: {error}', 'error')
        return redirect(url_for('auth.login'))

    client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '').strip()

    google = OAuth2Session(
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        state=session.get('oauth_state'),
    )

    try:
        google.fetch_token(
            TOKEN_URL,
            client_secret=client_secret,
            authorization_response=request.url,
        )
    except Exception as e:
        flash(f'Erro ao trocar code por token: {e}', 'error')
        return redirect(url_for('auth.login'))

    try:
        resp = google.get(USERINFO_URL, timeout=10)
        if resp.status_code != 200:
            raise ValueError(f'Status {resp.status_code} ao buscar userinfo')
        user_info = resp.json()
    except Exception as e:
        flash(f'Erro ao obter dados do usuário Google: {e}', 'error')
        return redirect(url_for('auth.login'))

    email = user_info.get('email', '')

    # --- BACKEND DOMAIN VALIDATION (crítico) ---
    if not validate_user_domain(email):
        flash(
            f'Acesso restrito a @{ALLOWED_DOMAIN}. '
            f'O e-mail "{email}" não é autorizado.',
            'error'
        )
        return redirect(url_for('auth.login'))

    session.permanent = True
    session['user'] = {
        'id': user_info.get('sub', ''),
        'email': email,
        'name': user_info.get('name', email.split('@')[0]),
        'avatar': user_info.get('picture', ''),
    }
    session.pop('oauth_state', None)

    return redirect(url_for('main.dashboard'))


# ── Rotas legadas ──────────────────────────────────────────────────────────────

@bp.route('/callback')
def callback():
    return render_template('auth/callback.html')


@bp.route('/session', methods=['POST'])
def set_session():
    return jsonify({'ok': False, 'message': 'Use /auth/google para autenticar.'}), 400


@bp.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada com sucesso.', 'info')
    return redirect(url_for('auth.login'))
