import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Секретний ключ для захисту форм та сесій
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tvij-super-secret-key-2025'
    
    # Налаштування бази даних SQLite
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'knowledge.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Папки для завантажених файлів та пошукового індексу
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    WHOOSH_BASE = os.path.join(BASE_DIR, 'whoosh_index')
    
    # Максимальний розмір файлу (50 МБ) та час життя сесії
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Налаштування для пошукового двіжка, щоб не блокував файли
    WHOOSH_INDEXING_PARAMS = {"limitmb": 256, "procs": 1, "multisegment": True}
    WHOOSH_DISABLE_LOCKING = True