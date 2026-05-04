from flask import Blueprint, request, jsonify
from datetime import datetime, UTC
from app.database import db_connection, sql
from app.utils import erro_json, validar_email, validar_csrf, login_required, get_current_user_id

bp = Blueprint('social', __name__)


@bp.route('/api/compartilhar', methods=['POST'])
@login_required
def compartilhar():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()
    permissao = str(data.get('permissao', 'leitura')).strip()
    if permissao not in ('leitura', 'escrita'):
        return erro_json('Permissão inválida.', 400)
    if not validar_email(email):
        return erro_json('Email inválido.', 400)
    user_id = get_current_user_id()
    with db_connection() as conn:
        target = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not target:
            return erro_json('Usuário não encontrado.', 404)
        if target[0] == user_id:
            return erro_json('Não é possível compartilhar consigo mesmo.', 400)
        conn.execute(sql("INSERT OR REPLACE INTO compartilhamentos (owner_id, shared_with_id, permissao, criado_em) VALUES (?,?,?,?)"),
            (user_id, target[0], permissao, datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok'})


@bp.route('/api/compartilhamentos')
@login_required
def api_compartilhamentos():
    user_id = get_current_user_id()
    with db_connection() as conn:
        shared = conn.execute("SELECT u.name, u.email, c.permissao, c.id FROM compartilhamentos c JOIN users u ON u.id = c.shared_with_id WHERE c.owner_id = ?", (user_id,)).fetchall()
        received = conn.execute("SELECT u.name, u.email, c.permissao FROM compartilhamentos c JOIN users u ON u.id = c.owner_id WHERE c.shared_with_id = ?", (user_id,)).fetchall()
    return jsonify({
        'compartilhados': [{'nome': r[0], 'email': r[1], 'permissao': r[2], 'id': r[3]} for r in shared],
        'recebidos': [{'nome': r[0], 'email': r[1], 'permissao': r[2]} for r in received]
    })


@bp.route('/api/compartilhar/<int:id>', methods=['DELETE'])
@login_required
def remover_compartilhamento(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM compartilhamentos WHERE id = ? AND owner_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Compartilhamento não encontrado.', 404)
    return jsonify({'status': 'ok'})
