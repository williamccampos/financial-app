from flask import Blueprint, request, jsonify
from datetime import datetime
import pandas as pd
from app.database import db_connection
from app.database import sql
from app.utils import (
    erro_json, validar_csrf, login_required, get_current_user_id,
    validar_lancamento_payload, query_lancamentos_paginado
)

bp = Blueprint('lancamentos', __name__)


@bp.route('/lancamento', methods=['POST'])
@login_required
def lancamento():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    data = request.json or {}
    erro = validar_lancamento_payload(data)
    if erro:
        return erro_json(erro, 400)

    parcelas = int(data.get('parcelas', 1))
    valor_total = float(data['valor'])
    categoria = data.get('categoria', '')
    vencimento = data.get('vencimento', '')
    recorrente = int(data.get('recorrente', False))
    user_id = get_current_user_id()

    with db_connection() as conn:
        if categoria.lower() == 'cartão de crédito' and parcelas > 1:
            valor_parcela = round(valor_total / parcelas, 2)
            for i in range(parcelas):
                data_parcela = pd.to_datetime(data['data']) + pd.DateOffset(months=i)
                venc = pd.to_datetime(vencimento) + pd.DateOffset(months=i) if vencimento else ''
                vp = valor_parcela if i < parcelas - 1 else round(valor_total - valor_parcela * (parcelas - 1), 2)
                conn.execute(
                    "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (user_id, data_parcela.strftime('%Y-%m-%d'), data['tipo'], data['descricao'],
                     vp, categoria, venc.strftime('%Y-%m-%d') if venc else '', recorrente, parcelas, i + 1))
        else:
            conn.execute(
                "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (user_id, data['data'], data['tipo'], data['descricao'], valor_total,
                 categoria, vencimento, recorrente, parcelas, 1))
    return jsonify({'status': 'ok'})


@bp.route('/excluir/<int:id>', methods=['DELETE'])
@login_required
def excluir(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM lancamentos WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Lançamento não encontrado.', 404)
    return jsonify({'status': 'ok'})


@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    if request.method == 'GET':
        with db_connection() as conn:
            cur = conn.execute("SELECT * FROM lancamentos WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
            row = cur.fetchone()
            if not row:
                return jsonify({'erro': 'Não encontrado'}), 404
            keys = [desc[0] for desc in cur.description]
            return jsonify(dict(zip(keys, row)))

    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    data = request.json or {}
    erro = validar_lancamento_payload(data, update=True)
    if erro:
        return erro_json(erro, 400)

    with db_connection() as conn:
        cur = conn.execute(
            "UPDATE lancamentos SET data=?, tipo=?, descricao=?, valor=?, categoria=?, vencimento=?, recorrente=?, parcelas=?, parcela_atual=? WHERE id=? AND user_id=?",
            (data['data'], data['tipo'], data['descricao'], float(data['valor']),
             data.get('categoria', ''), data.get('vencimento', ''),
             int(data.get('recorrente', False)), int(data.get('parcelas', 1)),
             int(data.get('parcela_atual', 1)), id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Lançamento não encontrado.', 404)
    return jsonify({'status': 'ok'})


@bp.route('/api/lancamentos')
@login_required
def api_lancamentos():
    user_id = get_current_user_id()
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 15)), 100)
    result = query_lancamentos_paginado(
        user_id, page=page, per_page=per_page,
        inicio=request.args.get('inicio'), fim=request.args.get('fim'),
        tipo=request.args.get('tipo'), categoria=request.args.get('categoria'),
        busca=request.args.get('busca'), sort=request.args.get('sort', 'data'),
        order=request.args.get('order', 'desc'))
    return jsonify(result)


@bp.route('/api/spending-line')
@login_required
def api_spending_line():
    user_id = get_current_user_id()
    mes = request.args.get('mes') or datetime.now().strftime('%Y-%m')
    with db_connection() as conn:
        rows = conn.execute(
            sql("SELECT data, tipo, SUM(valor) as total FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? GROUP BY data, tipo ORDER BY data"),
            (user_id, mes)).fetchall()

    tipos_saida = {'saida', 'divida', 'conta'}
    daily = {}
    for r in rows:
        d = r[0]
        if d not in daily:
            daily[d] = {'entrada': 0, 'saida': 0}
        if r[1] in tipos_saida:
            daily[d]['saida'] += r[2]
        else:
            daily[d]['entrada'] += r[2]

    acum_gasto = acum_entrada = 0
    points = []
    for d in sorted(daily.keys()):
        acum_gasto += daily[d]['saida']
        acum_entrada += daily[d]['entrada']
        points.append({'data': d, 'gasto_acumulado': round(acum_gasto, 2), 'entrada_acumulada': round(acum_entrada, 2)})

    orc_total = 0
    with db_connection() as conn:
        row = conn.execute("SELECT COALESCE(SUM(limite), 0) FROM orcamentos WHERE user_id = ? AND mes = ?", (user_id, mes)).fetchone()
        orc_total = row[0] if row else 0

    return jsonify({'mes': mes, 'pontos': points, 'orcamento_total': round(orc_total, 2)})


@bp.route('/api/assinaturas')
@login_required
def api_assinaturas():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT descricao, tipo, categoria, AVG(valor) as media, COUNT(*) as vezes, MAX(data) as ultima FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','conta') GROUP BY descricao, tipo ORDER BY media DESC",
            (user_id,)).fetchall()
    subs = []
    total = 0
    for r in rows:
        val = round(r[3], 2)
        total += val
        subs.append({'descricao': r[0], 'tipo': r[1], 'categoria': r[2] or '', 'valor_medio': val, 'vezes': r[4], 'ultima': r[5]})
    return jsonify({'assinaturas': subs, 'total_mensal': round(total, 2)})


@bp.route('/gerar-recorrentes', methods=['POST'])
@login_required
def gerar_recorrentes():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    user_id = get_current_user_id()
    mes_atual = datetime.now().strftime('%Y-%m')
    count = 0

    with db_connection() as conn:
        recorrentes = conn.execute(
            "SELECT descricao, tipo, MAX(valor) as valor, MAX(categoria) as categoria, MAX(vencimento) as vencimento FROM lancamentos WHERE user_id = ? AND recorrente = 1 GROUP BY descricao, tipo",
            (user_id,)).fetchall()

        for r in recorrentes:
            existe = conn.execute(
                sql("SELECT id FROM lancamentos WHERE user_id = ? AND descricao = ? AND tipo = ? AND strftime('%Y-%m', data) = ?"),
                (user_id, r[0], r[1], mes_atual)).fetchone()
            if not existe:
                hoje = datetime.now()
                dia_venc = ''
                if r[4]:
                    try:
                        dia_venc = datetime.strptime(r[4], '%Y-%m-%d').day
                        dia_venc = f"{hoje.year}-{hoje.month:02d}-{min(dia_venc, 28):02d}"
                    except ValueError:
                        dia_venc = ''
                conn.execute(
                    "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,1,1,1)",
                    (user_id, f"{mes_atual}-01", r[1], r[0], r[2], r[3], dia_venc))
                count += 1

    return jsonify({'status': 'ok', 'gerados': count})
