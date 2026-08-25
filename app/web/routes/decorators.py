from functools import wraps
from flask import session, redirect, url_for, request, jsonify

from app.extensions import csrf
from app.infrastructure.auth.crm_jwt import get_user_from_crm_jwt


def login_required(f):
    """
    Decorator that authenticates a request via EITHER:
      (a) the existing Google-OAuth session cookie (session['user']) — used by
          the standalone Jinja app, kept working unchanged; or
      (b) a valid 'Authorization: Bearer <jwt>' header issued by the CRM_MG
          backend (validated in app.infrastructure.auth.crm_jwt).

    When authenticated via (b), the resulting user dict is written into
    flask.session['user'] for the current request only, so every existing
    handler that reads session.get('user') keeps working unmodified — no
    persisted cookie is required for that to work.

    CSRF: WTF_CSRF_CHECK_DEFAULT=False (see app/__init__.py) means Flask-WTF
    no longer auto-checks every request. Path (a) is cookie/session-based, so
    it's still vulnerable to CSRF and we validate it manually here via
    csrf.protect(). Path (b) is a stateless Bearer header a malicious page
    cannot attach to a forged cross-site request, so CSRF doesn't apply and
    is skipped.

    If neither is present/valid: HTML/browser-style requests are redirected
    to the login page (unchanged behavior); requests carrying a Bearer header
    (i.e. the CRM API flow) get a 401 JSON response instead of a redirect.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user'):
            csrf.protect()
            return f(*args, **kwargs)

        crm_user = get_user_from_crm_jwt()
        if crm_user:
            session['user'] = crm_user
            return f(*args, **kwargs)

        if request.headers.get('Authorization', ''):
            # A Bearer token was sent but was missing/invalid/expired/wrong
            # domain — this is an API caller, not a browser navigation.
            return jsonify({'ok': False, 'message': 'Token inválido ou expirado.', 'code': 'UNAUTHORIZED'}), 401

        return redirect(url_for('auth.login'))
    return decorated_function
