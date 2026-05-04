from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response
import sqlite3
from datetime import datetime, UTC
import pandas as pd
import os
import secrets
from contextlib import contextmanager
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import time
import re
import csv
import io
import requests as http_requests

app = Flask(__name__)

# Carregar .env se existir
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())
def _get_or_create_secret():
    key = os.getenv('SECRET_KEY')
    if key:
        return key
    key_file = os.path.join('data', '.secret_key')
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    os.makedirs('data', exist_ok=True)
    with open(key_file, 'w') as f:
        f.write(key)
    return key

app.secret_key = _get_or_create_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') in ('1', 'true', 'True')
)
DB_PATH = 'data/lancamentos.db'
TIPOS_VALIDOS = {'entrada', 'saida', 'salario', 'recebimento', 'divida', 'conta'}
CATEGORIAS_PADRAO = [
    ('Moradia', '🏠'), ('Alimentação', '🍔'), ('Transporte', '🚗'),
    ('Educação', '📚'), ('Lazer', '🎮'), ('Saúde', '💊'),
    ('Cartão de Crédito', '💳'), ('Outros', '📦'),
]

# Mapa de palavras-chave para categorização automática
CATEGORIA_KEYWORDS = {
    'Alimentação': ['mercado', 'supermercado', 'ifood', 'rappi', 'restaurante', 'padaria', 'açougue', 'hortifruti', 'lanchonete', 'pizza', 'burger', 'sushi', 'café', 'coffee', 'starbucks', 'mcdonald', 'subway', 'food', 'alimenta'],
    'Transporte': ['uber', '99', 'cabify', 'gasolina', 'combustível', 'estacionamento', 'pedágio', 'ônibus', 'metrô', 'trem', 'passagem', 'avião', 'latam', 'gol', 'azul', 'posto'],
    'Moradia': ['aluguel', 'condomínio', 'iptu', 'luz', 'energia', 'água', 'gás', 'internet', 'telefone', 'celular', 'vivo', 'claro', 'tim', 'oi'],
    'Saúde': ['farmácia', 'drogaria', 'médico', 'consulta', 'exame', 'hospital', 'plano de saúde', 'unimed', 'academia', 'gym', 'smart fit'],
    'Educação': ['curso', 'escola', 'faculdade', 'universidade', 'udemy', 'alura', 'livro', 'livraria', 'mensalidade'],
    'Lazer': ['netflix', 'spotify', 'disney', 'hbo', 'amazon prime', 'youtube', 'cinema', 'teatro', 'show', 'ingresso', 'game', 'steam', 'playstation', 'xbox', 'bar', 'balada', 'viagem', 'hotel', 'airbnb', 'booking'],
    'Cartão de Crédito': ['fatura', 'cartão', 'nubank', 'inter', 'c6'],
}
UPLOAD_DIR = os.path.join('static', 'uploads', 'avatars')
LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300

# Pluggy Open Finance
PLUGGY_API_URL = 'https://api.pluggy.ai'

# Inicializa o banco
os.makedirs('data', exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
def init_db():
    with db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                nickname TEXT DEFAULT '',
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                avatar_url TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                data TEXT,
                tipo TEXT,
                descricao TEXT,
                valor REAL,
                categoria TEXT,
                vencimento TEXT,
                recorrente INTEGER DEFAULT 0,
                parcelas INTEGER DEFAULT 1,
                parcela_atual INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        cols = [row[1] for row in conn.execute("PRAGMA table_info(lancamentos)").fetchall()]
        if 'user_id' not in cols:
            conn.execute("ALTER TABLE lancamentos ADD COLUMN user_id INTEGER")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lancamentos_user_data ON lancamentos(user_id, data)")

        user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if 'nickname' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ''")
        if 'avatar_url' not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")

        # Orçamentos por categoria
        conn.execute('''
            CREATE TABLE IF NOT EXISTS orcamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                limite REAL NOT NULL,
                mes TEXT NOT NULL,
                rollover INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, categoria, mes)
            )
        ''')

        # Metas financeiras
        conn.execute('''
            CREATE TABLE IF NOT EXISTS metas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                emoji TEXT DEFAULT '🎯',
                valor_alvo REAL NOT NULL,
                valor_atual REAL DEFAULT 0,
                prazo TEXT,
                criado_em TEXT NOT NULL,
                concluida INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        conn.execute("CREATE INDEX IF NOT EXISTS idx_orcamentos_user ON orcamentos(user_id, mes)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_metas_user ON metas(user_id)")

        # Categorias customizáveis com emoji
        conn.execute('''
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                emoji TEXT DEFAULT '📁',
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, nome)
            )
        ''')

        # Multi-contas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                emoji TEXT DEFAULT '🏦',
                tipo TEXT DEFAULT 'corrente',
                saldo_inicial REAL DEFAULT 0,
                cor TEXT DEFAULT '#007aff',
                ativa INTEGER DEFAULT 1,
                criado_em TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # Adicionar conta_id em lancamentos se não existir
        lanc_cols = [row[1] for row in conn.execute("PRAGMA table_info(lancamentos)").fetchall()]
        if 'conta_id' not in lanc_cols:
            conn.execute("ALTER TABLE lancamentos ADD COLUMN conta_id INTEGER")

        # Compartilhamento familiar
        conn.execute('''
            CREATE TABLE IF NOT EXISTS compartilhamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                shared_with_id INTEGER NOT NULL,
                permissao TEXT DEFAULT 'leitura',
                criado_em TEXT NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES users(id),
                FOREIGN KEY (shared_with_id) REFERENCES users(id),
                UNIQUE(owner_id, shared_with_id)
            )
        ''')

        conn.execute("CREATE INDEX IF NOT EXISTS idx_contas_user ON contas(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_compartilhamentos ON compartilhamentos(owner_id, shared_with_id)")

        # Conexões bancárias (Pluggy)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conexoes_bancarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                connector_name TEXT DEFAULT '',
                status TEXT DEFAULT 'connected',
                conta_id INTEGER,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (conta_id) REFERENCES contas(id)
            )
        ''')


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


init_db()


def erro_json(mensagem, status=400):
    return jsonify({'status': 'erro', 'erro': mensagem}), status


def validar_email(email):
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email or ''))


def ext_permitida(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'webp'}


def get_current_user_id():
    return session.get('user_id')


