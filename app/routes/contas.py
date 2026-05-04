from flask import Blueprint, request, jsonify
from datetime import datetime, UTC
from app.database import db_connection
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('contas', __name__)


@bp.route('/api/contas')
@login_required
def api_contas():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute("SELECT id, nome, emoji, tipo, saldo_inicial, cor, ativa FROM contas WHERE user_id = ? ORDER BY nome", (user_id,)).fetchall()
        contas = []
        for r in rows:
            mov = conn.execute("SELECT COALESCE(SUM(CASE WHEN tipo IN ('entrada','salario','recebimento') THEN valor ELSE -valor END), 0) FROM lancamentos WHERE user_id = ? AND conta_id = ?", (user_id, r[0])).fetchone()[0]
            contas.append({'id': r[0], 'nome': r[1], 'emoji': r[2], 'tipo': r[3], 'saldo_inicial': r[4], 'cor': r[5], 'ativa': bool(r[6]), 'saldo': round(r[4] + mov, 2)})
    return jsonify(contas)


@bp.route('/api/contas', methods=['POST'])
@login_required
def criar_conta():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    nome = str(data.get('nome', '')).strip()
    if not nome:
        return erro_json('Nome é obrigatório.', 400)
    try:
        saldo_inicial = float(data.get('saldo_inicial', 0))
    except (TypeError, ValueError):
        saldo_inicial = 0
    with db_connection() as conn:
        conn.execute("INSERT INTO contas (user_id, nome, emoji, tipo, saldo_inicial, cor, criado_em) VALUES (?,?,?,?,?,?,?)",
            (get_current_user_id(), nome, str(data.get('emoji', '🏦')).strip() or '🏦',
             str(data.get('tipo', 'corrente')).strip(), saldo_inicial,
             str(data.get('cor', '#007aff')).strip(), datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok'})


@bp.route('/api/contas/<int:id>', methods=['DELETE'])
@login_required
def excluir_conta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM contas WHERE id = ? AND user_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Conta não encontrada.', 404)
    return jsonify({'status': 'ok'})


@bp.route('/api/patrimonio')
@login_required
def api_patrimonio():
    user_id = get_current_user_id()
    with db_connection() as conn:
        contas = conn.execute("SELECT c.id, c.nome, c.emoji, c.tipo, c.saldo_inicial, c.cor, COALESCE(SUM(CASE WHEN l.tipo IN ('entrada','salario','recebimento') THEN l.valor ELSE -l.valor END), 0) FROM contas c LEFT JOIN lancamentos l ON l.conta_id = c.id AND l.user_id = c.user_id WHERE c.user_id = ? AND c.ativa = 1 GROUP BY c.id", (user_id,)).fetchall()
        sem_conta = conn.execute("SELECT COALESCE(SUM(CASE WHEN tipo IN ('entrada','salario','recebimento') THEN valor ELSE -valor END), 0) FROM lancamentos WHERE user_id = ? AND (conta_id IS NULL OR conta_id = 0)", (user_id,)).fetchone()[0]
    items = []
    total = float(sem_conta)
    if sem_conta != 0:
        items.append({'nome': 'Geral', 'emoji': '💰', 'tipo': 'geral', 'saldo': round(sem_conta, 2), 'cor': '#8e8e93'})
    for r in contas:
        saldo = round(r[4] + r[6], 2)
        total += saldo
        items.append({'id': r[0], 'nome': r[1], 'emoji': r[2], 'tipo': r[3], 'saldo': saldo, 'cor': r[5]})
    evolucao = []
    with db_connection() as conn:
        rows = conn.execute("SELECT strftime('%Y-%m', data) as mes, COALESCE(SUM(CASE WHEN tipo IN ('entrada','salario','recebimento') THEN valor ELSE -valor END), 0) FROM lancamentos WHERE user_id = ? GROUP BY mes ORDER BY mes DESC LIMIT 6", (user_id,)).fetchall()
    acum = 0
    for r in sorted(rows, key=lambda x: x[0]):
        acum += r[1]
        evolucao.append({'mes': r[0], 'patrimonio': round(acum, 2)})
    return jsonify({'contas': items, 'total': round(total, 2), 'evolucao': evolucao})
