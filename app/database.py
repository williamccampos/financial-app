import sqlite3
from contextlib import contextmanager
from app.config import DATABASE_URL, DB_TYPE, DB_PATH

_pg_pool = None


def _get_pg_connection():
    import psycopg2
    url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    return psycopg2.connect(url, sslmode='require')


class PgCursorWrapper:
    """Wraps psycopg2 cursor to provide sqlite-compatible interface."""
    def __init__(self, conn):
        self._conn = conn
        self._cursor = None
        self.rowcount = 0
        self.description = None

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s')
        self._cursor = self._conn.cursor()
        self._cursor.execute(sql, params)
        self.rowcount = self._cursor.rowcount
        self.description = self._cursor.description
        return self

    def fetchone(self):
        return self._cursor.fetchone() if self._cursor else None

    def fetchall(self):
        return self._cursor.fetchall() if self._cursor else []


class PgConnectionWrapper:
    """Wraps psycopg2 connection to provide sqlite-compatible interface."""
    def __init__(self, conn):
        self._conn = conn
        self._last_cursor = None

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s')
        cur = self._conn.cursor()
        cur.execute(sql, params)
        self._last_cursor = cur
        wrapper = type('CursorResult', (), {
            'rowcount': cur.rowcount,
            'description': cur.description,
            'fetchone': cur.fetchone,
            'fetchall': cur.fetchall,
        })()
        return wrapper

    def commit(self):
        self._conn.commit()

    def close(self):
        pass  # pool handles this


@contextmanager
def db_connection():
    if DB_TYPE == 'postgresql':
        conn = _get_pg_connection()
        wrapper = PgConnectionWrapper(conn)
        try:
            yield wrapper
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


@contextmanager
def raw_connection():
    """Returns the raw DB connection (for pandas read_sql_query)."""
    if DB_TYPE == 'postgresql':
        conn = _get_pg_connection()
        try:
            yield conn
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            yield conn
        finally:
            conn.close()


def sql(statement):
    """Adapt SQL for current DB type."""
    if DB_TYPE == 'postgresql':
        statement = statement.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        statement = statement.replace('AUTOINCREMENT', '')
        statement = statement.replace("strftime('%Y-%m', data)", "TO_CHAR(data::date, 'YYYY-MM')")
        statement = statement.replace("strftime('%Y-%m-%d', data)", "TO_CHAR(data::date, 'YYYY-MM-DD')")
        # INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
        if 'INSERT OR REPLACE INTO orcamentos' in statement:
            statement = statement.replace('INSERT OR REPLACE INTO orcamentos', 'INSERT INTO orcamentos')
            statement = statement.rstrip().rstrip(')')
            statement += ') ON CONFLICT (user_id, categoria, mes) DO UPDATE SET limite = EXCLUDED.limite'
        elif 'INSERT OR REPLACE INTO categorias' in statement:
            statement = statement.replace('INSERT OR REPLACE INTO categorias', 'INSERT INTO categorias')
            statement = statement.rstrip().rstrip(')')
            statement += ') ON CONFLICT (user_id, nome) DO UPDATE SET emoji = EXCLUDED.emoji'
        elif 'INSERT OR REPLACE INTO compartilhamentos' in statement:
            statement = statement.replace('INSERT OR REPLACE INTO compartilhamentos', 'INSERT INTO compartilhamentos')
            statement = statement.rstrip().rstrip(')')
            statement += ') ON CONFLICT (owner_id, shared_with_id) DO UPDATE SET permissao = EXCLUDED.permissao'
    return statement


def init_db():
    with db_connection() as conn:
        if DB_TYPE == 'sqlite':
            _init_sqlite(conn)
        else:
            _init_postgresql(conn)


def _init_sqlite(conn):
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
    if 'conta_id' not in cols:
        conn.execute("ALTER TABLE lancamentos ADD COLUMN conta_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lancamentos_user_data ON lancamentos(user_id, data)")
    user_cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if 'nickname' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT DEFAULT ''")
    if 'avatar_url' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")
    if 'onboarding_done' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN onboarding_done INTEGER DEFAULT 0")
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


def _init_postgresql(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            nickname TEXT DEFAULT '',
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            avatar_url TEXT DEFAULT '',
            onboarding_done INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS lancamentos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            data TEXT,
            tipo TEXT,
            descricao TEXT,
            valor DOUBLE PRECISION,
            categoria TEXT,
            vencimento TEXT,
            recorrente INTEGER DEFAULT 0,
            parcelas INTEGER DEFAULT 1,
            parcela_atual INTEGER DEFAULT 1,
            conta_id INTEGER
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_done INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lancamentos_user_data ON lancamentos(user_id, data)")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS orcamentos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            categoria TEXT NOT NULL,
            limite DOUBLE PRECISION NOT NULL,
            mes TEXT NOT NULL,
            rollover INTEGER DEFAULT 0,
            UNIQUE(user_id, categoria, mes)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metas (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            nome TEXT NOT NULL,
            emoji TEXT DEFAULT '🎯',
            valor_alvo DOUBLE PRECISION NOT NULL,
            valor_atual DOUBLE PRECISION DEFAULT 0,
            prazo TEXT,
            criado_em TEXT NOT NULL,
            concluida INTEGER DEFAULT 0
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orcamentos_user ON orcamentos(user_id, mes)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metas_user ON metas(user_id)")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS categorias (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            nome TEXT NOT NULL,
            emoji TEXT DEFAULT '📁',
            UNIQUE(user_id, nome)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contas (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            nome TEXT NOT NULL,
            emoji TEXT DEFAULT '🏦',
            tipo TEXT DEFAULT 'corrente',
            saldo_inicial DOUBLE PRECISION DEFAULT 0,
            cor TEXT DEFAULT '#007aff',
            ativa INTEGER DEFAULT 1,
            criado_em TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS compartilhamentos (
            id SERIAL PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            shared_with_id INTEGER NOT NULL REFERENCES users(id),
            permissao TEXT DEFAULT 'leitura',
            criado_em TEXT NOT NULL,
            UNIQUE(owner_id, shared_with_id)
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contas_user ON contas(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_compartilhamentos ON compartilhamentos(owner_id, shared_with_id)")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS conexoes_bancarias (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            item_id TEXT NOT NULL,
            connector_name TEXT DEFAULT '',
            status TEXT DEFAULT 'connected',
            conta_id INTEGER REFERENCES contas(id),
            criado_em TEXT NOT NULL,
            atualizado_em TEXT
        )
    ''')