def get_current_user():
    user_id = get_current_user_id()
    if not user_id:
        return None
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, name, nickname, email, avatar_url FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
    if not row:
        return None
    return {
        'id': row[0],
        'name': row[1],
        'nickname': row[2] or '',
        'email': row[3],
        'avatar_url': row[4] or ''
    }


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not get_current_user_id():
            if request.path.startswith('/lancamento') or request.path.startswith('/editar') or request.path.startswith('/excluir'):
                return jsonify({'erro': 'Não autenticado'}), 401
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapper


def login_rate_limited(email):
    now = time.time()
    attempts = LOGIN_ATTEMPTS.get(email, [])
    attempts = [a for a in attempts if now - a < LOGIN_WINDOW_SECONDS]
    LOGIN_ATTEMPTS[email] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def record_login_attempt(email):
    now = time.time()
    attempts = LOGIN_ATTEMPTS.get(email, [])
    attempts.append(now)
    LOGIN_ATTEMPTS[email] = attempts


def clear_login_attempts(email):
    LOGIN_ATTEMPTS.pop(email, None)


def get_csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


def validar_csrf():
    token_header = request.headers.get('X-CSRF-Token', '')
    token_sessao = session.get('csrf_token', '')
    return bool(token_header and token_sessao and token_header == token_sessao)


def validar_lancamento_payload(data, update=False):
    if not isinstance(data, dict):
        return 'Payload inválido.'

    obrigatorios = ['data', 'tipo', 'descricao', 'valor']
    if not update:
        for campo in obrigatorios:
            if campo not in data:
                return f'Campo obrigatório ausente: {campo}'

    if 'tipo' in data:
        tipo = str(data.get('tipo', '')).strip().lower()
        if tipo not in TIPOS_VALIDOS:
            return 'Tipo inválido.'

    if 'descricao' in data:
        descricao = str(data.get('descricao', '')).strip()
        if not descricao:
            return 'Descrição é obrigatória.'

    if 'valor' in data:
        try:
            valor = float(data.get('valor'))
            if valor <= 0:
                return 'Valor deve ser maior que zero.'
        except (TypeError, ValueError):
            return 'Valor inválido.'

    if 'data' in data:
        try:
            datetime.strptime(str(data.get('data')), '%Y-%m-%d')
        except (TypeError, ValueError):
            return 'Data inválida. Use o formato YYYY-MM-DD.'

    vencimento = data.get('vencimento')
    if vencimento:
        try:
            datetime.strptime(str(vencimento), '%Y-%m-%d')
        except (TypeError, ValueError):
            return 'Vencimento inválido. Use o formato YYYY-MM-DD.'

    if 'parcelas' in data:
        try:
            parcelas = int(data.get('parcelas', 1))
            if parcelas < 1 or parcelas > 120:
                return 'Parcelas deve estar entre 1 e 120.'
        except (TypeError, ValueError):
            return 'Parcelas inválidas.'

    return None


def query_lancamentos(user_id, inicio=None, fim=None, tipo=None, categoria=None):
    clauses = ["user_id = ?"]
    params = [user_id]
    if inicio:
        clauses.append("data >= ?")
        params.append(inicio)
    if fim:
        clauses.append("data <= ?")
        params.append(fim)
    if tipo and tipo != 'todos':
        clauses.append("tipo = ?")
        params.append(tipo)
    if categoria:
        clauses.append("categoria = ?")
        params.append(categoria)
    where = " AND ".join(clauses)

    with db_connection() as conn:
        df = pd.read_sql_query(
            f"SELECT * FROM lancamentos WHERE {where} ORDER BY data DESC",
            conn, params=params, parse_dates=['data']
        )

    if df.empty:
        df = pd.DataFrame(columns=['id', 'user_id', 'data', 'tipo', 'descricao', 'valor', 'categoria', 'vencimento', 'recorrente', 'parcelas', 'parcela_atual'])

    if 'valor' in df.columns:
        df['valor'] = pd.to_numeric(df['valor'], errors='coerce').fillna(0.0)
    if 'recorrente' in df.columns:
        df['recorrente'] = df['recorrente'].fillna(0).astype(bool)
    if 'vencimento' in df.columns:
        df['vencimento'] = df['vencimento'].fillna('')
    if 'parcelas' not in df.columns:
        df['parcelas'] = 1
    else:
        df['parcelas'] = pd.to_numeric(df['parcelas'], errors='coerce').fillna(1).astype(int)
    if 'parcela_atual' not in df.columns:
        df['parcela_atual'] = 1
    else:
        df['parcela_atual'] = pd.to_numeric(df['parcela_atual'], errors='coerce').fillna(1).astype(int)
    return df


