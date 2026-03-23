import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    
    # Auth settings
    ALLOWED_DOMAIN = os.environ.get('ALLOWED_DOMAIN', 'mendoncagalvao.com.br').strip()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = APP_ENV == 'production'
    PERMANENT_SESSION_LIFETIME = 3600 * 24 * 30  # 30 days
    SESSION_REFRESH_EACH_REQUEST = True
    
    # Supabase Buckets
    STORAGE_BUCKET = 'documentos'

    # Upload limits (bytes)
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_MB', '50')) * 1024 * 1024

    @classmethod
    def validate(cls) -> None:
        """
        Fail-fast config validation for production.
        Keeps development flexible while preventing insecure defaults in prod.
        """
        if cls.APP_ENV == 'production':
            if not cls.SECRET_KEY or len(cls.SECRET_KEY.strip()) < 32:
                raise RuntimeError(
                    "Config inválida: em produção, defina SECRET_KEY forte (>= 32 chars) no ambiente."
                )
