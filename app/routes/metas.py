from flask import Blueprint, request, jsonify
from datetime import datetime, UTC
from app.database import db_connection
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('metas', __name__)


@bp.route('/meta', methods=['POST'])
@login_required
def criar_meta():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    nome = str(data.get('nome', '')).strip()
    emoji = str(data.get('emoji', '🎯')).strip() or '🎯'
    prazo = str(data.get('prazo', '')).strip()
    try:
        valor_alvo = float(data.get('valor_alvo', 0))
        if valor_alvo <= 0:
            return erro_json('Valor alvo deve ser maior que zero.', 400)
    except (TypeError, ValueError):
        return erro_json('Valor alvo inválido.', 400)
    if not nome:
        return erro_json('Nome da meta é obrigatório.', 400)

    with db_connection() as conn:
        conn.execute(
            "INSERT INTO metas (user_id, nome, emoji, valor_alvo, valor_atual, prazo, criado_em) VALUES (?,?,?,?,0,?,?)",
            (get_current_user_id(), nome, emoji, valor_alvo, prazo, datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok'})


@bp.route('/meta/<int:id>', methods=['POST'])
@login_required
def atualizar_meta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    user_id = get_current_user_id()

    with db_connection() as conn:
        existing = conn.execute("SELECT id FROM metas WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
        if not existing:
            return erro_json('Meta não encontrada.', 404)

        if 'valor_deposito' in data:
            try:
                deposito = float(data['valor_deposito'])
                if deposito <= 0:
                    return erro_json('Valor deve ser maior que zero.', 400)
            except (TypeError, ValueError):
                return erro_json('Valor inválido.', 400)
            conn.execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (deposito, id))
            meta = conn.execute("SELECT valor_atual, valor_alvo FROM metas WHERE id = ?", (id,)).fetchone()
            if meta and meta[0] >= meta[1]:
                conn.execute("UPDATE metas SET concluida = 1 WHERE id = ?", (id,))
        elif 'concluida' in data:
            conn.execute("UPDATE metas SET concluida = ? WHERE id = ?", (int(data['concluida']), id))

    return jsonify({'status': 'ok'})


@bp.route('/meta/<int:id>', methods=['DELETE'])
@login_required
def excluir_meta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM metas WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Meta não encontrada.', 404)
    return jsonify({'status': 'ok'})
