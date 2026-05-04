from flask import Blueprint, request, jsonify
from datetime import datetime
import calendar
from app.database import db_connection
from app.config import CATEGORIA_KEYWORDS
from app.utils import login_required, get_current_user_id

bp = Blueprint('ia', __name__)


@bp.route('/api/sugerir-categoria')
@login_required
def sugerir_categoria():
    descricao = str(request.args.get('descricao', '')).strip().lower()
    if not descricao:
        return jsonify({'categoria': '', 'confianca': 0})
    user_id = get_current_user_id()
    with db_connection() as conn:
        row = conn.execute(
            "SELECT categoria, COUNT(*) as freq FROM lancamentos WHERE user_id = ? AND LOWER(descricao) LIKE ? AND categoria != '' GROUP BY categoria ORDER BY freq DESC LIMIT 1",
            (user_id, f'%{descricao}%')).fetchone()
    if row and row[0]:
        return jsonify({'categoria': row[0], 'confianca': 0.95, 'fonte': 'historico'})
    for cat, keywords in CATEGORIA_KEYWORDS.items():
        for kw in keywords:
            if kw in descricao:
                return jsonify({'categoria': cat, 'confianca': 0.75, 'fonte': 'keywords'})
    return jsonify({'categoria': '', 'confianca': 0})


@bp.route('/api/insights')
@login_required
def api_insights():
    user_id = get_current_user_id()
    mes_atual = datetime.now().strftime('%Y-%m')
    insights = []
    with db_connection() as conn:
        atual = conn.execute(
            "SELECT categoria, SUM(valor) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta') AND categoria != '' GROUP BY categoria",
            (user_id, mes_atual)).fetchall()
        medias = conn.execute(
            "SELECT categoria, AVG(total) FROM (SELECT categoria, strftime('%Y-%m', data) as mes, SUM(valor) as total FROM lancamentos WHERE user_id = ? AND tipo IN ('saida','divida','conta') AND categoria != '' AND strftime('%Y-%m', data) < ? GROUP BY categoria, mes) GROUP BY categoria",
            (user_id, mes_atual)).fetchall()
    media_map = {r[0]: r[1] for r in medias}
    for cat, gasto in atual:
        media = media_map.get(cat)
        if not media or media == 0:
            continue
        variacao = round(((gasto - media) / media) * 100, 1)
        if variacao > 20:
            insights.append({'tipo': 'alerta', 'icone': '📈', 'mensagem': f'Você gastou {variacao}% a mais em {cat} este mês (R$ {gasto:.0f}) comparado à média (R$ {media:.0f}).'})
        elif variacao < -20:
            insights.append({'tipo': 'positivo', 'icone': '📉', 'mensagem': f'Parabéns! Você economizou {abs(variacao)}% em {cat} este mês (R$ {gasto:.0f} vs média R$ {media:.0f}).'})
    with db_connection() as conn:
        entradas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('entrada','salario','recebimento')", (user_id, mes_atual)).fetchone()[0]
        saidas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')", (user_id, mes_atual)).fetchone()[0]
    saldo = entradas - saidas
    if saldo > 0:
        taxa_poupanca = round((saldo / entradas) * 100, 1) if entradas > 0 else 0
        insights.append({'tipo': 'positivo', 'icone': '💰', 'mensagem': f'Você está poupando {taxa_poupanca}% da sua renda este mês (R$ {saldo:.0f}).'})
    elif saldo < 0:
        insights.append({'tipo': 'alerta', 'icone': '⚠️', 'mensagem': f'Atenção: seus gastos superaram sua renda em R$ {abs(saldo):.0f} este mês.'})
    if atual:
        maior = max(atual, key=lambda x: x[1])
        insights.append({'tipo': 'info', 'icone': '🏷️', 'mensagem': f'Sua maior categoria de gasto é {maior[0]} com R$ {maior[1]:.0f} este mês.'})
    return jsonify({'insights': insights, 'mes': mes_atual})


@bp.route('/api/projecao')
@login_required
def api_projecao():
    user_id = get_current_user_id()
    hoje = datetime.now()
    mes_atual = hoje.strftime('%Y-%m')
    dia_atual = hoje.day
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_restantes = dias_no_mes - dia_atual
    with db_connection() as conn:
        entradas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('entrada','salario','recebimento')", (user_id, mes_atual)).fetchone()[0]
        saidas_ate_agora = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')", (user_id, mes_atual)).fetchone()[0]
        recorrentes_pendentes = conn.execute(
            "SELECT COALESCE(SUM(sub.valor),0) FROM (SELECT descricao, tipo, MAX(valor) as valor FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','divida','conta') GROUP BY descricao, tipo) sub WHERE sub.descricao NOT IN (SELECT descricao FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta'))",
            (user_id, user_id, mes_atual)).fetchone()[0]
    gasto_diario = saidas_ate_agora / dia_atual if dia_atual > 0 else 0
    projecao_gastos = saidas_ate_agora + (gasto_diario * dias_restantes) + recorrentes_pendentes
    saldo_projetado = entradas - projecao_gastos
    return jsonify({
        'mes': mes_atual, 'dia_atual': dia_atual, 'dias_restantes': dias_restantes,
        'entradas': round(entradas, 2), 'saidas_ate_agora': round(saidas_ate_agora, 2),
        'gasto_diario_medio': round(gasto_diario, 2), 'recorrentes_pendentes': round(recorrentes_pendentes, 2),
        'projecao_gastos': round(projecao_gastos, 2), 'saldo_projetado': round(saldo_projetado, 2),
    })