def query_lancamentos_paginado(user_id, page=1, per_page=15, inicio=None, fim=None, tipo=None, categoria=None, busca=None, sort='data', order='desc'):
    clauses = ["user_id = ?"]
    params = [user_id]
    if inicio:
        clauses.append("data >= ?"); params.append(inicio)
    if fim:
        clauses.append("data <= ?"); params.append(fim)
    if tipo and tipo != 'todos':
        clauses.append("tipo = ?"); params.append(tipo)
    if categoria:
        clauses.append("categoria = ?"); params.append(categoria)
    if busca:
        clauses.append("(descricao LIKE ? OR categoria LIKE ?)")
        params.extend([f"%{busca}%", f"%{busca}%"])
    where = " AND ".join(clauses)
    sort_col = sort if sort in ('data', 'tipo', 'descricao', 'valor', 'categoria') else 'data'
    sort_dir = 'ASC' if order == 'asc' else 'DESC'

    with db_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM lancamentos WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual FROM lancamentos WHERE {where} ORDER BY {sort_col} {sort_dir} LIMIT ? OFFSET ?",
            params + [per_page, (page - 1) * per_page]
        ).fetchall()

    items = []
    for r in rows:
        items.append({
            'id': r[0], 'data': r[1], 'tipo': r[2], 'descricao': r[3],
            'valor': float(r[4] or 0), 'categoria': r[5] or '', 'vencimento': r[6] or '',
            'recorrente': bool(r[7]), 'parcelas': int(r[8] or 1), 'parcela_atual': int(r[9] or 1)
        })
    return {'items': items, 'total': total, 'page': page, 'per_page': per_page, 'pages': max(1, -(-total // per_page))}


def agregar_resumo(df):
    total_entrada = df[df['tipo'].isin(['entrada', 'salario', 'recebimento'])]['valor'].sum() if not df.empty else 0
    total_saida = df[df['tipo'].isin(['saida', 'divida', 'conta'])]['valor'].sum() if not df.empty else 0
    return {
        'entrada': float(total_entrada),
        'saida': float(total_saida),
        'saldo': float(total_entrada - total_saida)
    }


def agregar_serie_mensal(df):
    if df.empty:
        return []
    aux = df.copy()
    aux['mes'] = aux['data'].dt.to_period('M').astype(str)
    grouped = aux.groupby(['mes', 'tipo'])['valor'].sum().reset_index()
    series = {}
    for _, row in grouped.iterrows():
        mes = row['mes']
        tipo = row['tipo']
        val = float(row['valor'])
        if mes not in series:
            series[mes] = {'mes': mes, 'entrada': 0.0, 'saida': 0.0}
        if tipo in ['entrada', 'salario', 'recebimento']:
            series[mes]['entrada'] += val
        elif tipo in ['saida', 'divida', 'conta']:
            series[mes]['saida'] += val
    output = []
    acumulado = 0.0
    for mes in sorted(series.keys()):
        ent = series[mes]['entrada']
        sai = series[mes]['saida']
        saldo = ent - sai
        acumulado += saldo
        output.append({'mes': mes, 'entrada': ent, 'saida': sai, 'saldo': saldo, 'acumulado': acumulado})
    return output


def exportar_csv_df(df):
    export_df = df.copy()
    if export_df.empty:
        export_df = pd.DataFrame(columns=['id', 'data', 'tipo', 'descricao', 'valor', 'categoria', 'vencimento', 'recorrente', 'parcelas', 'parcela_atual'])
    if 'data' in export_df.columns:
        export_df['data'] = pd.to_datetime(export_df['data'], errors='coerce')
        export_df['mes_ano'] = export_df['data'].dt.strftime('%Y-%m').fillna('')
        export_df['data'] = export_df['data'].dt.strftime('%Y-%m-%d').fillna('')
    else:
        export_df['mes_ano'] = ''
    export_df['sinal_financeiro'] = export_df['tipo'].apply(lambda t: 'entrada' if t in ['entrada', 'salario', 'recebimento'] else 'saida') if 'tipo' in export_df.columns else ''
    export_df['valor_absoluto'] = export_df['valor'].abs() if 'valor' in export_df.columns else 0
    cols = ['id', 'data', 'tipo', 'descricao', 'valor', 'categoria', 'vencimento', 'recorrente', 'parcelas', 'parcela_atual', 'mes_ano', 'sinal_financeiro', 'valor_absoluto']
    for c in cols:
        if c not in export_df.columns:
            export_df[c] = ''
    return export_df[cols]


def common_template_context(user, active_tab):
    user_id = get_current_user_id()
    mes_atual = datetime.now().strftime('%Y-%m')

    # Orçamentos do mês
    orcamentos = []
    if user_id:
        with db_connection() as conn:
            rows = conn.execute(
                "SELECT id, categoria, limite, rollover FROM orcamentos WHERE user_id = ? AND mes = ?",
                (user_id, mes_atual)
            ).fetchall()
            for r in rows:
                gasto = conn.execute(
                    "SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND categoria = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')",
                    (user_id, r[1], mes_atual)
                ).fetchone()[0]
                pct = round((gasto / r[2]) * 100, 1) if r[2] > 0 else 0
                orcamentos.append({'id': r[0], 'categoria': r[1], 'limite': r[2], 'gasto': float(gasto), 'percentual': pct, 'rollover': r[3]})

    # Metas ativas
    metas = []
    if user_id:
        with db_connection() as conn:
            rows = conn.execute(
                "SELECT id, nome, emoji, valor_alvo, valor_atual, prazo, concluida FROM metas WHERE user_id = ? AND concluida = 0 ORDER BY prazo",
                (user_id,)
            ).fetchall()
            for r in rows:
                pct = round((r[4] / r[3]) * 100, 1) if r[3] > 0 else 0
                metas.append({'id': r[0], 'nome': r[1], 'emoji': r[2], 'valor_alvo': r[3], 'valor_atual': r[4], 'prazo': r[5], 'percentual': pct})

    # Alertas de vencimento (próximos 7 dias)
    alertas = []
    if user_id:
        hoje = datetime.now().strftime('%Y-%m-%d')
        limite = (datetime.now() + pd.Timedelta(days=7)).strftime('%Y-%m-%d')
        with db_connection() as conn:
            rows = conn.execute(
                "SELECT descricao, valor, vencimento, categoria FROM lancamentos WHERE user_id = ? AND vencimento BETWEEN ? AND ? AND tipo IN ('divida','conta') ORDER BY vencimento",
                (user_id, hoje, limite)
            ).fetchall()
            for r in rows:
                alertas.append({'descricao': r[0], 'valor': r[1], 'vencimento': r[2], 'categoria': r[3]})

    ctx = {
        'csrf_token': get_csrf_token(),
        'user_name': session.get('user_name', 'Usuário'),
        'user_nickname': (user or {}).get('nickname', ''),
        'user_email': (user or {}).get('email', ''),
        'user_avatar': (user or {}).get('avatar_url', ''),
        'active_tab': active_tab,
        'orcamentos': orcamentos,
        'metas': metas,
        'alertas_vencimento': alertas,
        'mes_atual': mes_atual,
    }

    # Categorias com emoji
    with db_connection() as conn:
        cat_rows = conn.execute("SELECT nome, emoji FROM categorias WHERE user_id = ?", (user_id,)).fetchall()
    if cat_rows:
        ctx['categorias_emoji'] = {r[0]: r[1] for r in cat_rows}
    else:
        ctx['categorias_emoji'] = {c[0]: c[1] for c in CATEGORIAS_PADRAO}

    # Assinaturas detectadas
    with db_connection() as conn:
        sub_rows = conn.execute(
            "SELECT descricao, AVG(valor) as media FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','conta') GROUP BY descricao ORDER BY media DESC LIMIT 10",
            (user_id,)
        ).fetchall()
    ctx['assinaturas'] = [{'descricao': r[0], 'valor': round(r[1], 2)} for r in sub_rows]
    ctx['assinaturas_total'] = round(sum(r[1] for r in sub_rows), 2)

    return ctx

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))


@app.route('/visao-geral')
@login_required
def visao_geral():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
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
                           data_inicio=data_inicio or '',
                           data_fim=data_fim or '',
                           serie_mensal=agregar_serie_mensal(df),
                           **context)


@app.route('/lancamentos')
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
                           data_inicio=data_inicio or '',
                           data_fim=data_fim or '',
                           **context)


@app.route('/relatorios')
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
                           serie_mensal=agregar_serie_mensal(df),
                           **context)


