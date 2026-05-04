# FinanZen — Roadmap de Próximos Passos

## Estado Atual (v1.0 — MVP)

- **Deploy:** Render (produção)
- **Stack:** Python/Flask, SQLite, Vanilla JS, Chart.js
- **Testes:** 50 passando
- **APIs:** 42 endpoints
- **Features:** Lançamentos, orçamentos, metas, gráficos, multi-contas, patrimônio, relatórios, compartilhamento, importação CSV, Open Finance (Pluggy), categorização IA, insights, projeção, PWA

---

## Fase 5 — Infraestrutura e Escalabilidade

### 5.1 Migrar SQLite → PostgreSQL
**Prioridade:** 🔴 Alta (bloqueante para múltiplos usuários)
**Motivo:** SQLite não suporta escrita concorrente. Com 10+ usuários simultâneos, vai travar.
**Como:**
- Render oferece PostgreSQL gratuito (90 dias) ou $7/mês
- Trocar `sqlite3` por `psycopg2` no `app.py`
- Usar SQLAlchemy como ORM para abstrair o banco
- Migrar schema com Alembic (versionamento de migrations)
- Adaptar queries que usam `strftime()` (SQLite) para `DATE_TRUNC()` (PostgreSQL)

**Estimativa:** 4-6 horas

### 5.2 Separar app.py em módulos
**Prioridade:** 🟡 Média
**Motivo:** 1.734 linhas em um arquivo dificulta manutenção.
**Estrutura proposta:**
```
app/
├── __init__.py          # Flask app factory
├── models.py            # SQLAlchemy models
├── routes/
│   ├── auth.py          # Login, cadastro, logout
│   ├── lancamentos.py   # CRUD lançamentos
│   ├── orcamentos.py    # Orçamentos e rollover
│   ├── metas.py         # Metas financeiras
│   ├── relatorios.py    # Relatórios e export
│   ├── contas.py        # Multi-contas e patrimônio
│   ├── social.py        # Compartilhamento
│   ├── pluggy.py        # Open Finance
│   └── ia.py            # Categorização, insights, projeção
├── services/
│   ├── pluggy_service.py
│   └── ia_service.py
└── utils.py             # Helpers compartilhados
```

**Estimativa:** 3-4 horas

### 5.3 Cache com Redis
**Prioridade:** 🟢 Baixa (quando tiver 100+ usuários)
**O que cachear:**
- Patrimônio líquido (muda só quando há novo lançamento)
- Insights (recalcular 1x por hora, não a cada request)
- Categorias do usuário
- Resultado da spending line

---

## Fase 6 — Experiência do Usuário

### 6.1 Onboarding para novos usuários
**Prioridade:** 🔴 Alta (retenção)
**Fluxo:**
1. Após cadastro, tela de boas-vindas com 3 passos
2. Passo 1: "Qual sua renda mensal?" → cria lançamento de salário recorrente
3. Passo 2: "Quais suas contas fixas?" → cria aluguel, internet, etc.
4. Passo 3: "Defina um orçamento" → cria orçamentos por categoria
5. Redireciona para dashboard com dados já populados

### 6.2 Notificações push (PWA)
**Prioridade:** 🟡 Média
**Como:**
- Usar Web Push API com VAPID keys
- Notificar: contas vencendo em 3 dias, orçamento acima de 80%, meta atingida
- Tabela `push_subscriptions` para armazenar tokens
- Endpoint `/api/push/subscribe` e job diário para enviar

### 6.3 Dashboard mobile-first
**Prioridade:** 🟡 Média
**Melhorias:**
- Cards de resumo com swipe horizontal (entradas, saídas, saldo)
- Bottom navigation bar em vez de top tabs no mobile
- Pull-to-refresh para sincronizar dados
- Gráficos com touch/zoom

### 6.4 Modo escuro automático por horário
**Prioridade:** 🟢 Baixa
- Opção "Automático" além de Claro/Escuro
- Usa `prefers-color-scheme` do sistema + horário (escuro após 18h)

---

## Fase 7 — Features Avançadas

### 7.1 Modo família (visualização consolidada)
**Prioridade:** 🟡 Média
**Como funciona:**
- Quem compartilhou com permissão "escrita" aparece como membro da família
- Nova aba "Família" no dashboard
- Mostra: gastos consolidados, orçamento familiar, quem gastou o quê
- Cada membro mantém seus dados individuais + visão compartilhada

### 7.2 Planejamento financeiro
**Prioridade:** 🟡 Média
**Features:**
- Simulador de investimentos (juros compostos)
- Calculadora de independência financeira
- Planejamento de aposentadoria (quanto poupar por mês)
- Simulador de financiamento imobiliário

### 7.3 Integração com mais bancos (Open Finance produção)
**Prioridade:** 🔴 Alta (quando tiver CNPJ)
**Passos:**
1. Solicitar acesso produção no Pluggy (requer CNPJ)
2. Remover `includeSandbox: true` do widget
3. Configurar webhooks para sincronização automática
4. Implementar refresh automático diário das conexões

### 7.4 Importação OFX
**Prioridade:** 🟢 Baixa
- Além de CSV, aceitar arquivos OFX (formato padrão de extratos bancários)
- Biblioteca `ofxparse` para Python
- Detecção automática de formato no upload

---

## Fase 8 — Monetização

### 8.1 Modelo freemium
**Plano gratuito:**
- 1 conta bancária
- Lançamentos manuais ilimitados
- Orçamentos e metas
- Gráficos básicos

**Plano Pro (R$ 9,90/mês):**
- Multi-contas ilimitadas
- Open Finance (conexão automática)
- Insights IA avançados
- Relatórios comparativos
- Compartilhamento familiar
- Importação CSV/OFX
- Exportação PDF

**Plano Família (R$ 14,90/mês):**
- Tudo do Pro
- Até 5 membros
- Dashboard familiar consolidado
- Orçamento compartilhado

### 8.2 Implementação técnica
- Tabela `planos` e `assinaturas` no banco
- Middleware que verifica plano antes de liberar features premium
- Integração com Stripe ou Mercado Pago para pagamentos
- Página de pricing com comparativo de planos

---

## Fase 9 — App Nativo

### 9.1 Flutter (recomendado)
**Motivo:** Já instalado no Mac, single codebase para iOS + Android, performance nativa.
**Abordagem:**
- Consumir as 42 APIs JSON existentes
- Usar `flutter_pluggy_connect` para Open Finance nativo
- Publicar na App Store e Google Play
- Manter o site web como versão PWA

### 9.2 Alternativa: React Native
- Se preferir ecossistema JavaScript
- `react-native-pluggy-connect` disponível
- Expo para build simplificado

---

## Ordem de Execução Recomendada

| # | Item | Impacto | Esforço |
|---|---|---|---|
| 1 | PostgreSQL | Escala | 4-6h |
| 2 | Onboarding | Retenção | 3-4h |
| 3 | Open Finance produção | Diferencial | 2h + aprovação Pluggy |
| 4 | Modularizar app.py | Manutenção | 3-4h |
| 5 | Notificações push | Engajamento | 4-5h |
| 6 | Modo família | Feature | 6-8h |
| 7 | Monetização (Stripe) | Receita | 8-10h |
| 8 | App Flutter | Alcance | 40-60h |

---

*Documento criado em 03/05/2026 — FinanZen v1.0*
