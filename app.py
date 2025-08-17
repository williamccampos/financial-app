from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime
import pandas as pd
import os

app = Flask(__name__)
DB_PATH = 'data/lancamentos.db'

# Inicializa o banco
os.makedirs('data', exist_ok=True)
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                tipo TEXT,
                descricao TEXT,
                valor REAL,
                categoria TEXT,
                vencimento TEXT,
                recorrente INTEGER DEFAULT 0,
                parcelas INTEGER DEFAULT 1,
                parcela_atual INTEGER DEFAULT 1
            )
        ''')
init_db()

@app.route('/')
def index():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM lancamentos ORDER BY data DESC", conn, parse_dates=['data'])

    df['valor'] = df['valor'].astype(float)
    df['recorrente'] = df['recorrente'].fillna(0).astype(bool)
    df['vencimento'] = df['vencimento'].fillna('')

    if 'parcelas' not in df.columns:
        df['parcelas'] = 1
    else:
        df['parcelas'] = df['parcelas'].fillna(1).astype(int)

    if 'parcela_atual' not in df.columns:
        df['parcela_atual'] = 1
    else:
        df['parcela_atual'] = df['parcela_atual'].fillna(1).astype(int)

    # Filtros
    data_inicio = request.args.get('inicio')
    data_fim = request.args.get('fim')
    tipo_filtro = request.args.get('tipo')

    if data_inicio:
        df = df[df['data'] >= pd.to_datetime(data_inicio)]
    if data_fim:
        df = df[df['data'] <= pd.to_datetime(data_fim)]
    if tipo_filtro and tipo_filtro != 'todos':
        df = df[df['tipo'] == tipo_filtro]

    total_entrada = df[df['tipo'].isin(['entrada', 'salario', 'recebimento'])]['valor'].sum()
    total_saida = df[df['tipo'].isin(['saida', 'divida', 'conta'])]['valor'].sum()
    saldo = total_entrada - total_saida

    hoje = pd.Timestamp.today()
    contas_fixas = df[df['recorrente'] == True]
    parcelas_futuras = df[(df['parcelas'] > 1) & (df['parcela_atual'] > 1)]

    return render_template('index.html', dados=df.to_dict('records'), saldo=saldo,
                           entrada=total_entrada, saida=total_saida,
                           contas_fixas=contas_fixas.to_dict('records'),
                           parcelas_futuras=parcelas_futuras.to_dict('records'),
                           filtro_tipo=tipo_filtro or 'todos',
                           data_inicio=data_inicio or '',
                           data_fim=data_fim or '')

@app.route('/lancamento', methods=['POST'])
def lancamento():
    data = request.json
    parcelas = int(data.get('parcelas', 1))
    valor_total = float(data['valor'])
    categoria = data.get('categoria', '')
    vencimento = data.get('vencimento', '')
    recorrente = int(data.get('recorrente', False))

    with sqlite3.connect(DB_PATH) as conn:
        if categoria.lower() == 'cartão de crédito' and parcelas > 1:
            valor_parcela = round(valor_total / parcelas, 2)
            for i in range(parcelas):
                data_parcela = pd.to_datetime(data['data']) + pd.DateOffset(months=i)
                venc = pd.to_datetime(vencimento) + pd.DateOffset(months=i) if vencimento else ''
                conn.execute('''
                    INSERT INTO lancamentos
                    (data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data_parcela.strftime('%Y-%m-%d'),
                    data['tipo'],
                    data['descricao'],
                    valor_parcela,
                    categoria,
                    venc.strftime('%Y-%m-%d') if venc else '',
                    recorrente,
                    parcelas,
                    i + 1
                ))
        else:
            conn.execute('''
                INSERT INTO lancamentos
                (data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['data'], data['tipo'], data['descricao'], valor_total,
                categoria, vencimento, recorrente, parcelas, 1
            ))
    return jsonify({'status': 'ok'})

@app.route('/excluir/<int:id>', methods=['DELETE'])
def excluir(id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM lancamentos WHERE id = ?", (id,))
    return jsonify({'status': 'ok'})

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if request.method == 'GET':
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT * FROM lancamentos WHERE id = ?", (id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'erro': 'Não encontrado'}), 404
            keys = [desc[0] for desc in cur.description]
            return jsonify(dict(zip(keys, row)))
    else:
        data = request.json
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                UPDATE lancamentos
                SET data=?, tipo=?, descricao=?, valor=?, categoria=?, vencimento=?, recorrente=?, parcelas=?, parcela_atual=?
                WHERE id = ?
            ''', (
                data['data'], data['tipo'], data['descricao'], float(data['valor']),
                data.get('categoria', ''), data.get('vencimento', ''),
                int(data.get('recorrente', False)), int(data.get('parcelas', 1)), int(data.get('parcela_atual', 1)), id
            ))
        return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
