import pytest
import shutil
import os
from io import BytesIO
from app import create_app, db
from models import User, Document
from config import Config

@pytest.fixture
def client():
    # Налаштування тестової конфігурації
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        WTF_CSRF_ENABLED = False
        UPLOAD_FOLDER = 'uploads_test'
        WHOOSH_BASE = 'whoosh_integration_index'  # Окрема папка для цих тестів!

    # Очистка перед запуском (на випадок, якщо минулий раз впало)
    if os.path.exists('whoosh_integration_index'):
        shutil.rmtree('whoosh_integration_index')
    if os.path.exists('uploads_test'):
        shutil.rmtree('uploads_test')

    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        u = User(name="Tester", email="test@test.com")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
        
        with app.test_client() as client:
            client.post('/login', data={'email': 'test@test.com', 'password': 'pass'}, follow_redirects=True)
            yield client
        
        # Очистка після тестів
        db.session.remove()
        db.drop_all()
    
    # Видаляємо тимчасові папки
    if os.path.exists('whoosh_integration_index'):
        shutil.rmtree('whoosh_integration_index')
    if os.path.exists('uploads_test'):
        shutil.rmtree('uploads_test')

def test_homepage(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Tester" in response.data

def test_upload_document(client):
    data = {
        'title': 'Test Doc',
        'authors': 'Ivanov',
        'year': 2025,
        'source': 'Test Source',
        'doc_type': 'стаття',
        'file': (BytesIO(b"dummy content"), 'test.docx')
    }
    
    response = client.post('/document/upload', data=data, follow_redirects=True)
    assert response.status_code == 200
    
    doc = Document.query.first()
    assert doc is not None, "Документ не зберігся. Перевірте forms.py"
    assert doc.title == 'Test Doc'

def test_search_page(client):
    response = client.get('/documents?q=something')
    assert response.status_code == 200

def test_add_knowledge(client):
    # Спочатку завантажуємо документ
    test_upload_document(client)
    doc = Document.query.first()
    
    data = {
        'text': 'Цікава цитата',
        'note': 'Моя думка',
        'tags': 'тест'
    }
    response = client.post(f'/knowledge/add/{doc.id}', data=data, follow_redirects=True)
    assert response.status_code == 200
    assert 'Цікава'.encode('utf-8') in response.data

def test_admin_access_denied(client):
    response = client.get('/admin/users')
    assert response.status_code == 403