from flask import Blueprint, request, render_template, redirect, url_for, Response, jsonify
from datetime import datetime
import csv
import io
from app.database import db_connection
from app.utils import (
    login_required, get_current_user, get_current_user_id,
    query_lancamentos, agregar_resumo, agregar_serie_mensal,
    exportar_csv_df, common_template_context, erro_json
)

bp = Blueprint('relatorios', __name__)


@bp.route('/')
@login_required
def index():
    return redirect(url_for('relatorios.dashboard'))


@bp.route('/visao-geral')
@login_required
def visao_geral():
    return redirect(url_for('relatorios.dashboard'))


@bp.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    user_id = get_current_user_id()
    data_inicio = request.args.get('inicio')
    data_fim = request.args.get('fim')
    tipo_filtro = request.args.get('tipo')
    df = query_lancamentos(user_id, data_inicio, data_fim, tipo_filtro)
    resumo = agregar_resumo(df)
    contas_fixas = df[df['recorrente'] == True]
    parcelas_futuras = df[(df['parcelas'] > 1) & (df['parcela_atual'] > 1)]
    context = common_template_context(user, 'dashboard')
    return render_template('dashboard.html', dados=df.to_dict('records'),
                           saldo=resumo['saldo'], entrada=resumo['entrada'], saida=resumo['saida'],
                           contas_fixas=contas_fixas.to_dict('records'),
                           parcelas_futuras=parcelas_futuras.to_dict('records'),
                           filtro_tipo=tipo_filtro or 'todos',
                           data_inicio=data_inicio or '', data_fim=data_fim or '',
                           serie_mensal=agregar_serie_mensal(df), **context)


@bp.route('/lancamentos')
@login_required
def lancamentos_page():
    user = get_current_user()
    user_id = get_current_user_id()
    data_inicio = request.args.get('inicio')
    data_fim = request.args.get('fim')
    tipo_filtro = request.args.get('tipo')
    categoria = request.args.get('categoria')
    df = query_lancamentos(user_id, data_inicio, data_fim, tipo_filtro, categoria)
    resumo = agregar_resumo(df)
    contas_fixas = df[df['recorrente'] == True]
    parcelas_futuras = df[(df['parcelas'] > 1) & (df['parcela_atual'] > 1)]
    context = common_template_context(user, 'lancamentos')
    return render_template('lancamentos.html', dados=df.to_dict('records'),
                           saldo=resumo['saldo'], entrada=resumo['entrada'], saida=resumo['saida'],
                           contas_fixas=contas_fixas.to_dict('records'),
                           parcelas_futuras=parcelas_futuras.to_dict('records'),
                           filtro_tipo=tipo_filtro or 'todos',
                           data_inicio=data_inicio or '', data_fim=data_fim or '', **context)


@bp.route('/relatorios')
@login_required
def relatorios():
    user = get_current_user()
    user_id = get_current_user_id()
    data_inicio = request.args.get('inicio')
    data_fim = request.args.get('fim')
    tipo_filtro = request.args.get('tipo')
    categoria = request.args.get('categoria')
    df = query_lancamentos(user_id, data_inicio, data_fim, tipo_filtro, categoria)
    resumo = agregar_resumo(df)
    context = common_template_context(user, 'relatorios')
    return render_template('relatorios.html', dados=df.to_dict('records'),
                           saldo=resumo['saldo'], entrada=resumo['entrada'], saida=resumo['saida'],
                           data_inicio=data_inicio or '', data_fim=data_fim or '',
                           serie_mensal=agregar_serie_mensal(df), **context)


@bp.route('/relatorios/export/csv')
@login_required
def exportar_csv():
    user_id = get_current_user_id()
    inicio = request.args.get('inicio')
    fim = request.args.get('fim')
    tipo = request.args.get('tipo')
    categoria = request.args.get('categoria')
    if inicio and fim:
        try:
            d_ini = datetime.strptime(inicio, '%Y-%m-%d')
            d_fim = datetime.strptime(fim, '%Y-%m-%d')
            if d_ini > d_fim:
                return erro_json('Período inválido: data inicial maior que data final.', 400)
        except ValueError:
            return erro_json('Formato de data inválido. Use YYYY-MM-DD.', 400)
    df = query_lancamentos(user_id, inicio, fim, tipo, categoria)
    export_df = exportar_csv_df(df)
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(export_df.columns.tolist())
    for _, row in export_df.iterrows():
        writer.writerow(row.tolist())
    inicio_nome = inicio or 'inicio'
    fim_nome = fim or 'fim'
    filename = f"lancamentos_{inicio_nome}_{fim_nome}.csv"
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@bp.route('/api/relatorio/comparativo')
@login_required
def api_comparativo_mensal():
    user_id = get_current_user_id()
    meses = min(int(request.args.get('meses', 6)), 12)
    with db_connection() as conn:
        rows = conn.execute("SELECT strftime('%Y-%m', data) as mes, categoria, tipo, SUM(valor) as total FROM lancamentos WHERE user_id = ? GROUP BY mes, categoria, tipo ORDER BY mes DESC", (user_id,)).fetchall()
    dados = {}
    for r in rows:
        mes = r[0]
        if mes not in dados:
            dados[mes] = {'mes': mes, 'entrada': 0, 'saida': 0, 'categorias': {}}
        if r[2] in ('entrada', 'salario', 'recebimento'):
            dados[mes]['entrada'] += r[3]
        else:
            dados[mes]['saida'] += r[3]
        dados[mes]['categorias'][r[1] or 'Outros'] = dados[mes]['categorias'].get(r[1] or 'Outros', 0) + r[3]
    result = []
    for mes in sorted(dados.keys(), reverse=True)[:meses]:
        d = dados[mes]
        d['saldo'] = round(d['entrada'] - d['saida'], 2)
        d['entrada'] = round(d['entrada'], 2)
        d['saida'] = round(d['saida'], 2)
        d['categorias'] = {k: round(v, 2) for k, v in d['categorias'].items()}
        result.append(d)
    medias = {}
    for d in result:
        for cat, val in d['categorias'].items():
            medias.setdefault(cat, []).append(val)
    return jsonify({'meses': result, 'medias_categoria': {c: round(sum(v)/len(v), 2) for c, v in medias.items()}})
