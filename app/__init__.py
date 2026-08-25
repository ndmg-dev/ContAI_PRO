from flask import Flask
from app.config import Config
from app.extensions import csrf
from flask_cors import CORS

def create_app(config_class=Config):
    app = Flask(__name__,
                template_folder='web/templates',
                static_folder='web/static')
    app.config.from_object(config_class)
    config_class.validate()

    # CSRF protection (forms + fetch POSTs). Desliga a checagem automatica
    # global (WTF_CSRF_CHECK_DEFAULT=False) porque ela roda cedo demais -
    # antes de login_required decidir se a request veio autenticada por
    # cookie de sessao (precisa de CSRF) ou por Bearer JWT do CRM (stateless,
    # nao precisa). login_required chama csrf.protect() manualmente so no
    # caso de sessao. Ver app/web/routes/decorators.py.
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    csrf.init_app(app)

    # CORS: for the JSON API used by the CRM_MG React frontend (/api/*) and
    # /empresas/* (company selector — legacy route, predates /api/*, but
    # already Bearer-aware via login_required, so the CRM frontend calls it
    # directly). The standalone Jinja app keeps using same-origin session
    # cookies and is unaffected — CORS is not applied globally.
    CORS(
        app,
        resources={r"/api/*": {"origins": [
            "https://crmmg.mendoncagalvao.com.br",
            "http://localhost:3000",
            "http://localhost:5173",
        ]}, r"/empresas/*": {"origins": [
            "https://crmmg.mendoncagalvao.com.br",
            "http://localhost:3000",
            "http://localhost:5173",
        ]}},
        methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Register Blueprints
    from app.web.routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.web.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.web.routes.chat import bp as chat_bp
    app.register_blueprint(chat_bp, url_prefix='/chat')

    from app.web.routes.documentos import bp as doc_bp
    app.register_blueprint(doc_bp)

    from app.web.routes.conciliacao import bp as concil_bp
    app.register_blueprint(concil_bp)

    from app.web.routes.configuracoes import bp as config_bp
    app.register_blueprint(config_bp)

    from app.web.routes.empresas import bp as empresa_bp
    app.register_blueprint(empresa_bp)

    from app.web.routes.integracoes import bp as integracoes_bp
    app.register_blueprint(integracoes_bp)

    from app.web.routes.plano_contas import bp as plano_contas_bp
    app.register_blueprint(plano_contas_bp)

    from app.web.routes.regras import bp as regras_bp
    app.register_blueprint(regras_bp)

    @app.template_filter('formato_brl')
    def formato_brl(valor):
        """Formata um número para o padrão BRL: R$ 1.234,56"""
        try:
            if valor is None:
                return 'R$ 0,00'
            val = float(valor)
            # Formata com separador de milhar (.) e decimal (,)
            return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(valor)

    @app.before_request
    def check_active_empresa():
        from flask import session, request
        import time

        # Skip static files and auth endpoints
        if request.endpoint and (request.endpoint.startswith('static') or request.endpoint.startswith('auth')):
            return

        active_empresa = session.get('active_empresa')
        if not active_empresa:
            return

        active_id = active_empresa.get('id')
        if not active_id:
            session.pop('active_empresa', None)
            return

        # Only validate against DB every 5 minutes to avoid N+1 per request
        now = time.time()
        last_check = session.get('_empresa_validated_at', 0)
        if now - last_check < 300:
            return

        try:
            from app.infrastructure.supabase.client import db_adapter
            client = db_adapter.get_client()
            if client:
                res = client.table('empresas').select('id').eq('id', active_id).execute()
                if not res.data:
                    session.pop('active_empresa', None)
                    session.pop('_empresa_validated_at', None)
                else:
                    session['_empresa_validated_at'] = now
        except Exception:
            pass  # Don't block the app on transient DB errors

    @app.errorhandler(413)
    def request_entity_too_large(_e):
        from flask import flash, redirect, request
        flash("Arquivo muito grande. Reduza o tamanho do upload e tente novamente.", "error")
        return redirect(request.referrer or "/")

    return app
