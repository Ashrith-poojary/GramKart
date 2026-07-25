import os
from datetime import timedelta

class Config:
    """Base Configuration Class."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'gramkart_production_secure_secret_key_987654321')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session Cookie Security Configuration settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # In production, set SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # CSRF Token Security configurations
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY', 'gramkart_csrf_secret_key_8888')
    
    # Max File Upload size cap (5 MB limit)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    
    # SMTP email configurations
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@gramkart.com')

    # Rate Limiting configuration
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    # Caching configuration
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    CACHE_DEFAULT_TIMEOUT = 300

    # Razorpay configurations
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_mockKeyId12345')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'mockKeySecret67890')
    
    # Twilio configurations
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')
    
    # Sentry configurations
    SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Database URL configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///gramkart.db')
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

class DevelopmentConfig(Config):
    """Development Configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///gramkart.db')

class ProductionConfig(Config):
    """Production Configuration."""
    DEBUG = False
    # Enforce cookie security in production
    SESSION_COOKIE_SECURE = True

class TestingConfig(Config):
    """Testing Configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    CACHE_TYPE = 'NullCache'
    RATELIMIT_STORAGE_URI = 'memory://'
    RATELIMIT_ENABLED = False