@app.route('/relatorios/export/csv')
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
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if get_current_user_id():
            return redirect(url_for('index'))
        return render_template('login.html')

    data = request.form or request.json or {}
    email = str(data.get('email', '')).strip().lower()
    senha = str(data.get('password', ''))

    if not validar_email(email) or not senha:
        return render_template('login.html', erro='Informe email e senha válidos.'), 400

    if login_rate_limited(email):
        return render_template('login.html', erro='Muitas tentativas. Aguarde alguns minutos.'), 429

    with db_connection() as conn:
        user = conn.execute(
            "SELECT id, name, nickname, email, password_hash, avatar_url FROM users WHERE email = ?",
            (email,)
        ).fetchone()

    if not user or not check_password_hash(user[4], senha):
        record_login_attempt(email)
        return render_template('login.html', erro='Credenciais inválidas.'), 401

    clear_login_attempts(email)
    session['user_id'] = user[0]
    session['user_name'] = user[1]
    session['user_nickname'] = user[2] or ''
    session['user_avatar'] = user[5] or ''
    get_csrf_token()
    return render_template('login.html', sucesso='Login realizado. Redirecionando...', redirect_to=url_for('index'))


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'GET':
        return render_template('register.html')

    data = request.form or request.json or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    password_confirm = str(data.get('password_confirm', ''))

    if len(name) < 2:
        return render_template('register.html', erro='Nome deve ter ao menos 2 caracteres.'), 400
    if not validar_email(email):
        return render_template('register.html', erro='Email inválido.'), 400
    if len(password) < 8:
        return render_template('register.html', erro='Senha deve ter ao menos 8 caracteres.'), 400
    if password != password_confirm:
        return render_template('register.html', erro='As senhas não conferem.'), 400

    with db_connection() as conn:
        exists = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            return render_template('register.html', erro='Já existe um usuário com esse email.'), 409

        conn.execute(
            "INSERT INTO users (name, nickname, email, password_hash, avatar_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, '', email, generate_password_hash(password), '', datetime.now(UTC).isoformat())
        )

    return render_template('register.html', sucesso='Cadastro realizado com sucesso. Faça login.', redirect_to=url_for('login'))


@app.route('/logout', methods=['POST'])
def logout():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    session.clear()
    return jsonify({'status': 'ok'})


