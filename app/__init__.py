from flask import Flask
import os
from app.config import _get_or_create_secret, DB_PATH, DB_TYPE, UPLOAD_DIR
from app.database import init_db


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    flask_app = Flask(__name__, template_folder=os.path.join(base_dir, 'templates'), static_folder=os.path.join(base_dir, 'static'))

    flask_app.secret_key = _get_or_create_secret()
    flask_app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') in ('1', 'true', 'True')
    )

    if DB_TYPE == 'sqlite':
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(os.path.join(flask_app.static_folder, 'uploads', 'avatars'), exist_ok=True)

    from app.routes import auth, lancamentos, orcamentos, metas, relatorios, contas, social, pluggy, ia, importacao, onboarding
    for bp in [auth.bp, lancamentos.bp, orcamentos.bp, metas.bp, relatorios.bp, contas.bp, social.bp, pluggy.bp, ia.bp, importacao.bp, onboarding.bp]:
        flask_app.register_blueprint(bp)

    init_db()

    return flask_app
