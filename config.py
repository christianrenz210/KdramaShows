import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kdramashows-dev-key-2026')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///kdramashows.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
    TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w500'
    TMDB_BASE_URL = 'https://api.themoviedb.org/3'