@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    if request.method == 'GET':
        user = get_current_user()
        if not user:
            return erro_json('Usuário não encontrado.', 404)
        return jsonify(user)

    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    user_id = get_current_user_id()
    data = request.form if request.form else (request.json or {})
    name = str(data.get('name', '')).strip()
    nickname = str(data.get('nickname', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    avatar_url = None

    if len(name) < 2:
        return erro_json('Nome deve ter ao menos 2 caracteres.', 400)
    if not validar_email(email):
        return erro_json('Email inválido.', 400)
    if password and len(password) < 8:
        return erro_json('Senha deve ter ao menos 8 caracteres.', 400)

    avatar_file = request.files.get('avatar')
    if avatar_file and avatar_file.filename:
        if not ext_permitida(avatar_file.filename):
            return erro_json('Formato de imagem inválido. Use PNG, JPG, JPEG ou WEBP.', 400)
        extensao = avatar_file.filename.rsplit('.', 1)[1].lower()
        nome_arquivo = f"user_{user_id}_{int(time.time())}.{extensao}"
        caminho_relativo = os.path.join('uploads', 'avatars', nome_arquivo)
        caminho_completo = os.path.join('static', caminho_relativo)
        avatar_file.save(caminho_completo)
        avatar_url = f"/static/{caminho_relativo}"

    with db_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if existing:
            return erro_json('Este email já está em uso.', 409)

        if password:
            if avatar_url is not None:
                conn.execute(
                    "UPDATE users SET name = ?, nickname = ?, email = ?, password_hash = ?, avatar_url = ? WHERE id = ?",
                    (name, nickname, email, generate_password_hash(password), avatar_url, user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, nickname = ?, email = ?, password_hash = ? WHERE id = ?",
                    (name, nickname, email, generate_password_hash(password), user_id)
                )
        else:
            if avatar_url is not None:
                conn.execute(
                    "UPDATE users SET name = ?, nickname = ?, email = ?, avatar_url = ? WHERE id = ?",
                    (name, nickname, email, avatar_url, user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, nickname = ?, email = ? WHERE id = ?",
                    (name, nickname, email, user_id)
                )

    session['user_name'] = name
    session['user_nickname'] = nickname
    if avatar_url is not None:
        session['user_avatar'] = avatar_url

    return jsonify({'status': 'ok', 'avatar_url': avatar_url or session.get('user_avatar', '')})

@app.route('/lancamento', methods=['POST'])
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
                conn.execute('''
                    INSERT INTO lancamentos
                    (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    data_parcela.strftime('%Y-%m-%d'),
                    data['tipo'],
                    data['descricao'],
                    vp,
                    categoria,
                    venc.strftime('%Y-%m-%d') if venc else '',
                    recorrente,
                    parcelas,
                    i + 1
                ))
        else:
            conn.execute('''
                INSERT INTO lancamentos
                (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                data['data'], data['tipo'], data['descricao'], valor_total,
                categoria, vencimento, recorrente, parcelas, 1
            ))
    return jsonify({'status': 'ok'})

@app.route('/excluir/<int:id>', methods=['DELETE'])
@login_required
def excluir(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)

    with db_connection() as conn:
        cur = conn.execute("DELETE FROM lancamentos WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Lançamento não encontrado.', 404)
    return jsonify({'status': 'ok'})

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
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
    else:
        if not validar_csrf():
            return erro_json('CSRF inválido.', 403)

        data = request.json or {}
        erro = validar_lancamento_payload(data, update=True)
        if erro:
            return erro_json(erro, 400)

        with db_connection() as conn:
            cur = conn.execute('''
                UPDATE lancamentos
                SET data=?, tipo=?, descricao=?, valor=?, categoria=?, vencimento=?, recorrente=?, parcelas=?, parcela_atual=?
                WHERE id = ? AND user_id = ?
            ''', (
                data['data'], data['tipo'], data['descricao'], float(data['valor']),
                data.get('categoria', ''), data.get('vencimento', ''),
                int(data.get('recorrente', False)), int(data.get('parcelas', 1)), int(data.get('parcela_atual', 1)), id, get_current_user_id()
            ))
            if cur.rowcount == 0:
                return erro_json('Lançamento não encontrado.', 404)
        return jsonify({'status': 'ok'})


# ── API paginada de lançamentos ──

@app.route('/api/lancamentos')
@login_required
def api_lancamentos():
    user_id = get_current_user_id()
    page = int(request.args.get('page', 1))
    per_page = min(int(request.args.get('per_page', 15)), 100)
    result = query_lancamentos_paginado(
        user_id, page=page, per_page=per_page,
        inicio=request.args.get('inicio'),
        fim=request.args.get('fim'),
        tipo=request.args.get('tipo'),
        categoria=request.args.get('categoria'),
        busca=request.args.get('busca'),
        sort=request.args.get('sort', 'data'),
        order=request.args.get('order', 'desc')
    )
    return jsonify(result)


# ── Spending line (gasto acumulado dia a dia no mês) ──

@app.route('/api/spending-line')
@login_required
def api_spending_line():
    user_id = get_current_user_id()
    mes = request.args.get('mes') or datetime.now().strftime('%Y-%m')
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT data, tipo, SUM(valor) as total FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? GROUP BY data, tipo ORDER BY data",
            (user_id, mes)
        ).fetchall()

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

    acum_gasto = 0
    acum_entrada = 0
    points = []
    for d in sorted(daily.keys()):
        acum_gasto += daily[d]['saida']
        acum_entrada += daily[d]['entrada']
        points.append({'data': d, 'gasto_acumulado': round(acum_gasto, 2), 'entrada_acumulada': round(acum_entrada, 2)})

    # Orçamento total do mês
    orc_total = 0
    with db_connection() as conn:
        row = conn.execute("SELECT COALESCE(SUM(limite), 0) FROM orcamentos WHERE user_id = ? AND mes = ?", (user_id, mes)).fetchone()
        orc_total = row[0] if row else 0

    return jsonify({'mes': mes, 'pontos': points, 'orcamento_total': round(orc_total, 2)})


# ── Detecção de assinaturas ──

@app.route('/api/assinaturas')
@login_required
def api_assinaturas():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT descricao, tipo, categoria, AVG(valor) as media, COUNT(*) as vezes, MAX(data) as ultima FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','conta') GROUP BY descricao, tipo ORDER BY media DESC",
            (user_id,)
        ).fetchall()
    subs = []
    total = 0
    for r in rows:
        val = round(r[3], 2)
        total += val
        subs.append({'descricao': r[0], 'tipo': r[1], 'categoria': r[2] or '', 'valor_medio': val, 'vezes': r[4], 'ultima': r[5]})
    return jsonify({'assinaturas': subs, 'total_mensal': round(total, 2)})


# ── Orçamentos ──

@app.route('/orcamento', methods=['POST'])
@login_required
def criar_orcamento():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    categoria = str(data.get('categoria', '')).strip()
    limite = data.get('limite')
    mes = str(data.get('mes', '')).strip()
    if not categoria or not mes:
        return erro_json('Categoria e mês são obrigatórios.', 400)
    try:
        limite = float(limite)
        if limite <= 0:
            return erro_json('Limite deve ser maior que zero.', 400)
    except (TypeError, ValueError):
        return erro_json('Limite inválido.', 400)

    user_id = get_current_user_id()
    with db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO orcamentos (user_id, categoria, limite, mes) VALUES (?, ?, ?, ?)",
            (user_id, categoria, limite, mes)
        )
    return jsonify({'status': 'ok'})


@app.route('/orcamento/<int:id>', methods=['DELETE'])
@login_required
def excluir_orcamento(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM orcamentos WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Orçamento não encontrado.', 404)
    return jsonify({'status': 'ok'})


# ── Metas ──

@app.route('/meta', methods=['POST'])
@login_required
def criar_meta():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    nome = str(data.get('nome', '')).strip()
    emoji = str(data.get('emoji', '🎯')).strip() or '🎯'
    prazo = str(data.get('prazo', '')).strip()
    try:
        valor_alvo = float(data.get('valor_alvo', 0))
        if valor_alvo <= 0:
            return erro_json('Valor alvo deve ser maior que zero.', 400)
    except (TypeError, ValueError):
        return erro_json('Valor alvo inválido.', 400)
    if not nome:
        return erro_json('Nome da meta é obrigatório.', 400)

    user_id = get_current_user_id()
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO metas (user_id, nome, emoji, valor_alvo, valor_atual, prazo, criado_em) VALUES (?, ?, ?, ?, 0, ?, ?)",
            (user_id, nome, emoji, valor_alvo, prazo, datetime.now(UTC).isoformat())
        )
    return jsonify({'status': 'ok'})


@app.route('/meta/<int:id>', methods=['POST'])
@login_required
def atualizar_meta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    user_id = get_current_user_id()

    with db_connection() as conn:
        existing = conn.execute("SELECT id FROM metas WHERE id = ? AND user_id = ?", (id, user_id)).fetchone()
        if not existing:
            return erro_json('Meta não encontrada.', 404)

        if 'valor_deposito' in data:
            try:
                deposito = float(data['valor_deposito'])
                if deposito <= 0:
                    return erro_json('Valor deve ser maior que zero.', 400)
            except (TypeError, ValueError):
                return erro_json('Valor inválido.', 400)
            conn.execute("UPDATE metas SET valor_atual = valor_atual + ? WHERE id = ?", (deposito, id))
            meta = conn.execute("SELECT valor_atual, valor_alvo FROM metas WHERE id = ?", (id,)).fetchone()
            if meta and meta[0] >= meta[1]:
                conn.execute("UPDATE metas SET concluida = 1 WHERE id = ?", (id,))
        elif 'concluida' in data:
            conn.execute("UPDATE metas SET concluida = ? WHERE id = ?", (int(data['concluida']), id))

    return jsonify({'status': 'ok'})


@app.route('/meta/<int:id>', methods=['DELETE'])
@login_required
def excluir_meta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        cur = conn.execute("DELETE FROM metas WHERE id = ? AND user_id = ?", (id, get_current_user_id()))
        if cur.rowcount == 0:
            return erro_json('Meta não encontrada.', 404)
    return jsonify({'status': 'ok'})


# ── Recorrência automática ──

@app.route('/gerar-recorrentes', methods=['POST'])
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
            (user_id,)
        ).fetchall()

        for r in recorrentes:
            existe = conn.execute(
                "SELECT id FROM lancamentos WHERE user_id = ? AND descricao = ? AND tipo = ? AND strftime('%Y-%m', data) = ?",
                (user_id, r[0], r[1], mes_atual)
            ).fetchone()
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
                    "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, 1)",
                    (user_id, f"{mes_atual}-01", r[1], r[0], r[2], r[3], dia_venc)
                )
                count += 1

    return jsonify({'status': 'ok', 'gerados': count})



