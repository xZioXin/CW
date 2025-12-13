import os
import shutil
from datetime import datetime
from whoosh.index import create_in, open_dir
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.fields import Schema, TEXT, ID, DATETIME, KEYWORD
import PyPDF2
from docx import Document as DocxDocument
from bleach import clean
from models import db, Document
from config import Config
from flask import current_app

def get_schema():
    return Schema(
        doc_id=ID(stored=True, unique=True),
        title=TEXT(stored=True, phrase=True),
        authors=TEXT(stored=True),
        content=TEXT(stored=True, phrase=True),
        year=DATETIME(stored=True),
        tags=KEYWORD(lowercase=True, commas=True)
    )

def init_search_index():
    if not os.path.exists(current_app.config['WHOOSH_BASE']):
        os.mkdir(current_app.config['WHOOSH_BASE'])
        ix = create_in(current_app.config['WHOOSH_BASE'], schema=get_schema())
        ix.close()

def extract_text(filepath):
    text = ""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.pdf':
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        elif ext == '.docx':
            doc = DocxDocument(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Помилка читання файлу {filepath}: {e}")
    return clean(text, tags=[], strip=True)[:900000]

def index_document(doc_id, filepath):
    ix = open_dir(current_app.config['WHOOSH_BASE'])
    writer = ix.writer()

    doc = Document.query.get(doc_id)
    content = extract_text(filepath)

    year_dt = None
    if doc.year:
        try:
            year_dt = datetime(doc.year, 1, 1)
        except:
            year_dt = None

    writer.update_document(
        doc_id=str(doc.id),
        title=doc.title or "",
        authors=doc.authors or "",
        content=content,
        year=year_dt,
        tags=""
    )
    writer.commit()

def delete_document_from_index(doc_id):
    """Видаляє документ із пошукового індексу Whoosh"""
    if not os.path.exists(current_app.config['WHOOSH_BASE']):
        return
    ix = open_dir(current_app.config['WHOOSH_BASE'])
    writer = ix.writer()
    writer.delete_by_term('doc_id', str(doc_id))
    writer.commit()

def search_fulltext(query_str, limit=100):
    if not query_str.strip():
        return []
    ix = open_dir(current_app.config['WHOOSH_BASE'])
    with ix.searcher() as searcher:
        parser = MultifieldParser(["title", "content", "authors"], ix.schema, group=OrGroup)
        query = parser.parse(query_str)
        results = searcher.search(query, limit=limit)
        return [int(r['doc_id']) for r in results]

def backup_database():
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")
    shutil.copyfile(
        os.path.join(current_app.instance_path, 'knowledge.db'),
        backup_path
    )
    return backup_path