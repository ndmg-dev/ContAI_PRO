from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Decorator that redirects to login if no valid session exists."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
