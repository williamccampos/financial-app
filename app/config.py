import os
import secrets

TIPOS_VALIDOS = {'entrada', 'saida', 'salario', 'recebimento', 'divida', 'conta'}

CATEGORIAS_PADRAO = [
    ('Moradia', '🏠'), ('Alimentação', '🍔'), ('Transporte', '🚗'),
    ('Educação', '📚'), ('Lazer', '🎮'), ('Saúde', '💊'),
    ('Cartão de Crédito', '💳'), ('Outros', '📦'),
]

CATEGORIA_KEYWORDS = {
    'Alimentação': ['mercado', 'supermercado', 'ifood', 'rappi', 'restaurante', 'padaria', 'açougue', 'hortifruti', 'lanchonete', 'pizza', 'burger', 'sushi', 'café', 'coffee', 'starbucks', 'mcdonald', 'subway', 'food', 'alimenta'],
    'Transporte': ['uber', '99', 'cabify', 'gasolina', 'combustível', 'estacionamento', 'pedágio', 'ônibus', 'metrô', 'trem', 'passagem', 'avião', 'latam', 'gol', 'azul', 'posto'],
    'Moradia': ['aluguel', 'condomínio', 'iptu', 'luz', 'energia', 'água', 'gás', 'internet', 'telefone', 'celular', 'vivo', 'claro', 'tim', 'oi'],
    'Saúde': ['farmácia', 'drogaria', 'médico', 'consulta', 'exame', 'hospital', 'plano de saúde', 'unimed', 'academia', 'gym', 'smart fit'],
    'Educação': ['curso', 'escola', 'faculdade', 'universidade', 'udemy', 'alura', 'livro', 'livraria', 'mensalidade'],
    'Lazer': ['netflix', 'spotify', 'disney', 'hbo', 'amazon prime', 'youtube', 'cinema', 'teatro', 'show', 'ingresso', 'game', 'steam', 'playstation', 'xbox', 'bar', 'balada', 'viagem', 'hotel', 'airbnb', 'booking'],
    'Cartão de Crédito': ['fatura', 'cartão', 'nubank', 'inter', 'c6'],
}

DB_PATH = 'data/lancamentos.db'
UPLOAD_DIR = os.path.join('static', 'uploads', 'avatars')
PLUGGY_API_URL = 'https://api.pluggy.ai'
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


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
