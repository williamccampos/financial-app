from flask import Blueprint, request, jsonify
from datetime import datetime
from app.database import db_connection, sql
from app.config import CATEGORIAS_PADRAO
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('orcamentos', __name__)


@bp.route('/orcamento', methods=['POST'])
@login_required
def criar_orcamento():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    categoria = str(data.get('categoria', '')).strip()
    limite = data.get('limite')
    mes = str(data.get('mes', '')).strip()
    if not categoria or not mes:
        return erro_json('Categoria e mês são obrigatórios.', 400)
    try:
        limite = float(limite)
        if limite <= 0:
            return erro_json('Limite deve ser maior que zero.', 400)
    except (TypeError, ValueError):
        return erro_json('Limite inválido.', 400)

    with db_connection() as conn:
        conn.execute(sql("INSERT OR REPLACE INTO orcamentos (user_id, categoria, limite, mes) VALUES (?,?,?,?)"),
            (get_current_user_id(), categoria, limite, mes))
    return jsonify({'status': 'ok'})


@bp.route('/orcamento/<int:id>', methods=['DELETE'])
@login_required
def excluir_orcamento(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM orcamentos WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Orçamento não encontrado.', 404)
    return jsonify({'status': 'ok'})


@bp.route('/api/categorias')
@login_required
def api_categorias():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute("SELECT nome, emoji FROM categorias WHERE user_id = ? ORDER BY nome", (user_id,)).fetchall()
    if rows:
        return jsonify([{'nome': r[0], 'emoji': r[1]} for r in rows])
    return jsonify([{'nome': c[0], 'emoji': c[1]} for c in CATEGORIAS_PADRAO])


@bp.route('/api/categorias', methods=['POST'])
@login_required
def salvar_categoria():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    nome = str(data.get('nome', '')).strip()
    emoji = str(data.get('emoji', '📁')).strip() or '📁'
    if not nome:
        return erro_json('Nome é obrigatório.', 400)
    with db_connection() as conn:
        conn.execute(sql("INSERT OR REPLACE INTO categorias (user_id, nome, emoji) VALUES (?,?,?)"),
            (get_current_user_id(), nome, emoji))
    return jsonify({'status': 'ok'})


@bp.route('/api/rollover')
@login_required
def api_rollover():
    user_id = get_current_user_id()
    hoje = datetime.now()
    mes_atual = hoje.strftime('%Y-%m')
    mes_anterior = f"{hoje.year - 1}-12" if hoje.month == 1 else f"{hoje.year}-{hoje.month - 1:02d}"
    rollovers = []
    with db_connection() as conn:
        for cat, limite in conn.execute("SELECT categoria, limite FROM orcamentos WHERE user_id = ? AND mes = ?", (user_id, mes_anterior)).fetchall():
            gasto = conn.execute(sql("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND categoria = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')"), (user_id, cat, mes_anterior)).fetchone()[0]
            sobra = round(limite - gasto, 2)
            if sobra > 0:
                rollovers.append({'categoria': cat, 'sobra': sobra})
    return jsonify({'rollovers': rollovers, 'mes_anterior': mes_anterior, 'mes_atual': mes_atual})
