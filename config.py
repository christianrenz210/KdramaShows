import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kdramashows-dev-key-2026')
    # Use DATABASE_URL if set (Render), otherwise fallback to SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///kdramashows.db')
    # Render provides postgres:// URL; SQLAlchemy 1.4+ expects postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
    TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w500'
    TMDB_BASE_URL = 'https://api.themoviedb.org/3'
    # Kisskh API keys for stream and subtitles
    KISSKH_STREAM_KEY = os.environ.get('KISSKH_STREAM_KEY', '')
    KISSKH_SUB_KEY = os.environ.get('KISSKH_SUB_KEY', '')
