import pytest
from io import BytesIO
from app import create_app, db
from models import User, Document
from config import Config

@pytest.fixture
def client():
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        WTF_CSRF_ENABLED = False  # Вимикаємо CSRF
        UPLOAD_FOLDER = 'uploads_test'

    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        # Створюємо юзера
        u = User(name="Tester", email="test@test.com")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
        
        with app.test_client() as client:
            # Логінимось
            client.post('/login', data={'email': 'test@test.com', 'password': 'pass'}, follow_redirects=True)
            yield client
        
        db.drop_all()

def test_homepage(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Tester" in response.data

def test_upload_document(client):
    data = {
        'title': 'Test Doc',
        'authors': 'Ivanov',
        'year': 2025, # Передаємо числом
        'source': 'Test Source',
        'doc_type': 'article',
        # Файл імітується через BytesIO
        'file': (BytesIO(b"dummy content"), 'test.docx')
    }
    
    # ВИПРАВЛЕНО: Ми НЕ вказуємо content_type вручну! Клієнт зробить це сам.
    response = client.post('/document/upload', data=data, follow_redirects=True)
    
    assert response.status_code == 200
    # Якщо тут впаде, то print покаже причину (помилки форми)
    if b"Test Doc" not in response.data:
        print(response.data.decode('utf-8'))
        
    doc = Document.query.first()
    assert doc is not None, "Документ не зберігся в БД"
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