"""Fail-closed environment settings; never ship production with development secrets."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str
    secret_key: str
    database_url: str
    frontend_url: str
    google_mode: str
    cookie_secure: bool


def get_settings() -> Settings:
    env = os.getenv('APP_ENV', 'development').lower()
    secret = os.getenv('SECRET_KEY', '')
    if env == 'production' and (len(secret) < 32 or secret == 'local-development-only-change-me'):
        raise RuntimeError('Production requires a strong SECRET_KEY')
    if not secret:
        if env != 'production':
            secret = 'local-development-only-change-me'
        else:
            raise RuntimeError('SECRET_KEY is missing')
    google_mode = os.getenv('GOOGLE_MODE', 'mock').lower()
    if google_mode not in ('mock', 'pending'):
        raise RuntimeError('Live Google integration is not enabled: keep GOOGLE_MODE=mock or pending')
    return Settings(
        environment=env,
        secret_key=secret,
        database_url=os.getenv('DATABASE_URL', 'sqlite:///./yorumpilot.db').replace('postgres://','postgresql+psycopg://',1).replace('postgresql://','postgresql+psycopg://',1),
        frontend_url=os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/'),
        google_mode=google_mode,
        cookie_secure=env == 'production',
    )
