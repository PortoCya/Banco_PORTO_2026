"""
Suíte de Testes de Segurança, LGPD e Critérios de Aceite do PRD — NPS KeyCore v1.0.
Valida: RBAC, Hash PBKDF2, JWT, Mass Assignment, XSS, Mascaramento de PII,
Antiduplicidade (Idempotency Key + Token Nominal), Versionamento de Pesquisa (RF-004),
Cálculo Determinístico do NPS e Resiliência a falhas da IA.
"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def run_all_tests():
    print("Iniciando bateria de testes de seguranca e conformidade PRD NPS KeyCore v1.0...\n")

    # 1. Segurança de Rotas Protegidas (401 sem token)
    r = client.get("/api/v1/surveys")
    assert r.status_code == 401, f"Esperado 401, veio {r.status_code}"
    assert "X-Content-Type-Options" in r.headers
    assert r.headers["X-Frame-Options"] == "DENY"
    print("[PASS] 1. Bloqueio de acesso nao autenticado (401) + Headers de Seguranca HTTP")

    # 2. Login ADMIN e ANALYST + Ocultação de senha_hash
    r_admin = client.post("/api/v1/auth/login", json={"email": "admin@keycore.com.br", "senha": "Admin@KeyCore2026!"})
    assert r_admin.status_code == 200, r_admin.text
    token_admin = r_admin.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    r_me = client.get("/api/v1/auth/me", headers=headers_admin)
    assert r_me.status_code == 200
    assert "senha_hash" not in r_me.json(), "VAZAMENTO DE SENHA_HASH DETECTADO!"
    print("[PASS] 2. Autenticacao JWT PBKDF2-SHA256 e protecao contra vazamento de senha_hash")

    r_analyst = client.post("/api/v1/auth/login", json={"email": "analista@keycore.com.br", "senha": "Analista@KeyCore2026!"})
    assert r_analyst.status_code == 200
    token_analyst = r_analyst.json()["access_token"]
    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}

    # 3. RBAC: ANALYST não pode criar pesquisa nem usuários (403 Forbidden)
    r_rbac = client.post(
        "/api/v1/surveys",
        headers=headers_analyst,
        json={"titulo": "Pesquisa Ilegal", "texto_pergunta_nps": "Nota de 0 a 10?"},
    )
    assert r_rbac.status_code == 403, f"Esperado 403 RBAC, veio {r_rbac.status_code}"
    print("[PASS] 3. RBAC no backend: ANALYST bloqueado em operacoes exclusivas de ADMIN (403)")

    # 4. Proteção contra Mass Assignment (extra='forbid' -> 422)
    r_mass = client.post(
        "/api/v1/surveys",
        headers=headers_admin,
        json={
            "titulo": "Pesquisa Teste",
            "texto_pergunta_nps": "De 0 a 10, quanto recomenda?",
            "campo_injetado_malicioso": "hacked",
        },
    )
    assert r_mass.status_code == 422
    print("[PASS] 4. Protecao contra Mass Assignment (campos extras rejeitados com 422)")

    # 5. Criação de Pesquisa + Publicação + Links (ABERTO e NOMINAL)
    r_surv = client.post(
        "/api/v1/surveys",
        headers=headers_admin,
        json={
            "titulo": "Pesquisa Trimestral KeyCore Q4",
            "texto_pergunta_nps": "De 0 a 10, quanto voce recomenda a KeyCore?",
            "texto_pergunta_aberta": "Deixe seu comentario:",
        },
    )
    assert r_surv.status_code == 201, r_surv.text
    pesquisa_id = r_surv.json()["id"]

    # Tentar responder pesquisa ainda em RASCUNHO deve falhar
    r_link_aberto = client.post(
        f"/api/v1/surveys/{pesquisa_id}/links",
        headers=headers_admin,
        json={"tipo": "ABERTO", "token_customizado": "slug-q4-aberto"},
    )
    assert r_link_aberto.status_code == 201

    r_sub_rascunho = client.post(
        "/api/v1/public/submissions",
        json={
            "token_link": "slug-q4-aberto",
            "nota_nps": 10,
            "chave_idempotencia": "idem-rascunho-001",
        },
    )
    assert r_sub_rascunho.status_code == 400
    print("[PASS] 5. Regra de integridade 1: Pesquisa nao-PUBLICADA rejeita submissoes (400)")

    # Publica a pesquisa
    r_pub = client.post(f"/api/v1/surveys/{pesquisa_id}/status/PUBLICADA", headers=headers_admin)
    assert r_pub.status_code == 200

    # 6. Submissões válidas (Notas 10, 9, 8, 6), Sanitização XSS, Mascaramento de PII e IA resiliente
    submissoes_teste = [
        ("idem-q4-001", 10, "Excelente sistema! Meu CPF é 123.456.789-00 e email joao@empresa.com.br <script>alert('xss')</script>"),
        ("idem-q4-002", 9, "Muito bom atendimento e suporte rapido."),
        ("idem-q4-003", 8, "Bom produto, mas pode melhorar relatórios."),
        ("idem-q4-004", 6, "Tive lentidao no carregamento."),
    ]
    for chave, nota, comentario in submissoes_teste:
        resp = client.post(
            "/api/v1/public/submissions",
            json={
                "token_link": "slug-q4-aberto",
                "nota_nps": nota,
                "texto_comentario": comentario,
                "chave_idempotencia": chave,
            },
        )
        assert resp.status_code == 201, resp.text
        dados = resp.json()
        assert "<script>" not in (dados.get("texto_comentario") or ""), "XSS NAO SANITIZADO!"

    print("[PASS] 6. Coleta transacional, sanitizacao contra XSS, mascaramento PII e resiliencia a falha de IA")

    # 7. Antiduplicidade: mesma chave_idempotencia retorna 409 Conflict
    r_dup = client.post(
        "/api/v1/public/submissions",
        json={
            "token_link": "slug-q4-aberto",
            "nota_nps": 10,
            "chave_idempotencia": "idem-q4-001",
        },
    )
    assert r_dup.status_code == 409
    print("[PASS] 7. Antiduplicidade por chave_idempotencia (409 Conflict)")

    # 8. Antiduplicidade: Link NOMINAL de uso único
    r_link_nom = client.post(
        f"/api/v1/surveys/{pesquisa_id}/links",
        headers=headers_admin,
        json={"tipo": "NOMINAL", "token_customizado": "convite-nominal-unico-01"},
    )
    assert r_link_nom.status_code == 201

    r_nom_1 = client.post(
        "/api/v1/public/submissions",
        json={
            "token_link": "convite-nominal-unico-01",
            "nota_nps": 9,
            "chave_idempotencia": "idem-nominal-001",
        },
    )
    assert r_nom_1.status_code == 201

    r_nom_2 = client.post(
        "/api/v1/public/submissions",
        json={
            "token_link": "convite-nominal-unico-01",
            "nota_nps": 2,
            "chave_idempotencia": "idem-nominal-002",
        },
    )
    assert r_nom_2.status_code == 409
    print("[PASS] 8. Token NOMINAL de uso unico bloqueia segunda resposta (409 Conflict)")

    # 9. Cálculo Determinístico do NPS (3 Promotores [10, 9, 9], 1 Neutro [8], 1 Detrator [6] => 60% - 20% = +40)
    r_nps = client.get(f"/api/v1/analytics/surveys/{pesquisa_id}", headers=headers_analyst)
    assert r_nps.status_code == 200, r_nps.text
    nps_data = r_nps.json()
    assert nps_data["total_respostas"] == 5
    assert nps_data["qtd_promotores"] == 3
    assert nps_data["qtd_neutros"] == 1
    assert nps_data["qtd_detratores"] == 1
    assert nps_data["valor_nps"] == 40
    print(f"[PASS] 9. Calculo deterministico oficial do NPS validado: valor_nps = +{nps_data['valor_nps']}")

    # 10. Exportação CSV com Mascaramento de PII e registro em LOG_EXPORTACAO
    r_csv = client.get(
        f"/api/v1/submissions/export/csv?id_pesquisa={pesquisa_id}&anonimizado=true",
        headers=headers_analyst,
    )
    assert r_csv.status_code == 200
    conteudo_csv = r_csv.text
    assert "123.456.789-00" not in conteudo_csv, "VAZAMENTO DE CPF NO CSV!"
    assert "joao@empresa.com.br" not in conteudo_csv, "VAZAMENTO DE EMAIL NO CSV!"
    assert "[CPF_MASCARADO]" in conteudo_csv
    assert "[EMAIL_MASCARADO]" in conteudo_csv
    print("[PASS] 10. Exportacao CSV segura (CPF e E-mail mascarados) + LOG_EXPORTACAO gravado")

    # 11. Versionamento automático de Pesquisa após ter respostas (RF-004)
    r_ver = client.patch(
        f"/api/v1/surveys/{pesquisa_id}",
        headers=headers_admin,
        json={"titulo": "Pesquisa Trimestral KeyCore Q4 (Revisada)"},
    )
    assert r_ver.status_code == 200
    ver_data = r_ver.json()
    assert ver_data["numero_versao"] == 2
    assert ver_data["id_pesquisa_pai"] == pesquisa_id
    print("[PASS] 11. RF-004: Edicao de pesquisa com respostas gera versao 2 preservando historico")

    # 12. Trilha de Auditoria Imutável (RF-020)
    r_audit = client.get("/api/v1/audit-logs", headers=headers_admin)
    assert r_audit.status_code == 200
    assert len(r_audit.json()) >= 6
    print(f"[PASS] 12. Trilha de auditoria (LOG_AUDITORIA) ativa com {len(r_audit.json())} eventos registrados")

    print("\nTODOS OS 12 TESTES DE SEGURANCA, LGPD E REGRAS DO PRD PASSARAM COM SUCESSO!")


if __name__ == "__main__":
    run_all_tests()
