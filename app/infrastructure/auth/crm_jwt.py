"""
CRM SSO — validates JWTs issued by the CRM_MG frontend/backend so it can call
ContAI's Flask API as a JSON API, alongside the existing Google-OAuth
session-cookie flow used by the standalone Jinja app.
"""
import os
from typing import Optional

import jwt
from flask import request

from app.infrastructure.supabase.auth import validate_user_domain
from app.infrastructure.logger import logger


def _get_bearer_token() -> Optional[str]:
    """Extracts the raw token from the 'Authorization: Bearer <token>' header."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return None
    parts = auth_header.split(' ', 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    token = parts[1].strip()
    return token or None


def get_user_from_crm_jwt() -> Optional[dict]:
    """
    Reads the Authorization header of the current Flask request, decodes it as a
    CRM-issued JWT (HS256, secret CRM_JWT_SECRET), and returns a user dict if
    valid, or None if the token is missing/invalid/expired/wrong domain.
    """
    token = _get_bearer_token()
    if not token:
        return None

    secret = os.environ.get('CRM_JWT_SECRET', '').strip()
    if not secret:
        logger.warning("[CRM JWT] CRM_JWT_SECRET não configurado; recusando token Bearer.")
        return None

    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        logger.info("[CRM JWT] Token expirado.")
        return None
    except jwt.InvalidTokenError as e:
        logger.info(f"[CRM JWT] Token inválido: {e}")
        return None

    email = (payload.get('email') or '').strip()
    if not validate_user_domain(email):
        logger.warning(f"[CRM JWT] Domínio não autorizado para: {email}")
        return None

    return {
        'id': payload.get('sub', ''),
        'email': email,
        'name': payload.get('name', email.split('@')[0] if email else ''),
        'avatar': payload.get('avatar', ''),
        'source': 'crm_jwt',
    }
