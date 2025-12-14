import pytest
import os
from datetime import datetime, timezone
from docx import Document as DocxDocument
from app import create_app, db
from models import User
from config import Config
from utils import extract_text

# --- Фікстура для налаштування тестового оточення ---
@pytest.fixture
def app_context():
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # БД в оперативній пам'яті
        WTF_CSRF_ENABLED = False
        WHOOSH_BASE = 'whoosh_test_index'

    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

# --- ТЕСТ 1: Перевірка хешування паролів ---
def test_password_hashing(app_context):
    u = User(name="TestUser", email="test@example.com")
    u.set_password("secret123")
    
    assert u.password_hash != "secret123"
    assert u.check_password("secret123") is True
    assert u.check_password("wrongpass") is False

# --- ТЕСТ 2: Перевірка створення користувача ---
def test_user_creation(app_context):
    u = User(name="Admin", email="admin@test.com", role="admin")
    u.set_password("123")
    
    db.session.add(u)
    db.session.commit()

    fetched_user = User.query.filter_by(email="admin@test.com").first()
    assert fetched_user is not None
    assert fetched_user.role == "admin"

# --- ТЕСТ 3: Перевірка витягування тексту з DOCX ---
def test_extract_text_docx(tmp_path):
    # Створюємо тимчасовий DOCX файл
    doc = DocxDocument()
    test_text = "Це унікальний тестовий рядок."
    doc.add_paragraph(test_text)
    
    file_path = tmp_path / "test_doc.docx"
    doc.save(file_path)

    # Перевіряємо екстракцію
    extracted_content = extract_text(str(file_path))
    assert test_text in extracted_content

# --- ТЕСТ 4: Перевірка ініціалізації індексу ---
def test_index_initialization(app_context):
    from utils import init_search_index
    
    index_dir = app_context.config.get('WHOOSH_BASE')
    
    init_search_index(index_dir)
    
    assert os.path.exists(index_dir)
    assert os.path.isdir(index_dir)
    
    import shutil
    if os.path.exists(index_dir):
        shutil.rmtree(index_dir)