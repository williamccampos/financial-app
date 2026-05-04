from flask import Blueprint, request, jsonify
import json
import os
from app.database import db_connection
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('push', __name__)


@bp.route('/api/push/vapid-key')
@login_required
def vapid_public_key():
    key = os.getenv('VAPID_PUBLIC_KEY', '')
    if not key:
        return erro_json('Push não configurado.', 503)
    return jsonify({'publicKey': key})


@bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def subscribe():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    subscription = data.get('subscription')
    if not subscription or not subscription.get('endpoint'):
        return erro_json('Subscription inválida.', 400)

    user_id = get_current_user_id()
    endpoint = subscription['endpoint']
    sub_json = json.dumps(subscription)

    with db_connection() as conn:
        existing = conn.execute("SELECT id FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint)).fetchone()
        if existing:
            conn.execute("UPDATE push_subscriptions SET subscription_json = ? WHERE id = ?", (sub_json, existing[0]))
        else:
            conn.execute("INSERT INTO push_subscriptions (user_id, endpoint, subscription_json) VALUES (?,?,?)",
                (user_id, endpoint, sub_json))
    return jsonify({'status': 'ok'})


@bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    endpoint = data.get('endpoint', '')
    user_id = get_current_user_id()
    with db_connection() as conn:
        conn.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
    return jsonify({'status': 'ok'})


@bp.route('/api/push/test', methods=['POST'])
@login_required
def test_push():
    """Envia uma notificação de teste para o usuário atual."""
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    user_id = get_current_user_id()
    sent = _send_to_user(user_id, 'FinanZen', 'Notificações ativadas com sucesso! 🎉')
    return jsonify({'status': 'ok', 'sent': sent})


def _send_to_user(user_id, title, body, url='/dashboard'):
    """Envia push para todas as subscriptions de um usuário."""
    vapid_private = os.getenv('VAPID_PRIVATE_KEY', '')
    vapid_email = os.getenv('VAPID_EMAIL', 'mailto:admin@finanzen.app')
    if not vapid_private:
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return 0

    with db_connection() as conn:
        rows = conn.execute("SELECT id, subscription_json FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall()

    payload = json.dumps({'title': title, 'body': body, 'url': url})
    sent = 0
    expired_ids = []

    for row in rows:
        sub = json.loads(row[1])
        try:
            webpush(sub, payload, vapid_private_key=vapid_private,
                    vapid_claims={'sub': vapid_email})
            sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                expired_ids.append(row[0])

    if expired_ids:
        with db_connection() as conn:
            for eid in expired_ids:
                conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (eid,))

    return sent