# ── Inteligência (Fase 4) ──

@app.route('/api/sugerir-categoria')
@login_required
def sugerir_categoria():
    """Sugere categoria baseado na descrição: primeiro busca no histórico do usuário, depois no mapa de keywords."""
    descricao = str(request.args.get('descricao', '')).strip().lower()
    if not descricao:
        return jsonify({'categoria': '', 'confianca': 0})

    user_id = get_current_user_id()

    # 1. Buscar no histórico do usuário (maior confiança)
    with db_connection() as conn:
        row = conn.execute(
            "SELECT categoria, COUNT(*) as freq FROM lancamentos WHERE user_id = ? AND LOWER(descricao) LIKE ? AND categoria != '' GROUP BY categoria ORDER BY freq DESC LIMIT 1",
            (user_id, f'%{descricao}%')
        ).fetchone()
    if row and row[0]:
        return jsonify({'categoria': row[0], 'confianca': 0.95, 'fonte': 'historico'})

    # 2. Buscar por keywords
    for cat, keywords in CATEGORIA_KEYWORDS.items():
        for kw in keywords:
            if kw in descricao:
                return jsonify({'categoria': cat, 'confianca': 0.75, 'fonte': 'keywords'})

    return jsonify({'categoria': '', 'confianca': 0})


@app.route('/api/insights')
@login_required
def api_insights():
    """Gera insights automáticos comparando mês atual com média dos últimos 3 meses."""
    user_id = get_current_user_id()
    mes_atual = datetime.now().strftime('%Y-%m')
    insights = []

    with db_connection() as conn:
        # Gastos por categoria no mês atual
        atual = conn.execute(
            "SELECT categoria, SUM(valor) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta') AND categoria != '' GROUP BY categoria",
            (user_id, mes_atual)
        ).fetchall()

        # Média dos últimos 3 meses (excluindo atual)
        medias = conn.execute(
            "SELECT categoria, AVG(total) FROM (SELECT categoria, strftime('%Y-%m', data) as mes, SUM(valor) as total FROM lancamentos WHERE user_id = ? AND tipo IN ('saida','divida','conta') AND categoria != '' AND strftime('%Y-%m', data) < ? GROUP BY categoria, mes) GROUP BY categoria",
            (user_id, mes_atual)
        ).fetchall()

    media_map = {r[0]: r[1] for r in medias}

    for cat, gasto in atual:
        media = media_map.get(cat)
        if not media or media == 0:
            continue
        variacao = round(((gasto - media) / media) * 100, 1)
        if variacao > 20:
            insights.append({
                'tipo': 'alerta',
                'icone': '📈',
                'mensagem': f'Você gastou {variacao}% a mais em {cat} este mês (R$ {gasto:.0f}) comparado à média (R$ {media:.0f}).'
            })
        elif variacao < -20:
            insights.append({
                'tipo': 'positivo',
                'icone': '📉',
                'mensagem': f'Parabéns! Você economizou {abs(variacao)}% em {cat} este mês (R$ {gasto:.0f} vs média R$ {media:.0f}).'
            })

    # Insight de saldo
    with db_connection() as conn:
        entradas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('entrada','salario','recebimento')", (user_id, mes_atual)).fetchone()[0]
        saidas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')", (user_id, mes_atual)).fetchone()[0]

    saldo = entradas - saidas
    if saldo > 0:
        taxa_poupanca = round((saldo / entradas) * 100, 1) if entradas > 0 else 0
        insights.append({'tipo': 'positivo', 'icone': '💰', 'mensagem': f'Você está poupando {taxa_poupanca}% da sua renda este mês (R$ {saldo:.0f}).'})
    elif saldo < 0:
        insights.append({'tipo': 'alerta', 'icone': '⚠️', 'mensagem': f'Atenção: seus gastos superaram sua renda em R$ {abs(saldo):.0f} este mês.'})

    # Maior gasto
    if atual:
        maior = max(atual, key=lambda x: x[1])
        insights.append({'tipo': 'info', 'icone': '🏷️', 'mensagem': f'Sua maior categoria de gasto é {maior[0]} com R$ {maior[1]:.0f} este mês.'})

    return jsonify({'insights': insights, 'mes': mes_atual})


@app.route('/api/projecao')
@login_required
def api_projecao():
    """Projeta saldo no fim do mês baseado em gastos até agora + recorrentes pendentes."""
    user_id = get_current_user_id()
    hoje = datetime.now()
    mes_atual = hoje.strftime('%Y-%m')
    dia_atual = hoje.day
    import calendar
    dias_no_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    dias_restantes = dias_no_mes - dia_atual

    with db_connection() as conn:
        # Entradas do mês
        entradas = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('entrada','salario','recebimento')", (user_id, mes_atual)).fetchone()[0]
        # Saídas até agora
        saidas_ate_agora = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')", (user_id, mes_atual)).fetchone()[0]
        # Recorrentes que ainda não foram lançados este mês
        recorrentes_pendentes = conn.execute(
            "SELECT COALESCE(SUM(sub.valor),0) FROM (SELECT descricao, tipo, MAX(valor) as valor FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','divida','conta') GROUP BY descricao, tipo) sub WHERE sub.descricao NOT IN (SELECT descricao FROM lancamentos WHERE user_id = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta'))",
            (user_id, user_id, mes_atual)
        ).fetchone()[0]

    # Projeção: gasto diário médio * dias restantes
    gasto_diario = saidas_ate_agora / dia_atual if dia_atual > 0 else 0
    projecao_gastos = saidas_ate_agora + (gasto_diario * dias_restantes) + recorrentes_pendentes
    saldo_projetado = entradas - projecao_gastos

    return jsonify({
        'mes': mes_atual,
        'dia_atual': dia_atual,
        'dias_restantes': dias_restantes,
        'entradas': round(entradas, 2),
        'saidas_ate_agora': round(saidas_ate_agora, 2),
        'gasto_diario_medio': round(gasto_diario, 2),
        'recorrentes_pendentes': round(recorrentes_pendentes, 2),
        'projecao_gastos': round(projecao_gastos, 2),
        'saldo_projetado': round(saldo_projetado, 2),
    })


# ── Categorias customizáveis ──

