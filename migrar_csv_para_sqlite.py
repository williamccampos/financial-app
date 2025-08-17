import pandas as pd
import sqlite3
import os

CSV_PATH = 'data/lancamentos.csv'
DB_PATH = 'data/lancamentos.db'

# Verifica se o CSV existe
if not os.path.exists(CSV_PATH):
    print("Arquivo CSV não encontrado.")
    exit()

# Lê os dados do CSV
df = pd.read_csv(CSV_PATH)

# Converte valores e campos booleanos
df['valor'] = df['valor'].astype(float)
df['recorrente'] = df.get('recorrente', False).fillna(False).astype(int)

# Cria a tabela e insere os dados no SQLite
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
            recorrente INTEGER DEFAULT 0
        )
    ''')

    for _, row in df.iterrows():
        conn.execute('''INSERT INTO lancamentos
            (data, tipo, descricao, valor, categoria, vencimento, recorrente)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', (
            row['data'], row['tipo'], row['descricao'], row['valor'],
            row.get('categoria', ''), row.get('vencimento', ''), row.get('recorrente', 0)
        ))

print("Migração concluída com sucesso!")