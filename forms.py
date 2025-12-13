from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, IntegerField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

class RegistrationForm(FlaskForm):
    name = StringField('ПІБ', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Повторіть пароль',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зареєструватися')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Увійти')

class DocumentForm(FlaskForm):
    title = StringField('Назва документу', validators=[DataRequired()])
    authors = StringField('Автори', validators=[DataRequired()])
    year = IntegerField('Рік публікації', validators=[Optional()])
    source = StringField('Джерело (журнал, конференція, URL тощо)')
    doc_type = SelectField('Тип документу', choices=[
        ('стаття', 'Наукова стаття'),
        ('звіт', 'Аналітичний звіт'),
        ('дисертація', 'Дисертація'),
        ('книга', 'Книга/розділ книги'),
        ('інше', 'Інше')
    ], validators=[DataRequired()])
    file = FileField('Файл (PDF або DOCX)', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'docx'], 'Тільки PDF та DOCX!')
    ])
    submit = SubmitField('Завантажити')

class DocumentEditForm(DocumentForm):
    file = FileField('Оновити файл (залиште пустим, якщо не змінюєте)', validators=[
        FileAllowed(['pdf', 'docx'], 'Тільки PDF та DOCX!')
    ])
    submit = SubmitField('Зберегти зміни')

class KnowledgeForm(FlaskForm):
    text = TextAreaField('Виділений фрагмент / цитата', validators=[DataRequired()])
    note = TextAreaField('Ваша анотація / коментар', validators=[Optional()])
    tags = StringField('Теги (через кому)')
    submit = SubmitField('Зберегти')

class CollectionForm(FlaskForm):
    name = StringField('Назва колекції', validators=[DataRequired()])
    submit = SubmitField('Зберегти')