import os
from pypdf import PdfReader
from docx import Document as DocxDocument
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser
from whoosh.analysis import StemmingAnalyzer
import shutil
from datetime import datetime
from models import db, Document

def get_schema():
    analyzer = StemmingAnalyzer()
    return Schema(
        id=ID(stored=True, unique=True),
        title=TEXT(stored=True, analyzer=analyzer),
        content=TEXT(stored=True, analyzer=analyzer),
        authors=TEXT(stored=True),
        year=ID(stored=True),
        path=ID(stored=True)
    )

def init_search_index(index_dir='whoosh_index'):
    if not os.path.exists(index_dir):
        os.mkdir(index_dir)
        create_in(index_dir, get_schema())
    else:
        if exists_in(index_dir):
            try:
                from whoosh.index import unlock_dir
                unlock_dir(index_dir)
            except: pass

def index_document(doc_id, filepath, index_dir='whoosh_index'):
    if not os.path.exists(index_dir):
        init_search_index(index_dir)

    ix = open_dir(index_dir)
    writer = ix.writer()
    text = extract_text(filepath)
    
    doc = db.session.get(Document, doc_id)
    
    if doc:
        writer.update_document(
            id=str(doc_id),
            title=doc.title,
            content=text,
            authors=doc.authors or "",
            year=str(doc.year) if doc.year else "",
            path=filepath
        )
        writer.commit()

def delete_document_from_index(doc_id, index_dir='whoosh_index'):
    if exists_in(index_dir):
        ix = open_dir(index_dir)
        writer = ix.writer()
        writer.delete_by_term('id', str(doc_id))
        writer.commit()

def search_fulltext(query_str, index_dir='whoosh_index'):
    if not exists_in(index_dir): return []
    ix = open_dir(index_dir)
    with ix.searcher() as searcher:
        query = MultifieldParser(["title", "content", "authors"], ix.schema).parse(query_str)
        results = searcher.search(query, limit=20)
        return [int(r['id']) for r in results]

def extract_text(filepath):
    text = ""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.pdf':
            with open(filepath, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
        elif ext == '.docx':
            doc = DocxDocument(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting text: {e}")
    return text[:900000]

def backup_database():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    src = 'instance/knowledge.db'
    dst = f'backups/knowledge_{timestamp}.db'
    if os.path.exists(src):
        shutil.copy2(src, dst)
        return dst
    return None