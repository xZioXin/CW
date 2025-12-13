import os
import uuid  
import tempfile                             
from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory, abort, send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime

from docx import Document as DocxDoc
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
from datetime import datetime
import os

from config import Config
from models import db, User, Document, Knowledge, Collection, Category
from forms import RegistrationForm, LoginForm, DocumentForm, DocumentEditForm, KnowledgeForm, CollectionForm
from utils import init_search_index, search_fulltext, index_document, delete_document_from_index, backup_database, extract_text

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Створюємо папки
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

    # === Ініціалізація при першому запуску ===
    with app.app_context():
        db.create_all()
        init_search_index()

        # Створюємо адміністратора, якщо його немає
        if not User.query.filter_by(email='admin@example.com').first():
            admin = User(
                email='admin@example.com',
                name='Адміністратор системи',
                role='admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Створено адміністратора: admin@example.com / admin123")

    # === Маршрути ===

    @app.route('/')
    def index():
        recent = Document.query.order_by(Document.uploaded_at.desc()).limit(10).all()
        return render_template('index.html', recent=recent)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(email=form.email.data, name=form.name.data, role='user')
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Реєстрація успішна! Тепер ви можете увійти.', 'success')
            return redirect(url_for('login'))
        return render_template('auth/register.html', form=form)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and user.check_password(form.password.data) and user.is_active:
                login_user(user, remember=True)
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            flash('Невірний email, пароль або акаунт заблоковано', 'danger')
        return render_template('auth/login.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Ви вийшли з системи', 'info')
        return redirect(url_for('index'))

    @app.route('/document/upload', methods=['GET', 'POST'])
    @login_required
    def upload_document():
        form = DocumentForm()
        if form.validate_on_submit():
            f = form.file.data
            original_filename = f.filename
            
            extension = os.path.splitext(original_filename)[1].lower()
            if not extension in ['.pdf', '.docx']:
                flash('Дозволені лише PDF та DOCX', 'danger')
                return redirect(request.url)
                
            unique_filename = str(uuid.uuid4()) + extension
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            f.save(filepath)

            doc = Document(
                title=form.title.data,
                authors=form.authors.data,
                year=form.year.data or None,
                source=form.source.data or '',
                doc_type=form.doc_type.data,
                original_filename=original_filename,
                stored_filename=unique_filename,
                uploaded_by=current_user.id
            )
            db.session.add(doc)
            db.session.commit()

            index_document(doc.id, filepath)

            flash(f'Документ "{original_filename}" успішно завантажено!', 'success')
            return redirect(url_for('document_list'))

        return render_template('document/upload.html', form=form)

    @app.route('/document/<int:doc_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        
        # Перевірка прав: Адмін АБО Власник
        if current_user.role != 'admin' and doc.uploaded_by != current_user.id:
            abort(403)
            
        form = DocumentEditForm(obj=doc)
        
        if form.validate_on_submit():
            doc.title = form.title.data
            doc.authors = form.authors.data
            doc.year = form.year.data or None
            doc.source = form.source.data
            doc.doc_type = form.doc_type.data
            
            # Якщо завантажено новий файл
            if form.file.data:
                f = form.file.data
                original_filename = f.filename
                extension = os.path.splitext(original_filename)[1].lower()
                
                # Видаляємо старий файл
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
                
                # Зберігаємо новий
                unique_filename = str(uuid.uuid4()) + extension
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                f.save(filepath)
                
                doc.original_filename = original_filename
                doc.stored_filename = unique_filename
            
            db.session.commit()
            
            # Оновлюємо індекс (метадані або повний текст)
            current_filepath = os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename)
            index_document(doc.id, current_filepath)
            
            flash('Документ успішно оновлено!', 'success')
            return redirect(url_for('document_detail', doc_id=doc.id))
            
        return render_template('document/upload.html', form=form, title="Редагування документу")

    @app.route('/document/<int:doc_id>/delete', methods=['POST'])
    @login_required
    def delete_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        
        # Перевірка прав: Адмін АБО Власник
        if current_user.role != 'admin' and doc.uploaded_by != current_user.id:
            abort(403)
            
        # 1. Видаляємо файл з диску
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc.stored_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Помилка видалення файлу: {e}")

        # 2. Видаляємо з пошукового індексу
        delete_document_from_index(doc.id)

        # 3. Видаляємо пов'язані знання
        Knowledge.query.filter_by(document_id=doc.id).delete()

        # 4. Видаляємо запис з БД
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

        docs = Document.query

        if query:
            ids = search_fulltext(query)
            if ids:
                docs = docs.filter(Document.id.in_(ids))
            else:
                docs = docs.filter(False)  # нічого не знайдено

        if author:
            docs = docs.filter(Document.authors.ilike(f'%{author}%'))
        if year_from:
            docs = docs.filter(Document.year >= year_from)
        if year_to:
            docs = docs.filter(Document.year <= year_to)
        if doc_type:
            docs = docs.filter_by(doc_type=doc_type)

        documents = docs.order_by(Document.uploaded_at.desc()).all()
        return render_template('document/list.html', documents=documents)

    @app.route('/document/<int:doc_id>')
    @login_required
    def document_detail(doc_id):
        doc = Document.query.get_or_404(doc_id)
        knowledges = Knowledge.query.filter_by(document_id=doc_id, user_id=current_user.id).all()
        return render_template('document/detail.html', doc=doc, knowledges=knowledges)

    @app.route('/document/<int:doc_id>/download')
    @login_required
    def download_document(doc_id):
        doc = Document.query.get_or_404(doc_id)
        return send_from_directory(
            directory=app.config['UPLOAD_FOLDER'],
            path=doc.stored_filename,
            as_attachment=True,
            download_name=doc.original_filename
        )

    @app.route('/knowledge/add/<int:doc_id>', methods=['POST'])
    @login_required
    def add_knowledge(doc_id):
        text = request.form.get('text', '').strip()
        note = request.form.get('note', '')
        tags = request.form.get('tags', '')

        if not text:
            flash('Текст цитати не може бути порожнім', 'danger')
            return redirect(url_for('document_detail', doc_id=doc_id))

        k = Knowledge(
            document_id=doc_id,
            user_id=current_user.id,
            text=text,
            note=note,
            tags=tags
        )
        db.session.add(k)
        db.session.commit()
        flash('Знання успішно збережено!', 'success')
        return redirect(url_for('document_detail', doc_id=doc_id))

    @app.route('/my/knowledge')
    @login_required
    def my_knowledge():
        knowledges = Knowledge.query.filter_by(user_id=current_user.id).order_by(Knowledge.created_at.desc()).all()
        collections = Collection.query.filter_by(user_id=current_user.id).all()
        return render_template('knowledge/list.html', knowledges=knowledges, collections=collections)

    @app.route('/admin/users')
    @login_required
    def admin_users():
        if current_user.role != 'admin':
            abort(403)
        users = User.query.all()
        return render_template('admin/users.html', users=users)

    @app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
    @login_required
    def toggle_user(user_id):
        if current_user.role != 'admin':
            abort(403)
        # Забороняємо блокувати самого себе
        if user_id == current_user.id:
            flash('Ви не можете заблокувати самі себе', 'danger')
            return redirect(url_for('admin_users'))
            
        user = User.query.get_or_404(user_id)
        user.is_active = not user.is_active
        db.session.commit()
        flash(f'Користувач {"розблокований" if user.is_active else "заблокований"}', 'info')
        return redirect(url_for('admin_users'))

    @app.route('/admin/backup')
    @login_required
    def admin_backup():
        if current_user.role != 'admin':
            abort(403)
        path = backup_database()
        flash(f'Резервну копію створено: {os.path.basename(path)}', 'success')
        return redirect(url_for('index'))
    
    @app.route('/collection/create', methods=['POST'])
    @login_required
    def create_collection():
        name = request.form.get('name', '').strip()
        if not name:
            flash('Назва колекції не може бути порожньою', 'danger')
            return redirect(url_for('my_knowledge'))
        
        exists = Collection.query.filter_by(
            name=name,
            user_id=current_user.id
        ).first()
        
        if exists:
            flash(f'Колекція "{name}" вже існує', 'warning')
        else:
            coll = Collection(name=name, user_id=current_user.id)
            db.session.add(coll)
            db.session.commit()
            flash(f'Колекцію "{name}" успішно створено!', 'success')
        
        return redirect(url_for('my_knowledge'))

    @app.route('/knowledge/export/docx')
    @login_required
    def export_knowledge_docx():
        knowledge_ids = request.args.get('ids', '')
        if not knowledge_ids:
            flash('Оберіть хоча б один фрагмент', 'warning')
            return redirect(url_for('my_knowledge'))

        ids = [int(x) for x in knowledge_ids.split(',') if x.isdigit()]
        knowledges = Knowledge.query.filter(
            Knowledge.id.in_(ids),
            Knowledge.user_id == current_user.id
        ).order_by(Knowledge.created_at).all()

        if not knowledges:
            flash('Немає вибраних фрагментів', 'warning')
            return redirect(url_for('my_knowledge'))

        doc = DocxDoc()
        doc.add_heading('Конспект знань', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

        p = doc.add_paragraph()
        p.add_run('Дата створення: ').bold = True
        p.add_run(datetime.now().strftime('%d.%m.%Y о %H:%M'))

        p = doc.add_paragraph()
        p.add_run('Кількість фрагментів: ').bold = True
        p.add_run(str(len(knowledges)))

        doc.add_page_break()

        for i, k in enumerate(knowledges, 1):
            heading = doc.add_heading(level=1)
            run = heading.add_run(f"{i}. {k.document.title}")
            run.font.color.rgb = RGBColor(0, 102, 204)
            run.font.size = Pt(14)
            run.bold = True

            meta = doc.add_paragraph()
            meta.add_run("Автори: ").bold = True
            meta.add_run(f"{k.document.authors} ({k.document.year or '—'})")

            quote = doc.add_paragraph(k.text)
            quote.style = 'Intense Quote'

            if k.note:
                note_p = doc.add_paragraph()
                note_p.add_run("Анотація: ").bold = True
                note_p.add_run(k.note)

            if k.tags:
                tags_p = doc.add_paragraph()
                tags_p.add_run("Теги: ").bold = True
                tags_p.add_run(k.tags)

            doc.add_paragraph()

        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"Конспект_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.docx",
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    @app.route('/knowledge/export/pdf')
    @login_required
    def export_knowledge_pdf():
        knowledge_ids = request.args.get('ids', '')
        ids = [int(x) for x in knowledge_ids.split(',') if x.isdigit()]
        knowledges = Knowledge.query.filter(
            Knowledge.id.in_(ids),
            Knowledge.user_id == current_user.id
        ).all()

        if not knowledges:
            flash('Немає вибраних фрагментів', 'warning')
            return redirect(url_for('my_knowledge'))

        doc = DocxDoc()
        doc.add_heading('Конспект знань', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        doc.add_paragraph(f"Кількість: {len(knowledges)}")
        doc.add_page_break()

        for i, k in enumerate(knowledges, 1):
            doc.add_heading(f"{i}. {k.document.title}", level=1)
            doc.add_paragraph(f"Автори: {k.document.authors} ({k.document.year or '—'})")
            doc.add_paragraph(k.text, style='Intense Quote')
            if k.note:
                p = doc.add_paragraph()
                p.add_run("Анотація: ").bold = True
                p.add_run(k.note)
            if k.tags:
                p = doc.add_paragraph()
                p.add_run("Теги: ").bold = True
                p.add_run(k.tags)
            doc.add_paragraph()

        temp_dir = tempfile.gettempdir()
        docx_path = os.path.join(temp_dir, f"conspect_{current_user.id}.docx")
        pdf_path = os.path.join(temp_dir, f"Конспект_{datetime.now().strftime('%Y-%m-%d')}.pdf")

        doc.save(docx_path)

        try:
            from docx2pdf import convert
            convert(docx_path, pdf_path)
            
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()

            os.remove(docx_path)
            os.remove(pdf_path)

            return send_file(
                BytesIO(pdf_data),
                as_attachment=True,
                download_name=os.path.basename(pdf_path),
                mimetype='application/pdf'
            )
        except Exception as e:
            flash('Не вдалося створити PDF. Встановіть Microsoft Word або скористайтеся DOCX', 'warning')
            if os.path.exists(docx_path): os.remove(docx_path)
            return redirect(url_for('my_knowledge'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)