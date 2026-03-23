import os
from urllib.parse import urlencode
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

DEFAULT_ALLOWED_DOMAIN = 'mendoncagalvao.com.br'


def get_oauth_url() -> str:
    """
    Returns the Supabase Google OAuth redirect URL.
    Includes redirect_to so Supabase returns the user to our Flask callback,
    not to the Supabase Studio dashboard.
    """
    supabase_url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    app_url = os.environ.get('APP_URL', 'http://localhost:5000').rstrip('/')
    redirect_to = f"{app_url}/auth/callback"
    params = urlencode({'provider': 'google', 'redirect_to': redirect_to})
    return f"{supabase_url}/auth/v1/authorize?{params}"


def exchange_code_for_session(code: str) -> dict | None:
    """Exchanges an OAuth authorization code for a Supabase session."""
    client = db_adapter.get_client()
    if not client:
        return None
    try:
        response = client.auth.exchange_code_for_session({"auth_code": code})
        return response
    except Exception as e:
        logger.exception(f"[Auth] exchange_code_for_session error: {e}")
        return None


def validate_user_domain(email: str) -> bool:
    """Returns True if the email belongs to the allowed corporate domain."""
    if not email:
        return False
    allowed_domain = os.environ.get('ALLOWED_DOMAIN', DEFAULT_ALLOWED_DOMAIN).strip().lower()
    if not allowed_domain:
        logger.warning("[Auth] ALLOWED_DOMAIN vazio; bloqueando validação de domínio por segurança.")
        return False
    return email.lower().strip().endswith(f"@{allowed_domain}")


def get_session_user(session: dict) -> dict | None:
    """Extracts user info dict from Flask session."""
    return session.get('user')
