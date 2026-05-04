from flask import Blueprint, request, jsonify
from datetime import datetime, UTC
import requests as http_requests
import os
from app.database import db_connection
from app.config import PLUGGY_API_URL
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('pluggy', __name__)


def pluggy_get_api_key():
    client_id = os.getenv('PLUGGY_CLIENT_ID', '')
    client_secret = os.getenv('PLUGGY_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return None
    res = http_requests.post(f'{PLUGGY_API_URL}/auth', json={
        'clientId': client_id, 'clientSecret': client_secret
    }, timeout=10)
    if res.status_code == 200:
        return res.json().get('apiKey')
    return None


@bp.route('/api/pluggy/connect-token', methods=['POST'])
@login_required
def pluggy_connect_token():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    api_key = pluggy_get_api_key()
    if not api_key:
        return erro_json('Pluggy não configurado. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.', 500)
    res = http_requests.post(f'{PLUGGY_API_URL}/connect_token', json={
        'clientUserId': str(get_current_user_id())
    }, headers={'X-API-KEY': api_key}, timeout=10)
    if res.status_code in (200, 201):
        return jsonify({'accessToken': res.json().get('accessToken')})
    return erro_json('Erro ao gerar token de conexão.', 502)


@bp.route('/api/pluggy/item-connected', methods=['POST'])
@login_required
def pluggy_item_connected():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    item_id = str(data.get('itemId', '')).strip()
    connector_name = str(data.get('connectorName', '')).strip()
    if not item_id:
        return erro_json('itemId é obrigatório.', 400)
    user_id = get_current_user_id()
    with db_connection() as conn:
        conn.execute("INSERT INTO contas (user_id, nome, emoji, tipo, saldo_inicial, cor, criado_em) VALUES (?,?,'🏦','corrente',0,'#007aff',?)",
            (user_id, connector_name or 'Banco conectado', datetime.now(UTC).isoformat()))
        conta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO conexoes_bancarias (user_id, item_id, connector_name, conta_id, criado_em) VALUES (?,?,?,?,?)",
            (user_id, item_id, connector_name, conta_id, datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok', 'conta_id': conta_id})


@bp.route('/api/pluggy/sincronizar', methods=['POST'])
@login_required
def pluggy_sincronizar():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    api_key = pluggy_get_api_key()
    if not api_key:
        return erro_json('Pluggy não configurado.', 500)
    user_id = get_current_user_id()
    headers = {'X-API-KEY': api_key}
    total_importados = 0
    with db_connection() as conn:
        conexoes = conn.execute("SELECT item_id, conta_id FROM conexoes_bancarias WHERE user_id = ? AND status = 'connected'", (user_id,)).fetchall()
    for item_id, conta_id in conexoes:
        acc_res = http_requests.get(f'{PLUGGY_API_URL}/accounts?itemId={item_id}', headers=headers, timeout=15)
        if acc_res.status_code != 200:
            continue
        for account in acc_res.json().get('results', []):
            account_id = account.get('id')
            page = 1
            while True:
                tx_res = http_requests.get(f'{PLUGGY_API_URL}/transactions?accountId={account_id}&page={page}', headers=headers, timeout=15)
                if tx_res.status_code != 200:
                    break
                tx_data = tx_res.json()
                transactions = tx_data.get('results', [])
                if not transactions:
                    break
                with db_connection() as conn:
                    for tx in transactions:
                        tx_id = tx.get('id', '')
                        existe = conn.execute("SELECT id FROM lancamentos WHERE user_id = ? AND descricao LIKE ? AND conta_id = ?",
                            (user_id, f'%[pluggy:{tx_id[:8]}]%', conta_id)).fetchone()
                        if existe:
                            continue
                        valor = abs(float(tx.get('amount', 0)))
                        if valor == 0:
                            continue
                        is_credit = tx.get('type') == 'CREDIT' or float(tx.get('amount', 0)) > 0
                        tipo = 'entrada' if is_credit else 'saida'
                        data_tx = (tx.get('date') or '')[:10]
                        descricao = tx.get('description', tx.get('descriptionRaw', ''))
                        categoria = tx.get('category', '') or ''
                        descricao_marcada = f"{descricao} [pluggy:{tx_id[:8]}]"
                        conn.execute("INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual, conta_id) VALUES (?,?,?,?,?,?,'',0,1,1,?)",
                            (user_id, data_tx, tipo, descricao_marcada, valor, categoria, conta_id))
                        total_importados += 1
                if page >= tx_data.get('totalPages', 1):
                    break
                page += 1
        with db_connection() as conn:
            conn.execute("UPDATE conexoes_bancarias SET atualizado_em = ? WHERE item_id = ? AND user_id = ?",
                (datetime.now(UTC).isoformat(), item_id, user_id))
    return jsonify({'status': 'ok', 'importados': total_importados})


@bp.route('/api/pluggy/conexoes')
@login_required
def pluggy_conexoes():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute("SELECT cb.id, cb.item_id, cb.connector_name, cb.status, cb.atualizado_em, c.nome as conta_nome FROM conexoes_bancarias cb LEFT JOIN contas c ON c.id = cb.conta_id WHERE cb.user_id = ?", (user_id,)).fetchall()
    return jsonify([{'id': r[0], 'item_id': r[1], 'connector_name': r[2], 'status': r[3], 'atualizado_em': r[4], 'conta_nome': r[5]} for r in rows])


@bp.route('/api/pluggy/conexoes/<int:id>', methods=['DELETE'])
@login_required
def pluggy_remover_conexao(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM conexoes_bancarias WHERE id = ? AND user_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Conexão não encontrada.', 404)
    return jsonify({'status': 'ok'})
