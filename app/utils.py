import re
import time
import secrets
import pandas as pd
from datetime import datetime
from functools import wraps
from flask import request, jsonify, session, redirect, url_for
from app.database import db_connection, raw_connection, sql
from app.config import TIPOS_VALIDOS, CATEGORIAS_PADRAO, MAX_LOGIN_ATTEMPTS, LOGIN_WINDOW_SECONDS, DB_TYPE

LOGIN_ATTEMPTS = {}


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
        'id': row[0], 'name': row[1], 'nickname': row[2] or '',
        'email': row[3], 'avatar_url': row[4] or ''
    }


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not get_current_user_id():
            if request.path.startswith('/lancamento') or request.path.startswith('/editar') or request.path.startswith('/excluir'):
                return jsonify({'erro': 'Não autenticado'}), 401
            return redirect(url_for('auth.login'))
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
    ph = '%s' if DB_TYPE == 'postgresql' else '?'
    clauses = [f"user_id = {ph}"]
    params = [user_id]
    if inicio:
        clauses.append(f"data >= {ph}"); params.append(inicio)
    if fim:
        clauses.append(f"data <= {ph}"); params.append(fim)
    if tipo and tipo != 'todos':
        clauses.append(f"tipo = {ph}"); params.append(tipo)
    if categoria:
        clauses.append(f"categoria = {ph}"); params.append(categoria)
    where = " AND ".join(clauses)

    with raw_connection() as conn:
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
    return {'entrada': float(total_entrada), 'saida': float(total_saida), 'saldo': float(total_entrada - total_saida)}


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

    orcamentos = []
    if user_id:
        with db_connection() as conn:
            rows = conn.execute(
                "SELECT id, categoria, limite, rollover FROM orcamentos WHERE user_id = ? AND mes = ?",
                (user_id, mes_atual)
            ).fetchall()
            for r in rows:
                gasto = conn.execute(
                    sql("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE user_id = ? AND categoria = ? AND strftime('%Y-%m', data) = ? AND tipo IN ('saida','divida','conta')"),
                    (user_id, r[1], mes_atual)
                ).fetchone()[0]
                pct = round((gasto / r[2]) * 100, 1) if r[2] > 0 else 0
                orcamentos.append({'id': r[0], 'categoria': r[1], 'limite': r[2], 'gasto': float(gasto), 'percentual': pct, 'rollover': r[3]})

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

    with db_connection() as conn:
        cat_rows = conn.execute("SELECT nome, emoji FROM categorias WHERE user_id = ?", (user_id,)).fetchall()
    if cat_rows:
        ctx['categorias_emoji'] = {r[0]: r[1] for r in cat_rows}
    else:
        ctx['categorias_emoji'] = {c[0]: c[1] for c in CATEGORIAS_PADRAO}

    with db_connection() as conn:
        sub_rows = conn.execute(
            "SELECT descricao, AVG(valor) as media FROM lancamentos WHERE user_id = ? AND recorrente = 1 AND tipo IN ('saida','conta') GROUP BY descricao ORDER BY media DESC LIMIT 10",
            (user_id,)
        ).fetchall()
    ctx['assinaturas'] = [{'descricao': r[0], 'valor': round(r[1], 2)} for r in sub_rows]
    ctx['assinaturas_total'] = round(sum(r[1] for r in sub_rows), 2)

    return ctx
