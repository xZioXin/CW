from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Зв’язкова таблиця для many-to-many між Knowledge та Collection
collection_knowledge = db.Table(
    'collection_knowledge',
    db.Column('collection_id', db.Integer, db.ForeignKey('collection.id'), primary_key=True),
    db.Column('knowledge_id', db.Integer, db.ForeignKey('knowledge.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')        # admin / user
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    authors = db.Column(db.Text)
    year = db.Column(db.Integer)
    source = db.Column(db.Text)
    doc_type = db.Column(db.String(50))
    
    # Оригінальна назва файлу
    original_filename = db.Column(db.String(300), nullable=False)
    # Безпечна назва для збереження на диску
    stored_filename = db.Column(db.String(200), nullable=False, unique=True)
    
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref='documents')


class Knowledge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    text = db.Column(db.Text, nullable=False)           
    note = db.Column(db.Text)                           
    tags = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document = db.relationship('Document', backref='knowledges')
    user = db.relationship('User', backref='knowledges')
    collections = db.relationship('Collection', secondary=collection_knowledge,
                                  back_populates='knowledges')


class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='collections')
    knowledges = db.relationship('Knowledge', secondary=collection_knowledge,
                                 back_populates='collections')

class RecentlyViewed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='viewed_history')
    document = db.relationship('Document')