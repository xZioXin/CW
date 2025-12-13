from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Таблиця для зв'язку "багато-до-багатьох" між колекціями та нотатками
class CollectionItem(db.Model):
    __tablename__ = 'collection_item'
    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'))
    knowledge_id = db.Column(db.Integer, db.ForeignKey('knowledge.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    collection = db.relationship("Collection", back_populates="items")
    knowledge = db.relationship("Knowledge", back_populates="collection_items")

# Користувачі системи
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Завантажені документи (статті, книги тощо)
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    authors = db.Column(db.Text)
    year = db.Column(db.Integer)
    source = db.Column(db.Text)
    doc_type = db.Column(db.String(50))
    original_filename = db.Column(db.String(300), nullable=False)
    stored_filename = db.Column(db.String(200), nullable=False, unique=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref='documents')

# Конспекти (нотатки), які користувач робить до документів
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
    collection_items = db.relationship('CollectionItem', back_populates='knowledge', cascade="all, delete-orphan")

# Колекції (папки) для групування конспектів
class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='collections')
    items = db.relationship('CollectionItem', back_populates='collection', 
                            order_by='CollectionItem.created_at', cascade="all, delete-orphan")

# Історія переглядів документів
class RecentlyViewed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='viewed_history')
    document = db.relationship('Document')