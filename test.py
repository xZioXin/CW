import unittest
from app import create_app
from models import db, User, Document, Knowledge
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    WHOOSH_BASE = 'whoosh_test_index'

class KnowledgeSystemTestCase(unittest.TestCase):
    def setUp(self):
        """Ініціалізація перед кожним тестом"""
        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()
        
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()

        user = User(email='test@kpi.ua', name='Test User')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()

    def tearDown(self):
        """Очищення після тестів"""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_password_hashing(self):
        """Перевірка безпеки паролів"""
        user = User.query.filter_by(email='test@kpi.ua').first()
        self.assertTrue(user.check_password('password123'))
        self.assertFalse(user.check_password('wrongpass'))

    def test_document_creation(self):
        """Перевірка запису документа в БД"""
        doc = Document(
            title="Unit Test Doc",
            original_filename="test.pdf",
            stored_filename="uuid-123.pdf",
            authors="Tester T."
        )
        db.session.add(doc)
        db.session.commit()
        
        saved_doc = Document.query.filter_by(title="Unit Test Doc").first()
        self.assertIsNotNone(saved_doc)
        self.assertEqual(saved_doc.authors, "Tester T.")

    def test_knowledge_relation(self):
        """Перевірка зв'язку нотаток з документом"""
        user = User.query.filter_by(email='test@kpi.ua').first()
        doc = Document(title="Doc", original_filename="a", stored_filename="b")
        db.session.add(doc)
        db.session.commit()
        
        note = Knowledge(document_id=doc.id, user_id=user.id, text="Quote")
        db.session.add(note)
        db.session.commit()
        
        self.assertEqual(len(doc.knowledges), 1)
        self.assertEqual(doc.knowledges[0].text, "Quote")

    def test_access_denied_for_guests(self):
        """Перевірка захисту сторінок"""
        response = self.client.get('/documents', follow_redirects=True)
        self.assertTrue('login' in response.request.url or response.status_code in [401, 403])

if __name__ == '__main__':
    unittest.main()