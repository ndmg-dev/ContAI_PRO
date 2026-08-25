"""
Extensões compartilhadas entre app/__init__.py e os blueprints de rotas.

Existe só pra dar acesso ao objeto `csrf` fora de create_app() — precisamos
chamar csrf.protect() manualmente dentro de login_required (ver
app/web/routes/decorators.py) só quando a autenticação veio por cookie de
sessão, pulando a checagem quando veio por Bearer JWT do CRM (uma chamada
stateless com Authorization header não é vulnerável a CSRF, que existe pra
proteger contra o BROWSER anexar cookies de sessão automaticamente).
"""
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
