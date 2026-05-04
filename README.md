💰 Sistema de Controle Financeiro Pessoal

Este é um projeto local com interface web responsiva para registro e visualização de entradas, saídas, contas fixas, parcelamentos e geração de relatórios.

✅ Funcionalidades

Registro de lançamentos (entradas, saídas, salários, dívidas, contas fixas, parcelamentos);

Filtros por período e tipo de transação;

Modo claro/escuro com persistência;

Geração de relatórios em Excel com resumo mensal;

Visualização de contas fixas e dívidas futuras;

Edição e exclusão de lançamentos futuros;

Filtros rápidos por período, busca textual, ordenação e paginação na tabela;

Modal de edição com melhor experiência de uso e feedback visual com toasts;

Gráficos de resumo e distribuição por categoria;

Proteção CSRF para operações de escrita.

Autenticação com login/cadastro/logout e isolamento de dados por usuário.

Menu superior com abas estilo iOS glass e avatar com menu de perfil.

Perfil editável com nome, apelido, email, senha e upload de foto.

Páginas separadas para Dashboard, Lançamentos e Relatórios.

Exportação CSV por período com escopo por usuário.

📦 Estrutura de Pastas

project/
├── app.py                      # Servidor Flask
├── migrar_csv_para_sqlite.py   # Script de migração (executar uma única vez)
├── requirements.txt            # Dependências do projeto
├── data/
│   └── lancamentos.db          # Banco de dados SQLite (após migração)
├── static/
│   ├── style.css               # Estilos visuais
│   ├── script.js               # Lógica geral (tema, gráfico)
│   ├── form.js                 # Scripts do formulário de lançamento
│   └── lancamentos.js          # Scripts de edição/exclusão
└── templates/      
    └── index.html              # Interface principal

🚀 Como executar localmente

Crie um ambiente virtual (opcional):

python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate    # Windows

Instale as dependências:

pip install -r requirements.txt

Migre dados do CSV, se necessário:

python migrar_csv_para_sqlite.py

Execute o servidor local:

python app.py

Configuração por ambiente (opcional):

export FLASK_DEBUG=1   # ativa debug
export PORT=8000       # define porta
export SECRET_KEY='troque-esta-chave-em-producao'

Acesse no navegador:

http://localhost:8000

📊 Requisitos

Python 3.9+

## 🔐 Autenticação e multiusuário

- Rotas disponíveis:
  - `GET/POST /login`
  - `GET/POST /cadastro`
  - `POST /logout`
- Cada lançamento pertence a um usuário autenticado (`user_id`).
- A página principal exige login.
- Senhas são armazenadas com hash seguro.

## 👤 Perfil do usuário

- Avatar redondo clicável no topo com menu de opções.
- Edição de perfil via modal:
  - Nome
  - Apelido
  - Email
  - Nova senha (opcional)
  - Foto de perfil (PNG/JPG/JPEG/WEBP)
- Endpoint de perfil:
  - `GET /perfil`
  - `POST /perfil` (requer CSRF)

## 🧭 Páginas principais

- `GET /dashboard`
- `GET /lancamentos`
- `GET /relatorios`

## 📤 Exportação CSV

- Endpoint: `GET /relatorios/export/csv`
- Filtros suportados por query string:
  - `inicio=YYYY-MM-DD`
  - `fim=YYYY-MM-DD`
  - `tipo`
  - `categoria`
- O arquivo é gerado no formato UTF-8 BOM para melhor compatibilidade com Excel.

� Requisitos adicionais (opcional)

Acesso pela rede local: Certifique-se de que o firewall permita conexões na porta 8000

Interface pode ser acessada de celulares na mesma rede Wi-Fi

Feito com 💻 por William Campos.
