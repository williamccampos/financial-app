from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from datetime import datetime, UTC
from app.database import db_connection
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id, get_csrf_token

bp = Blueprint('onboarding', __name__)


@bp.route('/onboarding')
@login_required
def onboarding_page():
    user_id = get_current_user_id()
    with db_connection() as conn:
        done = conn.execute("SELECT onboarding_done FROM users WHERE id = ?", (user_id,)).fetchone()
        if done and done[0]:
            return redirect(url_for('relatorios.dashboard'))
    return render_template('onboarding.html', csrf_token=get_csrf_token())


@bp.route('/onboarding/complete', methods=['POST'])
@login_required
def onboarding_complete():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    user_id = get_current_user_id()
    data = request.json or {}
    now = datetime.now(UTC).isoformat()
    mes_atual = datetime.now().strftime('%Y-%m')

    with db_connection() as conn:
        # Passo 1: Renda mensal
        renda = data.get('renda')
        if renda and float(renda) > 0:
            conn.execute(
                "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,1,1,1)",
                (user_id, f"{mes_atual}-01", 'salario', 'Salário', float(renda), 'Outros', ''))

        # Passo 2: Contas fixas
        contas_fixas = data.get('contas_fixas', [])
        for conta in contas_fixas:
            nome = conta.get('nome', '').strip()
            valor = conta.get('valor', 0)
            if nome and float(valor) > 0:
                conn.execute(
                    "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,1,1,1)",
                    (user_id, f"{mes_atual}-01", 'conta', nome, float(valor), 'Moradia', ''))

        # Passo 3: Orçamentos
        orcamentos = data.get('orcamentos', [])
        for orc in orcamentos:
            categoria = orc.get('categoria', '').strip()
            limite = orc.get('limite', 0)
            if categoria and float(limite) > 0:
                conn.execute(
                    "INSERT INTO orcamentos (user_id, categoria, limite, mes) VALUES (?,?,?,?)",
                    (user_id, categoria, float(limite), mes_atual))

        # Marcar onboarding como concluído
        conn.execute("UPDATE users SET onboarding_done = 1 WHERE id = ?", (user_id,))

    return jsonify({'status': 'ok'})
