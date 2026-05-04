from flask import Blueprint, request, render_template, session, redirect, url_for, jsonify
from datetime import datetime, UTC
from werkzeug.security import generate_password_hash, check_password_hash
import os
import time
from app.database import db_connection
from app.utils import (
    erro_json, validar_email, validar_csrf, get_csrf_token, get_current_user,
    get_current_user_id, login_required, login_rate_limited, record_login_attempt,
    clear_login_attempts, ext_permitida
)

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if get_current_user_id():
            return redirect(url_for('relatorios.index'))
        return render_template('login.html')

    data = request.form or request.json or {}
    email = str(data.get('email', '')).strip().lower()
    senha = str(data.get('password', ''))

    if not validar_email(email) or not senha:
        return render_template('login.html', erro='Informe email e senha válidos.'), 400

    if login_rate_limited(email):
        return render_template('login.html', erro='Muitas tentativas. Aguarde alguns minutos.'), 429

    with db_connection() as conn:
        user = conn.execute(
            "SELECT id, name, nickname, email, password_hash, avatar_url, onboarding_done FROM users WHERE email = ?",
            (email,)
        ).fetchone()

    if not user or not check_password_hash(user[4], senha):
        record_login_attempt(email)
        return render_template('login.html', erro='Credenciais inválidas.'), 401

    clear_login_attempts(email)
    session['user_id'] = user[0]
    session['user_name'] = user[1]
    session['user_nickname'] = user[2] or ''
    session['user_avatar'] = user[5] or ''
    get_csrf_token()
    redirect_to = url_for('relatorios.index') if user[6] else url_for('onboarding.onboarding_page')
    return render_template('login.html', sucesso='Login realizado. Redirecionando...', redirect_to=redirect_to)


@bp.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'GET':
        return render_template('register.html')

    data = request.form or request.json or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    password_confirm = str(data.get('password_confirm', ''))

    if len(name) < 2:
        return render_template('register.html', erro='Nome deve ter ao menos 2 caracteres.'), 400
    if not validar_email(email):
        return render_template('register.html', erro='Email inválido.'), 400
    if len(password) < 8:
        return render_template('register.html', erro='Senha deve ter ao menos 8 caracteres.'), 400
    if password != password_confirm:
        return render_template('register.html', erro='As senhas não conferem.'), 400

    try:
        with db_connection() as conn:
            exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                return render_template('register.html', erro='Já existe um usuário com esse email.'), 409
            conn.execute(
                "INSERT INTO users (name, nickname, email, password_hash, avatar_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, '', email, generate_password_hash(password), '', datetime.now(UTC).isoformat())
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return render_template('register.html', erro=f'Erro interno: {e}'), 500

    return render_template('register.html', sucesso='Cadastro realizado com sucesso. Faça login.', redirect_to=url_for('auth.login'))


@bp.route('/logout', methods=['POST'])
def logout():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    session.clear()
    return jsonify({'status': 'ok'})


@bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    if request.method == 'GET':
        user = get_current_user()
        if not user:
            return erro_json('Usuário não encontrado.', 404)
        return jsonify(user)

    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    user_id = get_current_user_id()
    data = request.form if request.form else (request.json or {})
    name = str(data.get('name', '')).strip()
    nickname = str(data.get('nickname', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    avatar_url = None

    if len(name) < 2:
        return erro_json('Nome deve ter ao menos 2 caracteres.', 400)
    if not validar_email(email):
        return erro_json('Email inválido.', 400)
    if password and len(password) < 8:
        return erro_json('Senha deve ter ao menos 8 caracteres.', 400)

    avatar_file = request.files.get('avatar')
    if avatar_file and avatar_file.filename:
        if not ext_permitida(avatar_file.filename):
            return erro_json('Formato de imagem inválido. Use PNG, JPG, JPEG ou WEBP.', 400)
        from flask import current_app
        extensao = avatar_file.filename.rsplit('.', 1)[1].lower()
        nome_arquivo = f"user_{user_id}_{int(time.time())}.{extensao}"
        caminho_completo = os.path.join(current_app.static_folder, 'uploads', 'avatars', nome_arquivo)
        os.makedirs(os.path.dirname(caminho_completo), exist_ok=True)
        avatar_file.save(caminho_completo)
        avatar_url = f"/static/uploads/avatars/{nome_arquivo}"

    with db_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if existing:
            return erro_json('Este email já está em uso.', 409)

        if password:
            if avatar_url is not None:
                conn.execute("UPDATE users SET name=?, nickname=?, email=?, password_hash=?, avatar_url=? WHERE id=?",
                    (name, nickname, email, generate_password_hash(password), avatar_url, user_id))
            else:
                conn.execute("UPDATE users SET name=?, nickname=?, email=?, password_hash=? WHERE id=?",
                    (name, nickname, email, generate_password_hash(password), user_id))
        else:
            if avatar_url is not None:
                conn.execute("UPDATE users SET name=?, nickname=?, email=?, avatar_url=? WHERE id=?",
                    (name, nickname, email, avatar_url, user_id))
            else:
                conn.execute("UPDATE users SET name=?, nickname=?, email=? WHERE id=?",
                    (name, nickname, email, user_id))

    session['user_name'] = name
    session['user_nickname'] = nickname
    if avatar_url is not None:
        session['user_avatar'] = avatar_url

    return jsonify({'status': 'ok', 'avatar_url': avatar_url or session.get('user_avatar', '')})
