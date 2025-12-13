import os
import uuid  
import tempfile                             
from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, abort, send_file
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

from docx import Document as DocxDoc
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO

from config import Config
from models import db, User, Document, Knowledge, Collection, RecentlyViewed
from forms import RegistrationForm, LoginForm, DocumentForm, DocumentEditForm, KnowledgeForm, CollectionForm
from utils import init_search_index, search_fulltext, index_document, delete_document_from_index, backup_database

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('backups', exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    from flask_login import LoginManager
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Будь ласка, увійдіть в систему'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # === Context Processor для Recently Viewed ===
    @app.context_processor
    def inject_recent():
        if current_user.is_authenticated:
            # Останні 5 переглянутих унікальних документів
            # (складніший запит, щоб не дублювати, спрощуємо: беремо всі і фільтруємо в python або просто останні записи)
            recent_views = RecentlyViewed.query.filter_by(user_id=current_user.id)\
                .order_by(RecentlyViewed.viewed_at.desc()).limit(10).all()
            
            # Прибираємо дублікати (залишаємо останній перегляд)
            seen = set()
            unique_recent = []
            for view in recent_views:
                if view.document_id not in seen:
                    unique_recent.append(view.document)
                    seen.add(view.document_id)
            return dict(recently_viewed_docs=unique_recent[:5])
        return dict(recently_viewed_docs=[])

    with app.app_context():
        db.create_all()
        init_search_index()
        if not User.query.filter_by(email='admin@example.com').first():
            admin = User(email='admin@example.com', name='Адміністратор системи', role='admin', is_active=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

    # === Маршрути ===

    @app.route('/')
    def index():
        recent_uploads = Document.query.order_by(Document.uploaded_at.desc()).limit(10).all()
        return render_template('index.html', recent=recent_uploads)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated: return redirect(url_for('index'))
        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(email=form.email.data, name=form.name.data, role='user')
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Реєстрація успішна!', 'success')
            return redirect(url_for('login'))
        return render_template('auth/register.html', form=form)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated: return redirect(url_for('index'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and user.check_password(form.password.data) and user.is_active:
                login_user(user, remember=True)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            flash('Невірний логін або пароль', 'danger')
        return render_template('auth/login.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Ви вийшли з системи', 'info')
        return redirect(url_for('index'))

    # === DOCUMENTS ===

    @app.route('/document/upload', methods=['GET', 'POST'])
    @login_required
    def upload_document():
        form = DocumentForm()
        if form.validate_on_submit():
            f = form.file.data
            original_filename = f.filename
            ext = os.path.splitext(original_filename)[1].lower()
            if ext not in ['.pdf', '.docx']:
                flash('Тільки PDF та DOCX', 'danger')
                return redirect(request.url)
            
            unique_filename = str(uuid.uuid4()) + ext
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            f.save(filepath)

            doc = Document(
                title=form.title.data, authors=form.authors.data, year=form.year.data,
                source=form.source.data, doc_type=form.doc_type.data,
                original_filename=original_filename, stored_filename=unique_filename,
                uploaded_by=current_user.id
            )
            db.session.add(doc)
            db.session.commit()
            index_document(doc.id, filepath)
            flash('Документ завантажено!', 'success')
            return redirect(url_for('document_list'))
        return render_template('document/upload.html', form=form)

    @app.route('/document/<int:doc_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        if current_user.role != 'admin' and doc.uploaded_by != current_user.id: abort(403)
        
        form = DocumentEditForm(obj=doc)
        if form.validate_on_submit():
            form.populate_obj(doc)
            if form.file.data:
                # Обробка нового файлу
                f = form.file.data
                ext = os.path.splitext(f.filename)[1].lower()
                new_filename = str(uuid.uuid4()) + ext
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                # Видалення старого
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename))
                except: pass
                doc.stored_filename = new_filename
                doc.original_filename = f.filename
            
            db.session.commit()
            index_document(doc.id, os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename))
            flash('Документ оновлено', 'success')
            return redirect(url_for('document_detail', doc_id=doc.id))
        return render_template('document/upload.html', form=form, title="Редагування")

    @app.route('/document/<int:doc_id>/delete', methods=['POST'])
    @login_required
    def delete_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        if current_user.role != 'admin' and doc.uploaded_by != current_user.id: abort(403)
        
        delete_document_from_index(doc.id)
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename))
        except: pass
        
        Knowledge.query.filter_by(document_id=doc.id).delete()
        RecentlyViewed.query.filter_by(document_id=doc.id).delete()
        db.session.delete(doc)
        db.session.commit()
        flash('Документ видалено', 'success')
        return redirect(url_for('document_list'))

    @app.route('/documents')
    @login_required
    def document_list():
        query = request.args.get('q', '').strip()
        author = request.args.get('author', '')
        year_from = request.args.get('year_from', type=int)
        year_to = request.args.get('year_to', type=int)
        doc_type = request.args.get('type', '')
        show_my = request.args.get('show_my')  # Фільтр "Тільки мої"

        docs = Document.query

        if query:
            ids = search_fulltext(query)
            docs = docs.filter(Document.id.in_(ids)) if ids else docs.filter(False)

        if author: docs = docs.filter(Document.authors.ilike(f'%{author}%'))
        if year_from: docs = docs.filter(Document.year >= year_from)
        if year_to: docs = docs.filter(Document.year <= year_to)
        if doc_type: docs = docs.filter_by(doc_type=doc_type)
        
        # 4. Фільтр "Тільки мої"
        if show_my == '1':
            docs = docs.filter_by(uploaded_by=current_user.id)

        documents = docs.order_by(Document.uploaded_at.desc()).all()
        return render_template('document/list.html', documents=documents)

    @app.route('/document/<int:doc_id>')
    @login_required
    def document_detail(doc_id):
        doc = Document.query.get_or_404(doc_id)
        
        # 3. Запис в історію переглядів
        view = RecentlyViewed(user_id=current_user.id, document_id=doc_id)
        db.session.add(view)
        db.session.commit()

        knowledges = Knowledge.query.filter_by(document_id=doc_id, user_id=current_user.id).all()
        return render_template('document/detail.html', doc=doc, knowledges=knowledges)

    @app.route('/document/<int:doc_id>/download')
    @login_required
    def download_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        return send_from_directory(app.config['UPLOAD_FOLDER'], doc.stored_filename,
                                   as_attachment=True, download_name=doc.original_filename)

    # === KNOWLEDGE & COLLECTIONS ===

    @app.route('/knowledge/add/<int:doc_id>', methods=['POST'])
    @login_required
    def add_knowledge(doc_id):
        text = request.form.get('text', '').strip()
        note = request.form.get('note', '')
        tags = request.form.get('tags', '')
        if text:
            k = Knowledge(document_id=doc_id, user_id=current_user.id, text=text, note=note, tags=tags)
            db.session.add(k)
            db.session.commit()
            flash('Збережено!', 'success')
        return redirect(url_for('document_detail', doc_id=doc_id))

    @app.route('/knowledge/<int:k_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_knowledge(k_id):
        k = Knowledge.query.get_or_404(k_id)
        if k.user_id != current_user.id: abort(403)
        form = KnowledgeForm(obj=k)
        if form.validate_on_submit():
            form.populate_obj(k)
            db.session.commit()
            flash('Конспект оновлено', 'success')
            return redirect(url_for('my_knowledge'))
        return render_template('base.html', content=f"<h1>Редагувати помилка (потрібен шаблон)</h1>") # Використовуємо modal або окрему сторінку, тут спрощено редірект

    @app.route('/knowledge/<int:k_id>/delete', methods=['POST'])
    @login_required
    def delete_knowledge(k_id):
        k = Knowledge.query.get_or_404(k_id)
        if k.user_id != current_user.id:
            abort(403)
            
        # Явно очищаємо зв'язки з колекціями перед видаленням
        # Це гарантує видалення з таблиці collection_knowledge
        k.collections = [] 
        db.session.commit() # Зберігаємо стан "без колекцій"

        # Тепер видаляємо сам конспект
        db.session.delete(k)
        db.session.commit()
        
        flash('Конспект видалено', 'success')
        return redirect(request.referrer or url_for('my_knowledge'))

    @app.route('/my/knowledge', methods=['GET', 'POST'])
    @login_required
    def my_knowledge():
        # Пошук та фільтрація
        q = request.args.get('q', '').strip()
        tag = request.args.get('tag', '').strip()
        
        query = Knowledge.query.filter_by(user_id=current_user.id)
        if q:
            query = query.filter( (Knowledge.text.ilike(f'%{q}%')) | (Knowledge.note.ilike(f'%{q}%')) )
        if tag:
            query = query.filter(Knowledge.tags.ilike(f'%{tag}%'))
            
        knowledges = query.order_by(Knowledge.created_at.desc()).all()
        collections = Collection.query.filter_by(user_id=current_user.id).all()
        
        # Обробка додавання вибраних до колекції
        if request.method == 'POST':
            collection_id = request.form.get('collection_id')
            selected_ids = request.form.getlist('knowledge_ids')
            if collection_id and selected_ids:
                coll = Collection.query.get(collection_id)
                if coll and coll.user_id == current_user.id:
                    count = 0
                    for kid in selected_ids:
                        kn = Knowledge.query.get(int(kid))
                        if kn and kn.user_id == current_user.id and kn not in coll.knowledges:
                            coll.knowledges.append(kn)
                            count += 1
                    db.session.commit()
                    flash(f'Додано {count} записів до колекції "{coll.name}"', 'success')
            return redirect(url_for('my_knowledge'))

        return render_template('knowledge/list.html', knowledges=knowledges, collections=collections)

    # === COLLECTION MANAGEMENT ===

    @app.route('/collection/create', methods=['POST'])
    @login_required
    def create_collection():
        name = request.form.get('name', '').strip()
        if name:
            if not Collection.query.filter_by(name=name, user_id=current_user.id).first():
                db.session.add(Collection(name=name, user_id=current_user.id))
                db.session.commit()
                flash(f'Колекція "{name}" створена', 'success')
            else:
                flash('Колекція з такою назвою вже існує', 'warning')
        return redirect(url_for('my_knowledge'))

    @app.route('/collection/<int:c_id>/delete', methods=['POST'])
    @login_required
    def delete_collection(c_id):
        c = Collection.query.get_or_404(c_id)
        if c.user_id != current_user.id: abort(403)
        db.session.delete(c)
        db.session.commit()
        flash('Колекцію видалено', 'success')
        return redirect(url_for('my_knowledge'))
    
    @app.route('/collection/<int:c_id>/rename', methods=['POST'])
    @login_required
    def rename_collection(c_id):
        c = Collection.query.get_or_404(c_id)
        if c.user_id != current_user.id: abort(403)
        new_name = request.form.get('name', '').strip()
        if new_name:
            c.name = new_name
            db.session.commit()
            flash('Колекцію перейменовано', 'success')
        return redirect(url_for('my_knowledge'))

    @app.route('/collection/<int:c_id>/remove_item/<int:k_id>', methods=['POST'])
    @login_required
    def remove_from_collection(c_id, k_id):
        c = Collection.query.get_or_404(c_id)
        k = Knowledge.query.get_or_404(k_id)
        if c.user_id != current_user.id: abort(403)
        if k in c.knowledges:
            c.knowledges.remove(k)
            db.session.commit()
            flash('Запис прибрано з колекції', 'info')
        return redirect(url_for('my_knowledge'))

    @app.route('/collection/<int:c_id>/export/docx')
    @login_required
    def export_collection_docx(c_id):
        c = Collection.query.get_or_404(c_id)
        if c.user_id != current_user.id: abort(403)
        
        knowledges = c.knowledges
        if not knowledges:
            flash('Колекція порожня', 'warning')
            return redirect(url_for('my_knowledge'))
        
        # Генерація DOCX (функція винесена для чистоти, але тут inline для copy-paste)
        doc = DocxDoc()
        doc.add_heading(f'Колекція: {c.name}', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f'Дата: {datetime.now().strftime("%d.%m.%Y")}')
        
        for i, k in enumerate(knowledges, 1):
            doc.add_heading(f"{i}. {k.document.title}", level=1)
            doc.add_paragraph(f"Автори: {k.document.authors}")
            doc.add_paragraph(k.text, style='Intense Quote')
            if k.note:
                p = doc.add_paragraph()
                p.add_run("Примітка: ").bold = True
                p.add_run(k.note)
            if k.tags:
                doc.add_paragraph(f"Теги: {k.tags}").italic = True
            doc.add_paragraph()

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        safe_name = secure_filename(c.name) or "collection"
        return send_file(
            buffer, as_attachment=True,
            download_name=f"{safe_name}.docx",
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    # === ADMIN ===

    @app.route('/admin/users')
    @login_required
    def admin_users():
        if current_user.role != 'admin': abort(403)
        users = User.query.all()
        return render_template('admin/users.html', users=users)

    @app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
    @login_required
    def toggle_user(user_id):
        if current_user.role != 'admin': abort(403)
        if user_id == current_user.id:
            flash('Неможливо заблокувати себе', 'warning')
            return redirect(url_for('admin_users'))
        user = User.query.get_or_404(user_id)
        user.is_active = not user.is_active
        db.session.commit()
        return redirect(url_for('admin_users'))

    @app.route('/admin/backup')
    @login_required
    def admin_backup():
        if current_user.role != 'admin': abort(403)
        path = backup_database()
        flash(f'Бекап: {os.path.basename(path)}', 'success')
        return redirect(url_for('index'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)