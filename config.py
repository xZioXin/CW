import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tvoj-super-secret-key-2025'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'knowledge.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    WHOOSH_BASE = os.path.join(BASE_DIR, 'whoosh_index')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    WHOOSH_BASE = os.path.join(BASE_DIR, 'whoosh_index')
    # Додаємо цю строчку — вимикає блокування (безпечна для одного користувача)
    WHOOSH_INDEXING_PARAMS = {"limitmb": 256, "procs": 1, "multisegment": True}
    # А головне — це:
    WHOOSH_DISABLE_LOCKING = True