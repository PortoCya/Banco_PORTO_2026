# NPS KeyCore — Backend

Plataforma de pesquisa de satisfação/NPS: o ADMIN cria e publica pesquisas, o
cliente responde pelo celular sem login, o NPS é calculado automaticamente e
toda ação é auditada. Uma camada de IA opcional sugere sentimento e tema dos
comentários.

A especificação completa (regras de negócio, tabelas, endpoints) está em
[`AGENTS.md`](AGENTS.md). Guia de plantão: [`docs/OPERACAO.md`](docs/OPERACAO.md).
Migrations: [`alembic/README.md`](alembic/README.md).

> **Regra de ouro:** núcleo (coleta, NPS, auditoria, LGPD) e camada de IA são
> isolados. A API nunca chama o provedor de IA; quem chama é o worker, em outro
> processo e com outro usuário de banco. Nenhuma falha da IA impede, atrasa ou
> altera a coleta de respostas ou o NPS.

## Arquitetura

```
Front (Next.js) ──HTTP──▶ API (FastAPI) ──▶ PostgreSQL ◀── Worker de IA ──HTTPS──▶ provedor
                             │                 ▲                 ▲
                             └── Redis Streams ┴─(só ids)────────┘
```

| Pasta | O que tem |
|---|---|
| `main.py` | App FastAPI, CORS, health checks |
| `app/core/` | Configuração, banco (pool + timeouts), segurança (Argon2id, JWT), rate limit, logs com request id, erros, middleware |
| `app/models/` · `app/schemas/` | Modelos SQLAlchemy 2.0 (16 tabelas) e schemas Pydantic (entrada estrita) |
| `app/services/` | Regras de domínio: NPS, registro de respostas (transação única), auditoria, PII, golden set, custo |
| `app/api/v1/endpoints/` | Rotas, todas sob `/api/v1` |
| `app/ia/` | Worker (`python -m app.ia.worker`), adaptador do provedor, prompt e validação da saída |
| `alembic/` | Migrations versionadas |
| `scripts/` | Backup, teste de restore, permissões do usuário de banco do worker |
| `tests/` | pytest |
| `frontend/` | Next.js: login, painel ADMIN de pesquisas e página pública de resposta |
| `dashboard/` | Painel de análise (Streamlit) para ANALYST/ADMIN, lendo da API |

## Rodando em desenvolvimento

### Atalho rápido no Windows (`rodar.bat`)

Depois de configurar o ambiente virtual (`venv`), instalar as dependências do `frontend/` (`npm ci`) e preencher o `.env`, basta executar:

```powershell
.\rodar.bat
```

O menu interativo do `rodar.bat` aplica as migrations (`alembic upgrade head`), garante o seed de demonstração (`seed_db.py --demo`), libera as portas e permite subir:
- **`[1]`** Tudo de uma vez: API (`:8000`) + Frontend Next.js (`:3000`) + Dashboard Streamlit (`:8501`) + Worker de IA
- **`[2]`** API (`:8000`) + Frontend Next.js (`:3000`)
- **`[3]`** Apenas API Backend (`:8000`)
- **`[4]`** API (`:8000`) + Dashboard Streamlit (`:8501`)
- **`[5]`** Worker de IA (`python -m app.ia.worker`)
- **`[6]`** Suíte de testes (`pytest`)
- **`[0]`** Fechar todas as portas (`fechar_portas.bat`)

### Passo a passo manual

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env
# Edite o .env:
#   SECRET_KEY   → openssl rand -hex 32
#   ADMIN_EMAIL / ADMIN_SENHA (12 a 128 caracteres) → primeiro ADMIN

alembic upgrade head            # cria o schema (SQLite por padrão)
python seed_db.py --demo        # primeiro ADMIN + pesquisa de demonstração (imprime o token do link)
uvicorn main:app --reload --port 8000
```

- Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health> (consulta o banco; 503 se ele cair)

Não existe usuário nem senha padrão: as credenciais do primeiro ADMIN são as
que você colocou no seu `.env`.

### Stack completa (PostgreSQL + Redis + worker)

```bash
cp .env.example .env    # preencha também POSTGRES_PASSWORD, WORKER_DB_PASSWORD e IA_API_KEY
docker compose up --build
docker compose run --rm api python seed_db.py --demo
```

Sem Docker: suba um PostgreSQL e um Redis, aponte `DATABASE_URL`/`REDIS_URL`,
rode `alembic upgrade head`, `scripts/permissoes_worker.sql` e, em outro
terminal, `python -m app.ia.worker`.

## Front (Next.js) e dashboard

Os dois só falam com a API — nada de banco ou provedor de IA direto.

```bash
# Front: login, /admin/pesquisas (ADMIN) e /pesquisa/{token} (respondente, sem login)
cd frontend && cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm ci && npm run dev                              # http://localhost:3000

# Dashboard de análise (ANALYST ou ADMIN)
pip install -r requirements-dashboard.txt
NPS_API_URL=http://localhost:8000 streamlit run dashboard/nps_dashboard.py
```

- A API precisa liberar a origem do front: `CORS_ORIGINS=http://localhost:3000`.
- Em desenvolvimento sem HTTPS use `COOKIE_SECURE=false` (senão o cookie do link aberto não é gravado).
- O NPS exibido vem da API. A análise sugerida (sentimento e tema) é feita pelo worker de IA; o dashboard só mostra.

