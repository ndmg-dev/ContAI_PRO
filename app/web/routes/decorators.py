from functools import wraps
from flask import session, redirect, url_for, request, jsonify

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

    If neither is present/valid: HTML/browser-style requests are redirected
    to the login page (unchanged behavior); requests carrying a Bearer header
    (i.e. the CRM API flow) get a 401 JSON response instead of a redirect.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user'):
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
