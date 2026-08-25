"""
Shared helpers for resolving request-scoped state (active empresa) in a way
that works both for the standalone Jinja app (persistent session cookie) and
for CRM Bearer-token API calls (no persistent session across requests).
"""
from flask import request, session


def get_active_empresa_id() -> str | None:
    """
    Resolves the active empresa id, preferring an explicit `empresa_id`
    passed by the caller (query string on GET, JSON/form body on POST/DELETE)
    over the session — Bearer-token requests from the CRM won't have a
    persistent session across calls, so they must pass it explicitly.
    Falls back to session['active_empresa']['id'] for backward compatibility
    with the standalone app.
    """
    empresa_id = request.args.get('empresa_id')

    if not empresa_id and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if request.is_json:
            body = request.get_json(silent=True) or {}
            empresa_id = body.get('empresa_id')
        if not empresa_id:
            empresa_id = request.form.get('empresa_id')

    if empresa_id:
        return empresa_id

    return (session.get('active_empresa') or {}).get('id')


def get_active_empresa() -> dict:
    """
    Resolves the active empresa dict. When empresa_id came from the request
    (not the session), only {'id': ...} is guaranteed — callers needing
    `nome` should fetch it themselves if the session copy isn't available.
    """
    session_empresa = session.get('active_empresa') or {}
    empresa_id = get_active_empresa_id()

    if not empresa_id:
        return {}

    if session_empresa.get('id') == empresa_id:
        return session_empresa

    return {'id': empresa_id}
