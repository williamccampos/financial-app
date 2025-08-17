💰 Sistema de Controle Financeiro Pessoal

Este é um projeto local com interface web responsiva para registro e visualização de entradas, saídas, contas fixas, parcelamentos e geração de relatórios.

✅ Funcionalidades

Registro de lançamentos (entradas, saídas, salários, dívidas, contas fixas, parcelamentos);

Filtros por período e tipo de transação;

Modo claro/escuro com persistência;

Geração de relatórios em Excel com resumo mensal;

Visualização de contas fixas e dívidas futuras;

Edição e exclusão de lançamentos futuros;

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

Acesse no navegador:

http://localhost:8000

📊 Requisitos

Python 3.9+

📁 Requisitos adicionais (opcional)

Acesso pela rede local: Certifique-se de que o firewall permita conexões na porta 8000

Interface pode ser acessada de celulares na mesma rede Wi-Fi

Feito com 💻 por William Camposv.