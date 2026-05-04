from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
from app.database import db_connection, sql
from app.utils import erro_json, login_required, get_current_user_id, get_current_user, common_template_context

bp = Blueprint('familia', __name__)


@bp.route('/familia')
@login_required
def familia_page():
    user = get_current_user()
    context = common_template_context(user, 'familia')
    return render_template('familia.html', dados=[], saldo=0, entrada=0, saida=0, **context)


def _get_family_members(user_id):
    """Returns user IDs of family members (bidirectional 'escrita' sharing)."""
    with db_connection() as conn:
        # Users I shared with (escrita) + users who shared with me (escrita)
        shared_by_me = conn.execute(
            "SELECT shared_with_id FROM compartilhamentos WHERE owner_id = ? AND permissao = 'escrita'",
            (user_id,)).fetchall()
        shared_with_me = conn.execute(
            "SELECT owner_id FROM compartilhamentos WHERE shared_with_id = ? AND permissao = 'escrita'",
            (user_id,)).fetchall()
    members = set([r[0] for r in shared_by_me] + [r[0] for r in shared_with_me])
    members.add(user_id)
    return list(members)


@bp.route('/api/familia/membros')
@login_required
def membros():
    user_id = get_current_user_id()
    member_ids = _get_family_members(user_id)
    if len(member_ids) <= 1:
        return jsonify({'membros': [], 'msg': 'Nenhum membro familiar. Compartilhe com permissão "escrita" para criar sua família.'})
    with db_connection() as conn:
        placeholders = ','.join(['?'] * len(member_ids))
        rows = conn.execute(
            f"SELECT id, name, nickname, avatar_url FROM users WHERE id IN ({placeholders})",
            member_ids).fetchall()
    membros = [{'id': r[0], 'nome': r[2] or r[1], 'avatar_url': r[3] or ''} for r in rows]
    return jsonify({'membros': membros})


@bp.route('/api/familia/resumo')
@login_required
def resumo():
    user_id = get_current_user_id()
    member_ids = _get_family_members(user_id)
    if len(member_ids) <= 1:
        return erro_json('Nenhum membro familiar encontrado.', 404)

    mes = request.args.get('mes') or datetime.now().strftime('%Y-%m')
    placeholders = ','.join(['?'] * len(member_ids))

    with db_connection() as conn:
        # Gastos por membro
        rows = conn.execute(
            sql(f"SELECT user_id, tipo, SUM(valor) FROM lancamentos WHERE user_id IN ({placeholders}) AND strftime('%Y-%m', data) = ? GROUP BY user_id, tipo"),
            member_ids + [mes]).fetchall()

        # Nomes
        users = conn.execute(
            f"SELECT id, name, nickname FROM users WHERE id IN ({placeholders})",
            member_ids).fetchall()

    user_map = {r[0]: r[2] or r[1] for r in users}
    tipos_saida = {'saida', 'divida', 'conta'}

    with db_connection() as conn:
        orc = conn.execute(
            f"SELECT COALESCE(SUM(limite), 0) FROM orcamentos WHERE user_id IN ({placeholders}) AND mes = ?",
            member_ids + [mes]).fetchone()

    por_membro = {}
    total_entradas = total_saidas = 0
    for r in rows:
        uid, tipo, valor = r[0], r[1], r[2]
        if uid not in por_membro:
            por_membro[uid] = {'nome': user_map.get(uid, ''), 'entradas': 0, 'saidas': 0}
        if tipo in tipos_saida:
            por_membro[uid]['saidas'] += valor
            total_saidas += valor
        else:
            por_membro[uid]['entradas'] += valor
            total_entradas += valor

    return jsonify({
        'mes': mes,
        'total_entradas': round(total_entradas, 2),
        'total_saidas': round(total_saidas, 2),
        'saldo': round(total_entradas - total_saidas, 2),
        'orcamento_familiar': round(orc[0], 2) if orc else 0,
        'por_membro': [{'id': uid, **data, 'entradas': round(data['entradas'], 2), 'saidas': round(data['saidas'], 2)} for uid, data in por_membro.items()]
    })


@bp.route('/api/familia/gastos-categoria')
@login_required
def gastos_categoria():
    user_id = get_current_user_id()
    member_ids = _get_family_members(user_id)
    if len(member_ids) <= 1:
        return erro_json('Nenhum membro familiar encontrado.', 404)

    mes = request.args.get('mes') or datetime.now().strftime('%Y-%m')
    placeholders = ','.join(['?'] * len(member_ids))

    with db_connection() as conn:
        rows = conn.execute(
            sql(f"SELECT user_id, categoria, SUM(valor) FROM lancamentos WHERE user_id IN ({placeholders}) AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta') GROUP BY user_id, categoria ORDER BY SUM(valor) DESC"),
            member_ids + [mes]).fetchall()
        users = conn.execute(
            f"SELECT id, name, nickname FROM users WHERE id IN ({placeholders})",
            member_ids).fetchall()

    user_map = {r[0]: r[2] or r[1] for r in users}

    # Consolidado por categoria
    por_categoria = {}
    for r in rows:
        cat = r[1] or 'Sem categoria'
        if cat not in por_categoria:
            por_categoria[cat] = {'total': 0, 'membros': []}
        por_categoria[cat]['total'] += r[2]
        por_categoria[cat]['membros'].append({'nome': user_map.get(r[0], ''), 'valor': round(r[2], 2)})

    categorias = [{'categoria': k, 'total': round(v['total'], 2), 'membros': v['membros']}
                  for k, v in sorted(por_categoria.items(), key=lambda x: -x[1]['total'])]

    return jsonify({'mes': mes, 'categorias': categorias})
