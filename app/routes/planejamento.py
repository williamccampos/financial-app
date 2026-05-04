from flask import Blueprint, request, jsonify
from app.utils import login_required

bp = Blueprint('planejamento', __name__)


@bp.route('/api/simulador/investimento', methods=['POST'])
@login_required
def simulador_investimento():
    data = request.json or {}
    aporte_inicial = float(data.get('aporte_inicial', 0))
    aporte_mensal = float(data.get('aporte_mensal', 0))
    taxa_anual = float(data.get('taxa_anual', 12)) / 100
    meses = int(data.get('meses', 12))

    taxa_mensal = (1 + taxa_anual) ** (1/12) - 1
    saldo = aporte_inicial
    evolucao = []

    for m in range(1, meses + 1):
        saldo = (saldo + aporte_mensal) * (1 + taxa_mensal)
        if m % max(1, meses // 12) == 0 or m == meses:
            evolucao.append({'mes': m, 'saldo': round(saldo, 2)})

    total_investido = aporte_inicial + (aporte_mensal * meses)
    return jsonify({
        'saldo_final': round(saldo, 2),
        'total_investido': round(total_investido, 2),
        'rendimento': round(saldo - total_investido, 2),
        'evolucao': evolucao
    })


@bp.route('/api/simulador/independencia', methods=['POST'])
@login_required
def simulador_independencia():
    data = request.json or {}
    gasto_mensal = float(data.get('gasto_mensal', 3000))
    patrimonio_atual = float(data.get('patrimonio_atual', 0))
    aporte_mensal = float(data.get('aporte_mensal', 1000))
    taxa_anual = float(data.get('taxa_anual', 8)) / 100
    taxa_retirada = float(data.get('taxa_retirada', 4)) / 100

    meta = (gasto_mensal * 12) / taxa_retirada
    taxa_mensal = (1 + taxa_anual) ** (1/12) - 1
    saldo = patrimonio_atual
    meses = 0

    while saldo < meta and meses < 600:
        saldo = (saldo + aporte_mensal) * (1 + taxa_mensal)
        meses += 1

    anos = meses // 12
    meses_rest = meses % 12
    return jsonify({
        'meta_patrimonio': round(meta, 2),
        'meses': meses,
        'anos': anos,
        'meses_restantes': meses_rest,
        'descricao': f'{anos} anos e {meses_rest} meses' if meses < 600 else 'Mais de 50 anos'
    })


@bp.route('/api/simulador/financiamento', methods=['POST'])
@login_required
def simulador_financiamento():
    data = request.json or {}
    valor_imovel = float(data.get('valor_imovel', 300000))
    entrada = float(data.get('entrada', 60000))
    taxa_anual = float(data.get('taxa_anual', 10)) / 100
    prazo_meses = int(data.get('prazo_meses', 360))

    financiado = valor_imovel - entrada
    taxa_mensal = taxa_anual / 12
    parcela = financiado * (taxa_mensal * (1 + taxa_mensal)**prazo_meses) / ((1 + taxa_mensal)**prazo_meses - 1)
    total_pago = parcela * prazo_meses
    return jsonify({
        'valor_financiado': round(financiado, 2),
        'parcela_mensal': round(parcela, 2),
        'total_pago': round(total_pago, 2),
        'juros_total': round(total_pago - financiado, 2),
        'prazo_meses': prazo_meses
    })
