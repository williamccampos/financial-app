import os
import tempfile
import unittest
from contextlib import closing


class FinancialAppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")

        os.environ["SECRET_KEY"] = "test-secret-key"

        import app as financial_app

        financial_app.DB_PATH = self.db_path
        financial_app.app.config["TESTING"] = True
        financial_app.app.secret_key = "test-secret-key"
        financial_app.init_db()

        self.module = financial_app
        self.client = financial_app.app.test_client()

        self.client.post(
            "/cadastro",
            data={
                "name": "Teste",
                "email": "teste@example.com",
                "password": "SenhaForte123",
                "password_confirm": "SenhaForte123",
            },
        )

        self.client.post(
            "/login",
            data={"email": "teste@example.com", "password": "SenhaForte123"},
        )

        self.client.get("/dashboard")

        with self.client.session_transaction() as sess:
            self.csrf = sess.get("csrf_token")
            self.user_id = sess.get("user_id")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _headers(self, with_csrf=True):
        h = {"Content-Type": "application/json"}
        if with_csrf:
            h["X-CSRF-Token"] = self.csrf
        return h

    def _create_lancamento(self, **overrides):
        payload = {
            "data": "2026-05-01",
            "tipo": "entrada",
            "descricao": "Freela",
            "valor": 1500.0,
            "categoria": "Outros",
            "vencimento": "",
            "recorrente": False,
            "parcelas": 1,
        }
        payload.update(overrides)
        return self.client.post("/lancamento", json=payload, headers=self._headers())

    # ── CRUD básico ──

    def test_criar_editar_excluir_lancamento(self):
        res = self._create_lancamento()
        self.assertEqual(res.status_code, 200)

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, user_id FROM lancamentos LIMIT 1").fetchone()
            lid = row[0]
            self.assertEqual(row[1], self.user_id)

        get_res = self.client.get(f"/editar/{lid}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["descricao"], "Freela")

        update = get_res.get_json()
        update["descricao"] = "Freela Atualizado"
        update["valor"] = 1600.0
        self.assertEqual(
            self.client.post(f"/editar/{lid}", json=update, headers=self._headers()).status_code,
            200,
        )
        self.assertEqual(self.client.get(f"/editar/{lid}").get_json()["descricao"], "Freela Atualizado")

        self.assertEqual(
            self.client.delete(f"/excluir/{lid}", headers={"X-CSRF-Token": self.csrf}).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/excluir/{lid}", headers={"X-CSRF-Token": self.csrf}).status_code,
            404,
        )

    # ── Autenticação ──

    def test_rota_protegida_sem_login(self):
        other = self.module.app.test_client()
        res = other.get("/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.location)

    def test_login_credenciais_invalidas(self):
        other = self.module.app.test_client()
        res = other.post("/login", data={"email": "teste@example.com", "password": "errada"})
        self.assertEqual(res.status_code, 401)

    def test_cadastro_email_duplicado(self):
        res = self.client.post(
            "/cadastro",
            data={
                "name": "Outro",
                "email": "teste@example.com",
                "password": "SenhaForte123",
                "password_confirm": "SenhaForte123",
            },
        )
        self.assertEqual(res.status_code, 409)

    def test_cadastro_senhas_diferentes(self):
        res = self.client.post(
            "/cadastro",
            data={
                "name": "Novo",
                "email": "novo@example.com",
                "password": "SenhaForte123",
                "password_confirm": "OutraSenha99",
            },
        )
        self.assertEqual(res.status_code, 400)

    def test_cadastro_senha_curta(self):
        res = self.client.post(
            "/cadastro",
            data={
                "name": "Novo",
                "email": "novo2@example.com",
                "password": "123",
                "password_confirm": "123",
            },
        )
        self.assertEqual(res.status_code, 400)

    # ── CSRF ──

    def test_lancamento_sem_csrf_rejeitado(self):
        res = self.client.post(
            "/lancamento",
            json={"data": "2026-05-01", "tipo": "entrada", "descricao": "X", "valor": 10},
            headers=self._headers(with_csrf=False),
        )
        self.assertEqual(res.status_code, 403)

    def test_excluir_sem_csrf_rejeitado(self):
        self._create_lancamento()
        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            lid = conn.execute("SELECT id FROM lancamentos LIMIT 1").fetchone()[0]
        res = self.client.delete(f"/excluir/{lid}", headers={"Content-Type": "application/json"})
        self.assertEqual(res.status_code, 403)

    # ── Validação de campos ──

    def test_lancamento_valor_negativo(self):
        res = self._create_lancamento(valor=-100)
        self.assertEqual(res.status_code, 400)

    def test_lancamento_tipo_invalido(self):
        res = self._create_lancamento(tipo="invalido")
        self.assertEqual(res.status_code, 400)

    def test_lancamento_data_invalida(self):
        res = self._create_lancamento(data="nao-e-data")
        self.assertEqual(res.status_code, 400)

    def test_lancamento_descricao_vazia(self):
        res = self._create_lancamento(descricao="")
        self.assertEqual(res.status_code, 400)

    def test_lancamento_parcelas_fora_do_limite(self):
        res = self._create_lancamento(parcelas=200)
        self.assertEqual(res.status_code, 400)

    # ── Parcelas cartão de crédito ──

    def test_parcelas_cartao_credito_split(self):
        res = self._create_lancamento(
            tipo="saida",
            categoria="Cartão de Crédito",
            parcelas=3,
            valor=300.0,
            descricao="Compra parcelada",
        )
        self.assertEqual(res.status_code, 200)

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT valor, parcela_atual FROM lancamentos WHERE descricao = 'Compra parcelada' ORDER BY parcela_atual"
            ).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[0][0], 100.0, places=2)
        self.assertEqual(rows[0][1], 1)
        self.assertEqual(rows[2][1], 3)

    # ── Isolamento entre usuários ──

    def test_isolamento_dados_entre_usuarios(self):
        self._create_lancamento(descricao="Dado do user 1")

        other = self.module.app.test_client()
        other.post(
            "/cadastro",
            data={
                "name": "Outro",
                "email": "outro@example.com",
                "password": "SenhaForte123",
                "password_confirm": "SenhaForte123",
            },
        )
        other.post("/login", data={"email": "outro@example.com", "password": "SenhaForte123"})
        other.get("/dashboard")

        with other.session_transaction() as sess:
            csrf2 = sess.get("csrf_token")

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            lid = conn.execute("SELECT id FROM lancamentos WHERE descricao = 'Dado do user 1'").fetchone()[0]

        # Outro usuário não pode editar
        res = other.get(f"/editar/{lid}")
        self.assertEqual(res.status_code, 404)

        # Outro usuário não pode excluir
        res = other.delete(f"/excluir/{lid}", headers={"X-CSRF-Token": csrf2})
        self.assertEqual(res.status_code, 404)

    # ── Páginas e exportação ──

    def test_rotas_paginas_e_export_csv(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/lancamentos").status_code, 200)
        self.assertEqual(self.client.get("/relatorios").status_code, 200)

        csv_res = self.client.get("/relatorios/export/csv?inicio=2026-01-01&fim=2026-12-31")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("text/csv", csv_res.content_type)

    def test_export_csv_periodo_invalido(self):
        res = self.client.get("/relatorios/export/csv?inicio=2026-12-31&fim=2026-01-01")
        self.assertEqual(res.status_code, 400)

    def test_visao_geral_redireciona_para_dashboard(self):
        res = self.client.get("/visao-geral")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/dashboard", res.location)

    # ── Perfil ──

    def test_atualizacao_perfil(self):
        res = self.client.post(
            "/perfil",
            data={"name": "Teste Atualizado", "nickname": "Will", "email": "teste@example.com", "password": ""},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(res.status_code, 200)

        perfil = self.client.get("/perfil").get_json()
        self.assertEqual(perfil["name"], "Teste Atualizado")
        self.assertEqual(perfil["nickname"], "Will")

    def test_perfil_email_duplicado(self):
        self.client.post(
            "/cadastro",
            data={
                "name": "Segundo",
                "email": "segundo@example.com",
                "password": "SenhaForte123",
                "password_confirm": "SenhaForte123",
            },
        )
        res = self.client.post(
            "/perfil",
            data={"name": "Teste", "nickname": "", "email": "segundo@example.com", "password": ""},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(res.status_code, 409)

    # ── Rate limiting ──

    def test_rate_limiting_login(self):
        other = self.module.app.test_client()
        email = "rate@example.com"
        self.module.LOGIN_ATTEMPTS.pop(email, None)
        for _ in range(5):
            other.post("/login", data={"email": email, "password": "errada"})
        res = other.post("/login", data={"email": email, "password": "errada"})
        self.assertEqual(res.status_code, 429)
        self.module.LOGIN_ATTEMPTS.pop(email, None)

    # ── Orçamentos ──

    def test_criar_e_excluir_orcamento(self):
        res = self.client.post("/orcamento", json={
            "categoria": "Alimentação", "limite": 800, "mes": "2026-05"
        }, headers=self._headers())
        self.assertEqual(res.status_code, 200)

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, categoria, limite FROM orcamentos WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "Alimentação")
            self.assertAlmostEqual(row[2], 800.0)
            orc_id = row[0]

        res = self.client.delete(f"/orcamento/{orc_id}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(res.status_code, 200)

    def test_orcamento_limite_invalido(self):
        res = self.client.post("/orcamento", json={
            "categoria": "Lazer", "limite": -100, "mes": "2026-05"
        }, headers=self._headers())
        self.assertEqual(res.status_code, 400)

    def test_orcamento_sem_csrf(self):
        res = self.client.post("/orcamento", json={
            "categoria": "Lazer", "limite": 500, "mes": "2026-05"
        }, headers=self._headers(with_csrf=False))
        self.assertEqual(res.status_code, 403)

    # ── Metas ──

    def test_criar_depositar_e_excluir_meta(self):
        res = self.client.post("/meta", json={
            "nome": "Viagem", "emoji": "✈️", "valor_alvo": 5000, "prazo": "2026-12-31"
        }, headers=self._headers())
        self.assertEqual(res.status_code, 200)

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT id, nome, valor_alvo, valor_atual, concluida FROM metas WHERE user_id = ?", (self.user_id,)).fetchone()
            self.assertIsNotNone(row)
            meta_id = row[0]
            self.assertEqual(row[1], "Viagem")
            self.assertAlmostEqual(row[3], 0.0)

        # Depositar
        res = self.client.post(f"/meta/{meta_id}", json={"valor_deposito": 2000}, headers=self._headers())
        self.assertEqual(res.status_code, 200)

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT valor_atual FROM metas WHERE id = ?", (meta_id,)).fetchone()
            self.assertAlmostEqual(row[0], 2000.0)

        # Excluir
        res = self.client.delete(f"/meta/{meta_id}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(res.status_code, 200)

    def test_meta_auto_concluida(self):
        self.client.post("/meta", json={
            "nome": "Pequena", "valor_alvo": 100, "prazo": ""
        }, headers=self._headers())

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            meta_id = conn.execute("SELECT id FROM metas WHERE user_id = ? AND nome = 'Pequena'", (self.user_id,)).fetchone()[0]

        self.client.post(f"/meta/{meta_id}", json={"valor_deposito": 150}, headers=self._headers())

        with closing(self.module.sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT concluida FROM metas WHERE id = ?", (meta_id,)).fetchone()
            self.assertEqual(row[0], 1)

    def test_meta_valor_invalido(self):
        res = self.client.post("/meta", json={
            "nome": "Teste", "valor_alvo": -500
        }, headers=self._headers())
        self.assertEqual(res.status_code, 400)

    # ── Recorrência ──

    def test_gerar_recorrentes(self):
        self._create_lancamento(descricao="Aluguel", tipo="conta", recorrente=True, valor=1500, categoria="Moradia")

        res = self.client.post("/gerar-recorrentes", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Pode ser 0 se já existe no mês atual (o lançamento criado acima já é do mês)
        self.assertIn("gerados", data)

    def test_recorrentes_nao_duplica(self):
        # Criar recorrente no mês anterior para forçar geração
        self._create_lancamento(descricao="Internet", tipo="conta", recorrente=True, valor=100, categoria="Moradia", data="2026-04-01")

        r1 = self.client.post("/gerar-recorrentes", headers={"X-CSRF-Token": self.csrf})
        gerados1 = r1.get_json()["gerados"]
        self.assertEqual(gerados1, 1)

        # Segunda chamada não deve duplicar
        r2 = self.client.post("/gerar-recorrentes", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r2.get_json()["gerados"], 0)

    # ── Dashboard com orçamentos e metas ──

    def test_dashboard_inclui_orcamentos_e_metas(self):
        self.client.post("/orcamento", json={"categoria": "Lazer", "limite": 300, "mes": "2026-05"}, headers=self._headers())
        self.client.post("/meta", json={"nome": "Carro", "valor_alvo": 50000}, headers=self._headers())

        html = self.client.get("/dashboard").data.decode()
        self.assertIn("Orçamentos do mês", html)
        self.assertIn("Metas financeiras", html)
        self.assertIn("Lazer", html)
        self.assertIn("Carro", html)

    # ── Fase 2: APIs ──

    def test_api_lancamentos_paginado(self):
        for i in range(5):
            self._create_lancamento(descricao=f"Item {i}", valor=100 + i)
        res = self.client.get("/api/lancamentos?page=1&per_page=3")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(data["page"], 1)
        self.assertGreaterEqual(data["total"], 5)

    def test_api_lancamentos_busca(self):
        self._create_lancamento(descricao="Netflix Premium", valor=45)
        res = self.client.get("/api/lancamentos?busca=Netflix")
        data = res.get_json()
        self.assertTrue(any("Netflix" in i["descricao"] for i in data["items"]))

    def test_api_spending_line(self):
        self._create_lancamento(tipo="saida", valor=100, data="2026-05-01")
        self._create_lancamento(tipo="saida", valor=200, data="2026-05-02")
        res = self.client.get("/api/spending-line?mes=2026-05")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertGreaterEqual(len(data["pontos"]), 2)
        self.assertGreater(data["pontos"][-1]["gasto_acumulado"], 0)

    def test_api_assinaturas(self):
        self._create_lancamento(descricao="Netflix", tipo="saida", recorrente=True, valor=45)
        res = self.client.get("/api/assinaturas")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(any(s["descricao"] == "Netflix" for s in data["assinaturas"]))

    def test_api_categorias(self):
        res = self.client.get("/api/categorias")
        self.assertEqual(res.status_code, 200)
        cats = res.get_json()
        self.assertTrue(len(cats) > 0)
        self.assertIn("emoji", cats[0])

    def test_salvar_categoria_custom(self):
        res = self.client.post("/api/categorias", json={"nome": "Pets", "emoji": "🐕"}, headers=self._headers())
        self.assertEqual(res.status_code, 200)
        cats = self.client.get("/api/categorias").get_json()
        self.assertTrue(any(c["nome"] == "Pets" for c in cats))

    def test_api_rollover(self):
        res = self.client.get("/api/rollover")
        self.assertEqual(res.status_code, 200)
        self.assertIn("rollovers", res.get_json())

    # ── Fase 3: Multi-contas ──

    def test_criar_e_listar_contas(self):
        res = self.client.post("/api/contas", json={
            "nome": "Nubank", "emoji": "💜", "tipo": "corrente", "saldo_inicial": 1000
        }, headers=self._headers())
        self.assertEqual(res.status_code, 200)

        contas = self.client.get("/api/contas").get_json()
        self.assertTrue(any(c["nome"] == "Nubank" for c in contas))
        nubank = next(c for c in contas if c["nome"] == "Nubank")
        self.assertAlmostEqual(nubank["saldo"], 1000.0)

    def test_excluir_conta(self):
        self.client.post("/api/contas", json={"nome": "Temp", "saldo_inicial": 0}, headers=self._headers())
        contas = self.client.get("/api/contas").get_json()
        cid = next(c["id"] for c in contas if c["nome"] == "Temp")
        res = self.client.delete(f"/api/contas/{cid}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(res.status_code, 200)

    # ── Patrimônio ──

    def test_api_patrimonio(self):
        self._create_lancamento(tipo="salario", valor=5000)
        res = self.client.get("/api/patrimonio")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("total", data)
        self.assertIn("evolucao", data)
        self.assertGreater(data["total"], 0)

    # ── Relatórios avançados ──

    def test_api_comparativo_mensal(self):
        self._create_lancamento(tipo="saida", valor=200, categoria="Alimentação")
        res = self.client.get("/api/relatorio/comparativo?meses=3")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("meses", data)
        self.assertIn("medias_categoria", data)

    # ── Compartilhamento ──

    def test_compartilhar_e_listar(self):
        # Criar segundo usuário
        other = self.module.app.test_client()
        other.post("/cadastro", data={"name": "Parceiro", "email": "parceiro@test.com", "password": "SenhaForte123", "password_confirm": "SenhaForte123"})

        res = self.client.post("/api/compartilhar", json={
            "email": "parceiro@test.com", "permissao": "leitura"
        }, headers=self._headers())
        self.assertEqual(res.status_code, 200)

        lista = self.client.get("/api/compartilhamentos").get_json()
        self.assertEqual(len(lista["compartilhados"]), 1)
        self.assertEqual(lista["compartilhados"][0]["email"], "parceiro@test.com")

        # Remover
        sid = lista["compartilhados"][0]["id"]
        res = self.client.delete(f"/api/compartilhar/{sid}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(res.status_code, 200)

    def test_compartilhar_consigo_mesmo(self):
        res = self.client.post("/api/compartilhar", json={
            "email": "teste@example.com", "permissao": "leitura"
        }, headers=self._headers())
        self.assertEqual(res.status_code, 400)

    # ── Importação CSV ──

    def test_importar_csv(self):
        csv_content = "data,descricao,valor,categoria\n2026-05-01,Mercado,-150.50,Alimentação\n2026-05-02,Salário,3000,\n"
        from io import BytesIO
        data = {"arquivo": (BytesIO(csv_content.encode("utf-8-sig")), "extrato.csv")}
        res = self.client.post("/importar/csv", data=data, headers={"X-CSRF-Token": self.csrf}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["importados"], 2)

    def test_importar_csv_formato_invalido(self):
        from io import BytesIO
        data = {"arquivo": (BytesIO(b"not csv"), "file.txt")}
        res = self.client.post("/importar/csv", data=data, headers={"X-CSRF-Token": self.csrf}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)

    # ── Fase 4: IA ──

    def test_sugerir_categoria_por_keywords(self):
        res = self.client.get("/api/sugerir-categoria?descricao=Uber")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["categoria"], "Transporte")
        self.assertGreater(data["confianca"], 0.5)

    def test_sugerir_categoria_por_historico(self):
        self._create_lancamento(descricao="Padaria do Zé", categoria="Alimentação")
        self._create_lancamento(descricao="Padaria do Zé", categoria="Alimentação")
        res = self.client.get("/api/sugerir-categoria?descricao=Padaria do Zé")
        data = res.get_json()
        self.assertEqual(data["categoria"], "Alimentação")
        self.assertEqual(data["fonte"], "historico")

    def test_sugerir_categoria_vazia(self):
        res = self.client.get("/api/sugerir-categoria?descricao=xyzabc123")
        data = res.get_json()
        self.assertEqual(data["categoria"], "")

    def test_api_insights(self):
        self._create_lancamento(tipo="saida", valor=500, categoria="Alimentação")
        res = self.client.get("/api/insights")
        self.assertEqual(res.status_code, 200)
        self.assertIn("insights", res.get_json())

    def test_api_projecao(self):
        self._create_lancamento(tipo="salario", valor=5000)
        self._create_lancamento(tipo="saida", valor=1000, categoria="Moradia")
        res = self.client.get("/api/projecao")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("saldo_projetado", data)
        self.assertIn("gasto_diario_medio", data)
        self.assertGreater(data["entradas"], 0)


if __name__ == "__main__":
    unittest.main()