## Testes

```bash
pytest                                                             # SQLite em memória
TEST_DATABASE_URL=postgresql+psycopg://user:senha@localhost/nps_test pytest   # mesma suíte em PostgreSQL
```

Os testes de corrida (`tests/test_concorrencia.py`) só rodam em PostgreSQL.
O banco apontado por `TEST_DATABASE_URL` é **apagado e recriado** a cada teste.

## Endpoints (`/api/v1`)

| Método | Rota | Acesso |
|---|---|---|
| POST | `/auth/login` | público (rate limit por IP e por e-mail) |
| GET | `/auth/me` | autenticado |
| POST/GET | `/usuarios` · GET/PATCH/DELETE `/usuarios/{id}` | ADMIN |
| POST | `/pesquisas` · PATCH/DELETE `/pesquisas/{id}` | ADMIN |
| GET | `/pesquisas` · `/pesquisas/{id}` | ANALYST/ADMIN |
| POST | `/pesquisas/{id}/publicar` · `/pausar` · `/arquivar` | ADMIN |
| POST/GET | `/pesquisas/{id}/links` · DELETE `/pesquisas/{id}/links/{id_link}` | ADMIN |
| GET/POST | `/public/respostas/{token}` | público (rate limit por IP) |
| GET | `/pesquisas/{id}/nps` · `/nps/historico` | ANALYST/ADMIN |
| GET | `/pesquisas/{id}/respostas` (para os painéis, comentário anonimizado) | ANALYST/ADMIN |
| GET | `/pesquisas/{id}/exportacao` | ANALYST (anonimizado) / ADMIN |
| GET | `/pesquisas/{id}/analises-feedback` · `/analises-feedback/resumo` | ANALYST/ADMIN |
| PATCH | `/analises-feedback/{id}` | ANALYST |
| GET/POST | `/prompts` · `/modelos-ia` · POST `/modelos-ia/{id}/ativar` | ADMIN |
| GET/POST | `/golden-set/comentarios` · `/golden-set/avaliacoes` | ADMIN |
| GET/PUT | `/ia/limite-custo` · GET `/ia/circuit-breaker/eventos` · `/ia/telemetria` | ADMIN |
| GET | `/ia/jobs` · POST `/ia/jobs/{id}/reprocessar` | ADMIN |
| GET | `/log-auditoria` · `/log-exportacao` | ADMIN |

Fora do `/api/v1`: `GET /health` (readiness, confere o banco) e `GET /health/live`.

### Enviando uma resposta

```http
POST /api/v1/public/respostas/{token}
Content-Type: application/json

{"nota_nps": 9, "texto_comentario": "Atendimento rápido", "chave_idempotencia": "<uuid gerado pelo front>"}
```

- `chave_idempotencia`: gere **um uuid por formulário aberto** e reenvie o mesmo valor se a requisição falhar por rede. A mesma chave nunca conta duas vezes — a repetição recebe 409, que o front deve tratar como "já respondido".
- Link `ABERTO`: a resposta grava um cookie HttpOnly de 24h; chame com `credentials: "include"`.

### Erros

Formato único, sempre com o id da requisição (também no cabeçalho `X-Request-ID`):

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Dados de entrada inválidos.", "correlation_id": "…"}}
```

| Código | Quando |
|---|---|
| 401 | sem login ou token inválido/expirado |
| 403 | papel insuficiente ou pesquisa não publicada |
| 404 | não existe |
| 409 | token usado / resposta duplicada / transição inválida / modelo reprovado no golden set |
| 413 | corpo acima de 64 KB |
| 422 | validação (nada é gravado) |
| 429 | excesso por IP, ou servidor saturado (`SERVER_BUSY`) — respeite o `Retry-After` |
| 503 | banco indisponível |

## Decisões que vale conhecer

- **Senhas:** Argon2id. Erro de login sempre genérico. Papel e `ativo` lidos do banco a cada requisição.
- **Entrada:** todo schema rejeita campo desconhecido; ids são `uuid`, filtros são valores fechados, paginação tem teto (`limit ≤ 200`).
- **SQL:** só via ORM/parâmetros. Erros de banco nunca carregam SQL nem dados (`hide_parameters`).
- **Transações:** uma por operação. Resposta do cliente = `SUBMISSAO` + `LINK_PESQUISA.usado_em` + `SNAPSHOT_NPS` (+ `JOB_IA`) no mesmo commit.
- **Banco:** pool de conexões com `pool_pre_ping`, `connect_timeout`, `statement_timeout` e `lock_timeout`.
- **IA:** timeout explícito; só erro transitório (timeout, rede, 429, 5xx) é repetido, com backoff exponencial; PII mascarada antes de qualquer envio; comentário delimitado como dado; saída validada por schema estrito.
- **Logs:** toda linha tem `request_id`; nunca senha, token, hash, corpo de requisição ou token de link público.
