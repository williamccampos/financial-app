import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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

        lanc_cols = [row[1] for row in conn.execute("PRAGMA table_info(lancamentos)").fetchall()]
        if 'conta_id' not in lanc_cols:
            conn.execute("ALTER TABLE lancamentos ADD COLUMN conta_id INTEGER")

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
