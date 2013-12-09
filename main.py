# coding: utf-8
from __future__ import unicode_literals
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, escape, jsonify
from pymongo import MongoClient
import re
from datetime import datetime
import hashlib
import string

# config
DEBUG = True
SECRET_KEY = 'Bv\x96\xb0\x06\xdf\xe0\xbd\xe3S\xb4*\x1dWa\xedb\r\xe1\nmGe\xff\xc1\xa9\xb7\x93\x85m'


app = Flask(__name__)
app.config.from_object(__name__)

client = MongoClient()
db = client.tracker

def make_hash(obj):
    return hashlib.sha1(obj).hexdigest()

categories = ['Программирование', 'Дизайн', 'Верстка']
allowed_message_types = ['comments', 'bugs', 'todos']
statuses = ['не рассмотренно', 'рассмотренно', 'принято', 'отклонено']

@app.route('/')
def main():
    return render_template('main.html', projects=db.projects.find().sort( [('time', -1)] ))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('logged'):
        flash('Выйдите, прежде чем регистрироваться')
        return redirect(url_for('main'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_categories = [cat for num, cat in enumerate(categories) if request.form.get('checkbox{0}'.format(num))]
        errors = []
        pattern = r'[^a-zA-Z0-9_]'
        if not username or re.search(pattern, username):
            errors.append('Некорректное имя пользователя. Разрешена латиница, знаки подчеркивания и цифры.')
        if not password or re.search(pattern, password):
            errors.append('Некорректный пароль. Разрешена латиница, знаки подчеркивания и цифры.')
        if db.users.find_one( {'username': username} ):
            errors.append('Имя пользователя уже занято.')
        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('register'))
        hashed_password = make_hash(password)
        db.users.insert({
            'username': username,
            'hash': hashed_password,
            'categories': user_categories
        })
        flash('Вы успешно зарегистрированы.', 'success')
        session['logged'] = True
        session['username'] = request.form['username']
        return redirect(url_for('main'))
    if request.method == 'GET':
        return render_template('register.html', categories=categories, enumerate=enumerate)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = make_hash(password)
        if db.users.find_one( {'username': username, 'hash': hashed_password} ):
            session['logged'] = True
            session['username'] = request.form['username']
            flash('Успешный вход.', 'info')
            return redirect(url_for('main'))
        else:
            flash('Неправильное имя пользвателя или пароль.', 'error')
            return redirect(url_for('login'))
    if request.method == 'GET':
        return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged', None)
    session.pop('username', None)
    flash('Успешный выход.', 'info')
    return redirect(url_for('main'))


@app.route('/add', methods=['GET', 'POST'])
def add():
    if not session.get('logged'):
        flash('Вы должны войти, чтобы добавить проект.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        project = {}
        project['name'] = request.form['name']
        project['url'] = request.form['url']
        project['description'] = request.form['description']
        project['status'] = request.form['status']
        project['progress'] = request.form['progress']
        author = session['username']
        project['moderators'] = map(string.strip, request.form['moderators'].split(','))
        time = datetime.now()
        errors = []
        pattern = r'[^a-zA-Z0-9_]'
        if not project['name']:
            errors.append('Имя не должно быть пустым.')
        if re.search(pattern, project['url']):
            errors.append('URL может содержать только латиницу, цифры и знак подчеркивания.')
        try:
            project['progress'] = int(project['progress'])
        except ValueError:
            errors.append('Прогресс должен быть числом.')
        if type(project['progress']) is int and not 0 <= project['progress'] <= 100:
            errors.append('Прогресс должен быть числом от 0 до 100.')
        for m in project['moderators']:
            if m and not db.users.find_one( {'username': m} ):
                errors.append('Пользователя {0} не существует'.format(escape(m)))
        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('add.html', project=project)
        db.projects.insert( {
            'name': project['name'],
            'url': project['url'],
            'description': project['description'],
            'status': project['status'],
            'progress': project['progress'],
            'author': session['username'],
            'moderators': project['moderators'],
            'time': time,
            'comments': [],
            'bugs': [],
            'todos': []
        } )
        return redirect(url_for('get_project', url=project['url']))
    if request.method == 'GET':
        return render_template('add.html')

@app.route('/project/<url>')
def get_project(url):
    def generate_urls(moderators):
        def yoba(moder):
            return '<a href="{0}">{1}</a>'.format(url_for('user', name=moder), moder)
        return ', '.join(map(yoba, moderators))
    
    project = db.projects.find_one( {'url': url} )
    if not project:
        abort(404)
    return render_template('project.html', project=project, statuses=statuses, enumerate=enumerate, generate_urls=generate_urls)

@app.route('/modify/<url>', methods=['GET', 'POST'])
def modify_project(url):
    project = db.projects.find_one( {'url': url} )
    if not project:
        abort(404)
    if not session.get('logged'):
        flash('Вы должны войти, чтобы изменять проект.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        username = session.get('username')
        if username != project['author'] and username not in project['moderators']:
            flash('Вы не можете изменять чужой проект', 'error')
            return redirect(url_for('get_project', url=url))
        oldurl = project['url']
        project['name'] = request.form['name']
        project['url'] = request.form['url']
        project['description'] = request.form['description']
        project['status'] = request.form['status']
        project['progress'] = request.form['progress']
        project['moderators'] = map(string.strip, request.form['moderators'].split(','))
        errors = []
        pattern = r'[^a-zA-Z0-9_-]'
        if not project['name']:
            errors.append('Имя не должно быть пустым.')
        if re.search(pattern, project['url']):
            errors.append('URL может содержать только латиницу, цифры, минус и знаки подчеркивания.')
        try:
            project['progress'] = int(project['progress'])
        except ValueError:
            errors.append('Прогресс должен быть числом.')
        if type(project['progress']) is int and not 0 <= project['progress'] <= 100:
            errors.append('Прогресс должен быть числом от 0 до 100.')
        for m in project['moderators']:
            if m and not db.users.find_one( {'username': m} ):
                errors.append('Пользователя {0} не существует'.format(escape(m)))
        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('modify.html', project=project)
        set_to = {
            '$set': {
                'name': project['name'],
                'url': project['url'],
                'description': project['description'],
                'status': project['status'],
                'progress': project['progress']
            }
        }
        if username == project['author']:
            set_to['$set']['moderators'] = project['moderators']
        db.projects.update(
            {
                'url': oldurl
            }, set_to
        )
        return redirect(url_for('get_project', url=project['url']))
    if request.method == 'GET':
        return render_template('modify.html', project=project)

@app.route('/delete/project/<url>')
def delete_project(url, confirm=False):
    confirm = request.args.get('confirm') == 'True'
    project = db.projects.find_one( {'url': url} )
    if not project:
        abort(404)
    if not session['logged']:
        flash('Вы должны быть залогинены, чтобы удалять проект', 'error')
        return redirect(url_for('login'))
    if not confirm:
        return render_template('confirm_delete.html', project=project)
    db.projects.remove( {'url': url} )
    flash('Проект {0} успешно удален'.format(escape(project['name'])), 'info')
    return redirect(url_for('main'))

@app.route('/add_message/<url>', methods=['POST'])
def add_message(url):
    if not session.get('logged'):
        flash('Вы должны быть залогинены, чтобы добавлять комментарий', 'error')
        return redirect(url_for('login'))
    message_type = request.form['type']
    if message_type not in allowed_message_types:
        return redirect(url_for('get_project', url=url))
    text = request.form['message']
    if len(text) > 1000:
        flash('Сообщение слишком большое', 'error')
        return redirect(url_for('get_project', url=url))
    if not text.strip():
        flash('Сообщение не может быть пустым.', 'error')
        return redirect(url_for('get_project', url=url))
    author = session.get('username')
    time = datetime.now()
    db.projects.update(
        {
            'url': url
        },
        {
            '$push': {
                message_type: {
                    'author': author,
                    'time': time,
                    'text': text,
                    'status': 'не рассмотренно'
                }
            },
        }
    )
    return redirect(url_for('get_project', url=url))


@app.route('/delete/<url>/<message_types>/<num>')
def delete_message(url, message_types, num):
    try:
        num = int(num)
    except Exception:
        return redirect(url_for('get_project', url=url))
    if message_types not in allowed_message_types:
        return redirect(url_for('get_project', url_for))
    project = db.projects.find_one( {'url': url} )
    username = session.get('username')
    messages = project.get(message_types)
    if num < 0 or num >= len(messages):
        return redirect(url_for('get_project', url=url))
    message = messages[num]
    if not session.get('logged'):
        flash('Вы должны быть залогинены, чтобы удалять комментарии.', 'error')
        return redirect(url_for('login'))
    if project.get('author') != username and message.get('author') != username:
        flash('Вы не можете удалить этот комментарий.', 'error')
        return redirect(url_for('get_project', url=url))
    db.projects.update(
        {
            'url': url
        },
        {
            '$unset': {
                '{0}.{1}'.format(message_types, num): 1
            }
        }
    )
    db.projects.update(
        {
            'url': url
        },
        {
            '$pull': {
                message_types: None
            }
        }
    )
    return redirect(url_for('get_project', url=url))

@app.route('/change_message_status', methods=['POST'])
def change_message_status():
    url = request.form.get('url')
    message_types = request.form.get('message_types')
    num = request.form.get('num')
    status = request.form.get('status')
    project = db.projects.find_one( {'url': url} )
    messages = project.get(message_types)
    user = session.get('username')
    project_author = project['author']
    r = redirect(url_for('get_project', url=url))
    if user != project_author:
        return r
    try:
        num = int(num)
    except ValueError:
        return r
    if num < 0 or num >= len(messages):
        return r
    if message_types not in allowed_message_types:
        return r
    db.projects.update(
        {
            'url': url
        },
        {
            '$set': {
                '{0}.{1}.status'.format(message_types, num): status
            }
        }
    )
    return r

@app.route('/users')
def user_list():
    users = db.users.find().sort( [('username', 1)] )
    return render_template('users.html', users=users)

@app.route('/user/<name>')
def user(name):
    user = db.users.find_one( {'username': name} )
    if not user:
        abort(404)
    projects = db.projects.find({
        'author': {'$regex': name}
    })
    return render_template('profile.html', user=user, projects=projects.sort( [('time', -1)] ))

@app.route('/search', methods=['GET', 'POST'])
def search():
    search = request.form['search']
    r = {'$regex': search, '$options': '-i'}
    projects = db.projects.find({
        '$or': [
            {'name': r},
            {'description': r},
            {'author': r},
            {'status': r}
        ]
    })
    return render_template('search.html', projects=projects.sort( [('time', -1)] ))

@app.route('/_add_numbers')
def add_numbers():
    from operator import add, sub, mul, div
    a = request.args.get('a', 0, type=int)
    action = {
        '+': add,
        '-': sub,
        '*': mul,
        '/': lambda a, b: 'NaN' if b == 0 else div(a, b)
    }.get(request.args.get('action', lambda *a, **kw: None, type=str))
    b = request.args.get('b', 0, type=int)
    return jsonify(result=action(a, b))

@app.route('/ajax')
def ajax_test():
    return render_template('ajax_test.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run()