@app.route('/api/categorias')
@login_required
def api_categorias():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute("SELECT nome, emoji FROM categorias WHERE user_id = ? ORDER BY nome", (user_id,)).fetchall()
    if rows:
        return jsonify([{'nome': r[0], 'emoji': r[1]} for r in rows])
    return jsonify([{'nome': c[0], 'emoji': c[1]} for c in CATEGORIAS_PADRAO])


@app.route('/api/categorias', methods=['POST'])
@login_required
def salvar_categoria():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    nome = str(data.get('nome', '')).strip()
    emoji = str(data.get('emoji', '📁')).strip() or '📁'
    if not nome:
        return erro_json('Nome é obrigatório.', 400)
    with db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO categorias (user_id, nome, emoji) VALUES (?, ?, ?)", (get_current_user_id(), nome, emoji))
    return jsonify({'status': 'ok'})


# ── Rollover de orçamento ──

@app.route('/api/rollover')
@login_required
def api_rollover():
    user_id = get_current_user_id()
    hoje = datetime.now()
    mes_atual = hoje.strftime('%Y-%m')
    mes_anterior = f"{hoje.year - 1}-12" if hoje.month == 1 else f"{hoje.year}-{hoje.month - 1:02d}"
    rollovers = []
    with db_connection() as conn:
        for cat, limite in conn.execute("SELECT categoria, limite FROM orcamentos WHERE user_id = ? AND mes = ?", (user_id, mes_anterior)).fetchall():
            gasto = conn.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND categoria = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')", (user_id, cat, mes_anterior)).fetchone()[0]
            sobra = round(limite - gasto, 2)
            if sobra > 0:
                rollovers.append({'categoria': cat, 'sobra': sobra})
    return jsonify({'rollovers': rollovers, 'mes_anterior': mes_anterior, 'mes_atual': mes_atual})


# ── Multi-contas ──

@app.route('/api/contas')
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


@app.route('/api/contas', methods=['POST'])
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
        conn.execute("INSERT INTO contas (user_id, nome, emoji, tipo, saldo_inicial, cor, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (get_current_user_id(), nome, str(data.get('emoji', '🏦')).strip() or '🏦', str(data.get('tipo', 'corrente')).strip(), saldo_inicial, str(data.get('cor', '#007aff')).strip(), datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok'})


@app.route('/api/contas/<int:id>', methods=['DELETE'])
@login_required
def excluir_conta(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM contas WHERE id = ? AND user_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Conta não encontrada.', 404)
    return jsonify({'status': 'ok'})


# ── Patrimônio líquido ──

@app.route('/api/patrimonio')
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
    # Evolução últimos 6 meses
    evolucao = []
    with db_connection() as conn:
        rows = conn.execute("SELECT strftime('%Y-%m', data) as mes, COALESCE(SUM(CASE WHEN tipo IN ('entrada','salario','recebimento') THEN valor ELSE -valor END), 0) FROM lancamentos WHERE user_id = ? GROUP BY mes ORDER BY mes DESC LIMIT 6", (user_id,)).fetchall()
    acum = 0
    for r in sorted(rows, key=lambda x: x[0]):
        acum += r[1]
        evolucao.append({'mes': r[0], 'patrimonio': round(acum, 2)})
    return jsonify({'contas': items, 'total': round(total, 2), 'evolucao': evolucao})


# ── Relatórios avançados ──

@app.route('/api/relatorio/comparativo')
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


# ── Compartilhamento familiar ──

@app.route('/api/compartilhar', methods=['POST'])
@login_required
def compartilhar():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    email = str(data.get('email', '')).strip().lower()
    permissao = str(data.get('permissao', 'leitura')).strip()
    if permissao not in ('leitura', 'escrita'):
        return erro_json('Permissão inválida.', 400)
    if not validar_email(email):
        return erro_json('Email inválido.', 400)
    user_id = get_current_user_id()
    with db_connection() as conn:
        target = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not target:
            return erro_json('Usuário não encontrado.', 404)
        if target[0] == user_id:
            return erro_json('Não é possível compartilhar consigo mesmo.', 400)
        conn.execute("INSERT OR REPLACE INTO compartilhamentos (owner_id, shared_with_id, permissao, criado_em) VALUES (?, ?, ?, ?)",
            (user_id, target[0], permissao, datetime.now(UTC).isoformat()))
    return jsonify({'status': 'ok'})


@app.route('/api/compartilhamentos')
@login_required
def api_compartilhamentos():
    user_id = get_current_user_id()
    with db_connection() as conn:
        shared = conn.execute("SELECT u.name, u.email, c.permissao, c.id FROM compartilhamentos c JOIN users u ON u.id = c.shared_with_id WHERE c.owner_id = ?", (user_id,)).fetchall()
        received = conn.execute("SELECT u.name, u.email, c.permissao FROM compartilhamentos c JOIN users u ON u.id = c.owner_id WHERE c.shared_with_id = ?", (user_id,)).fetchall()
    return jsonify({
        'compartilhados': [{'nome': r[0], 'email': r[1], 'permissao': r[2], 'id': r[3]} for r in shared],
        'recebidos': [{'nome': r[0], 'email': r[1], 'permissao': r[2]} for r in received]
    })


@app.route('/api/compartilhar/<int:id>', methods=['DELETE'])
@login_required
def remover_compartilhamento(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM compartilhamentos WHERE id = ? AND owner_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Compartilhamento não encontrado.', 404)
    return jsonify({'status': 'ok'})


# ── Importação CSV bancário ──

@app.route('/importar/csv', methods=['POST'])
@login_required
def importar_csv():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    file = request.files.get('arquivo')
    if not file or not file.filename:
        return erro_json('Arquivo é obrigatório.', 400)
    if not file.filename.lower().endswith('.csv'):
        return erro_json('Apenas arquivos CSV são aceitos.', 400)
    conta_id = request.form.get('conta_id') or None
    user_id = get_current_user_id()
    try:
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        with db_connection() as conn:
            for row in reader:
                data_val = (row.get('data') or row.get('Data') or row.get('date') or '').strip()
                descricao = (row.get('descricao') or row.get('Descrição') or row.get('description') or row.get('Descricao') or '').strip()
                valor_str = (row.get('valor') or row.get('Valor') or row.get('amount') or '0').strip()
                valor_str = valor_str.replace('.', '').replace(',', '.') if ',' in valor_str else valor_str
                try:
                    valor = abs(float(valor_str))
                except (ValueError, TypeError):
                    continue
                if not data_val or not descricao or valor <= 0:
                    continue
                raw = (row.get('valor') or row.get('Valor') or row.get('amount') or '0').strip()
                tipo = 'saida' if raw.startswith('-') else 'entrada'
                categoria = (row.get('categoria') or row.get('Categoria') or row.get('category') or '').strip()
                conn.execute("INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual, conta_id) VALUES (?, ?, ?, ?, ?, ?, '', 0, 1, 1, ?)",
                    (user_id, data_val, tipo, descricao, valor, categoria, conta_id))
                count += 1
    except Exception as e:
        return erro_json(f'Erro ao processar: {str(e)}', 400)
    return jsonify({'status': 'ok', 'importados': count})


# ── Pluggy Open Finance ──

def pluggy_get_api_key():
    """Autentica com Pluggy e retorna API key (válida por 2h)."""
    client_id = os.getenv('PLUGGY_CLIENT_ID', '')
    client_secret = os.getenv('PLUGGY_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return None
    res = http_requests.post(f'{PLUGGY_API_URL}/auth', json={
        'clientId': client_id,
        'clientSecret': client_secret
    }, timeout=10)
    if res.status_code == 200:
        return res.json().get('apiKey')
    return None


@app.route('/api/pluggy/connect-token', methods=['POST'])
@login_required
def pluggy_connect_token():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    api_key = pluggy_get_api_key()
    if not api_key:
        return erro_json('Pluggy não configurado. Defina PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.', 500)

    user_id = get_current_user_id()
    res = http_requests.post(f'{PLUGGY_API_URL}/connect_token', json={
        'clientUserId': str(user_id)
    }, headers={'X-API-KEY': api_key}, timeout=10)

    if res.status_code in (200, 201):
        return jsonify({'accessToken': res.json().get('accessToken')})
    return erro_json('Erro ao gerar token de conexão.', 502)


@app.route('/api/pluggy/item-connected', methods=['POST'])
@login_required
def pluggy_item_connected():
    """Chamado pelo frontend após o widget Pluggy retornar sucesso."""
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    data = request.json or {}
    item_id = str(data.get('itemId', '')).strip()
    connector_name = str(data.get('connectorName', '')).strip()
    if not item_id:
        return erro_json('itemId é obrigatório.', 400)

    user_id = get_current_user_id()

    # Criar conta automática para esta conexão
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO contas (user_id, nome, emoji, tipo, saldo_inicial, cor, criado_em) VALUES (?, ?, '🏦', 'corrente', 0, '#007aff', ?)",
            (user_id, connector_name or 'Banco conectado', datetime.now(UTC).isoformat())
        )
        conta_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO conexoes_bancarias (user_id, item_id, connector_name, conta_id, criado_em) VALUES (?, ?, ?, ?, ?)",
            (user_id, item_id, connector_name, conta_id, datetime.now(UTC).isoformat())
        )

    return jsonify({'status': 'ok', 'conta_id': conta_id})


@app.route('/api/pluggy/sincronizar', methods=['POST'])
@login_required
def pluggy_sincronizar():
    """Puxa transações do Pluggy e importa como lançamentos."""
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    api_key = pluggy_get_api_key()
    if not api_key:
        return erro_json('Pluggy não configurado.', 500)

    user_id = get_current_user_id()
    headers = {'X-API-KEY': api_key}
    total_importados = 0

    with db_connection() as conn:
        conexoes = conn.execute(
            "SELECT item_id, conta_id FROM conexoes_bancarias WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchall()

    for item_id, conta_id in conexoes:
        # Buscar contas do item
        acc_res = http_requests.get(f'{PLUGGY_API_URL}/accounts?itemId={item_id}', headers=headers, timeout=15)
        if acc_res.status_code != 200:
            continue

        for account in acc_res.json().get('results', []):
            account_id = account.get('id')
            # Buscar transações
            page = 1
            while True:
                tx_res = http_requests.get(
                    f'{PLUGGY_API_URL}/transactions?accountId={account_id}&page={page}',
                    headers=headers, timeout=15
                )
                if tx_res.status_code != 200:
                    break
                tx_data = tx_res.json()
                transactions = tx_data.get('results', [])
                if not transactions:
                    break

                with db_connection() as conn:
                    for tx in transactions:
                        tx_id = tx.get('id', '')
                        # Evitar duplicatas pelo ID da transação Pluggy
                        existe = conn.execute(
                            "SELECT id FROM lancamentos WHERE user_id = ? AND descricao LIKE ? AND conta_id = ?",
                            (user_id, f'%[pluggy:{tx_id[:8]}]%', conta_id)
                        ).fetchone()
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
                        # Marcar com ID Pluggy para evitar duplicatas
                        descricao_marcada = f"{descricao} [pluggy:{tx_id[:8]}]"

                        conn.execute(
                            "INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual, conta_id) VALUES (?, ?, ?, ?, ?, ?, '', 0, 1, 1, ?)",
                            (user_id, data_tx, tipo, descricao_marcada, valor, categoria, conta_id)
                        )
                        total_importados += 1

                if page >= tx_data.get('totalPages', 1):
                    break
                page += 1

        # Atualizar timestamp
        with db_connection() as conn:
            conn.execute("UPDATE conexoes_bancarias SET atualizado_em = ? WHERE item_id = ? AND user_id = ?",
                (datetime.now(UTC).isoformat(), item_id, user_id))

    return jsonify({'status': 'ok', 'importados': total_importados})


@app.route('/api/pluggy/conexoes')
@login_required
def pluggy_conexoes():
    user_id = get_current_user_id()
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT cb.id, cb.item_id, cb.connector_name, cb.status, cb.atualizado_em, c.nome as conta_nome FROM conexoes_bancarias cb LEFT JOIN contas c ON c.id = cb.conta_id WHERE cb.user_id = ?",
            (user_id,)
        ).fetchall()
    return jsonify([{
        'id': r[0], 'item_id': r[1], 'connector_name': r[2],
        'status': r[3], 'atualizado_em': r[4], 'conta_nome': r[5]
    } for r in rows])


@app.route('/api/pluggy/conexoes/<int:id>', methods=['DELETE'])
@login_required
def pluggy_remover_conexao(id):
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    with db_connection() as conn:
        if conn.execute("DELETE FROM conexoes_bancarias WHERE id = ? AND user_id = ?", (id, get_current_user_id())).rowcount == 0:
            return erro_json('Conexão não encontrada.', 404)
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', '0') in ('1', 'true', 'True')
    port = int(os.getenv('PORT', '8000'))
    app.run(debug=debug, host='0.0.0.0', port=port)
