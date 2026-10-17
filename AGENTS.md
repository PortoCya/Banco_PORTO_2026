# AGENTS.md

Plataforma de pesquisa de satisfação/NPS da KeyCore. ADMIN cria e publica pesquisas, cliente responde pelo celular sem login, NPS é calculado automaticamente e toda ação é auditada. Uma camada de IA opcional sugere sentimento e tema dos comentários.

> O código atual em `app/` (modelos como `Conversa`, `SoaIa`, `Gerenciacao`...) é de uma versão anterior e **não segue esta especificação**. Em caso de conflito, este arquivo é a fonte da verdade.

## Regra de ouro

**Núcleo** (coleta, NPS, auditoria, LGPD) e **camada de IA** são isolados. Nenhuma falha, atraso ou saída da IA pode impedir, atrasar ou alterar a coleta de respostas ou o NPS. A IA só sugere; nunca altera nota, faixa ou NPS.

## Stack

- **Front:** Next.js + TypeScript (página pública SSR + painéis ADMIN/ANALYST). Tipos gerados via `openapi-typescript` + `openapi-fetch` (`npm run sync-types`).
- **API principal:** Python + FastAPI, rotas sob `/api/v1`, JWT.
- **Worker de IA:** Python, processo separado. Fala com a API só via fila e banco.
- **Banco:** PostgreSQL + SQLAlchemy 2.0 + Alembic (toda mudança de schema = migration).
- **Fila:** Redis Streams (só trafega `id_submissao`, nunca texto). Redis também guarda limite por IP e contador de custo.
- **Validação:** Pydantic (entrada da API e saída da IA).
- **Provedor de IA:** terceiro (OpenAI/Anthropic/Gemini) atrás de um adaptador único.
- **Ambiente:** Docker Compose.

Nomes de campos na API = nomes das colunas no banco (sem tradução). Código e nomes em português.

## Papéis

- `ADMIN`: usuários, pesquisas (criar/publicar/pausar/arquivar), links, auditoria, export identificado, gestão da IA.
- `ANALYST`: NPS, histórico, export **anonimizado**, revisar/descartar sugestões da IA.
- `RESPONDENT`: público, sem login, só `GET/POST /public/respostas/{token}`.

## Autenticação e segurança

Já implementado. Reutilize, não reescreva:

- **Rotas protegidas:** `Depends(get_usuario_atual)` ou `Depends(requer_papel("ADMIN"))` de `app/api/deps.py`. Toda rota não pública precisa de um dos dois; esconder botão no front não é controle de acesso.
- **Senha:** só via `gerar_hash_senha`/`verificar_senha` (`app/core/security.py`, Argon2id). Senha de 12 a 128 caracteres. Nunca retornar `senha_hash` em resposta nem em auditoria.
- **JWT:** HS256, `sub` = uuid do usuário, expira em `ACCESS_TOKEN_EXPIRE_MINUTES`. Papel e `ativo` são lidos do banco a cada requisição (desativar ou trocar papel vale na hora).
- **Login:** erro sempre genérico ("E-mail ou senha inválidos."), sem revelar se o e-mail existe. Rate limit por IP e por e-mail (`app/core/rate_limit.py`, em memória; migrar para Redis mantendo a interface).
- **Auditoria:** ação administrativa chama `registrar_auditoria(...)` (`app/services/auditoria.py`) antes do `commit`, na mesma transação.
- **Segredos:** só por variável de ambiente (`.env`, ignorado pelo git). `SECRET_KEY` não tem padrão: sem ela a app não sobe.
- **Logs:** nunca logar senha, token, hash ou o `input` de erros de validação.
- **SQL:** sempre via ORM/parâmetros; nunca f-string em `text()`.
- **Chamadas externas:** sempre com timeout explícito.
- **Primeiro ADMIN:** `ADMIN_EMAIL` e `ADMIN_SENHA` no `.env` + `python seed_db.py`.

## Regras do núcleo

- **NPS** = %promotores (9–10) − %detratores (0–6). Neutros (7–8) só contam no total. Inteiro de −100 a +100, arredondamento meio para cima. Sem respostas → `valor_nps: null`, `status: "sem_dados_suficientes"` (nunca 0). Lógica em serviço de domínio, fora das rotas.
- Só submissões `VALIDA` entram no NPS. Guardar só a nota; a faixa é calculada na hora.
- Gravar `SUBMISSAO` + `LINK_PESQUISA.usado_em` + atualizar `SNAPSHOT_NPS` na **mesma transação**. Responder 201 sem esperar a IA.
- **Duplicidade:** link `NOMINAL` = token de uso único; link `ABERTO` = cookie HttpOnly 24h + rate limit por IP (Redis). `chave_idempotencia` única. Duplicada → grava `BLOQUEADA_DUPLICADA`, retorna 409 sem dizer qual regra barrou.
- **Versionamento:** editar pesquisa que já tem respostas cria nova `PESQUISA` com `id_pesquisa_pai`; nunca sobrescreve.
- **Auditoria:** toda ação administrativa grava `LOG_AUDITORIA` com `estado_antes`/`estado_depois`. Toda exportação grava `LOG_EXPORTACAO`.
- **LGPD:** só ADMIN exporta dados identificados; ANALYST recebe anonimizado.

## Camada de IA

Fluxo: API grava resposta → se comentário não vazio, cria `JOB_IA` (`NA_FILA`) e publica `id_submissao` → worker mascara PII → chama provedor com a `VERSAO_MODELO` ativa → valida com Pydantic → grava nova linha em `ANALISE_FEEDBACK`.

- **Saída do modelo (JSON):** `sentimento` (`POSITIVO|NEUTRO|NEGATIVO`), `tema` (lista fechada: `atendimento, preco, produto, prazo, usabilidade, outro`), `confianca` (0–1), `justificativa` curta.
- **PII (obrigatório, antes de qualquer envio):** mascarar CPF, e-mail e telefone (regex + NER). Falhou/incerto → não envia, marca `SUBMISSAO.status_mascaramento_pii = FALHA_MASCARAMENTO_PII`, análise fica `PENDENTE`. Varrer também a resposta da IA. O original permanece íntegro no banco.
- **Prompt:** comentário delimitado como dado, nunca como instrução (anti prompt injection). Máx. 2.000 caracteres. Prompts versionados na tabela `PROMPT`; cada análise registra `id_versao_modelo`.
- Comentário vazio → não chama a IA.
- Confiança < 0,6 → `BAIXA_CONFIANCA`, fora das contagens.
- Reanálise → nova linha com `sequencia_versao` maior; API mostra sempre a mais recente.
- UI sempre rotula como "análise sugerida". ANALYST pode descartar (`DESCARTADA_MANUAL`) ou corrigir.
- Nunca usar comentários para treinar/ajustar modelos.

### Falhas → estado (nunca erro propagado ao núcleo)

| Situação | Estado |
|---|---|
| Timeout/5xx do provedor | `JOB_IA` → `TENTANDO_NOVAMENTE` (backoff exponencial); após máx. tentativas → `FALHOU` |
| JSON fora do schema | `ANALISE_FEEDBACK.status = FALHA_SCHEMA` |
| Orçamento estourado | abre `EVENTO_CIRCUIT_BREAKER` (pausa envios enquanto `resolvido_em` é nulo) |
| Falha ao mascarar PII | `FALHA_MASCARAMENTO_PII`, texto não sai |
| Modelo reprovado | `POST /modelos-ia/{id}/ativar` → 409, mantém versão anterior |

### Golden set (gate de ativação de modelo)

100 comentários rotulados (`COMENTARIO_GOLDEN_SET`). Uma `VERSAO_MODELO` só pode ficar `ativo = true` se a última `AVALIACAO_GOLDEN_SET` for `APROVADO`:
- acurácia de sentimento ≥ 80%
- acurácia de tema ≥ 70%
- falso positivo (negativo → positivo) ≤ 5%
- queda > 5 p.p. em qualquer métrica vs. versão anterior bloqueia

### Isolamento garantido

API e worker em processos distintos; o usuário de banco do worker só tem permissão de escrita nas tabelas de IA.

## Tabelas

**Núcleo:** `USUARIO`, `PESQUISA` (status `RASCUNHO|PUBLICADA|PAUSADA|ARQUIVADA`), `LINK_PESQUISA` (`NOMINAL|ABERTO`), `SUBMISSAO` (`VALIDA|BLOQUEADA_DUPLICADA`; `NAO_APLICAVEL|MASCARADO|FALHA_MASCARAMENTO_PII`), `SNAPSHOT_NPS`, `LOG_AUDITORIA`, `LOG_EXPORTACAO`.

**IA:** `ANALISE_FEEDBACK` (`PENDENTE|CONCLUIDA|FALHA_SCHEMA|DESCARTADA_MANUAL|BAIXA_CONFIANCA`), `JOB_IA` (`NA_FILA|PROCESSANDO|CONCLUIDO|FALHOU|TENTANDO_NOVAMENTE`), `VERSAO_MODELO`, `PROMPT`.

**Golden set:** `COMENTARIO_GOLDEN_SET`, `ROTULO_GOLDEN_SET`, `AVALIACAO_GOLDEN_SET` (`APROVADO|REPROVADO`).

**Operacionais (sem FK):** `EVENTO_CIRCUIT_BREAKER`, `SNAPSHOT_TELEMETRIA`.

Todas as PKs são `uuid`.

## Endpoints (`/api/v1`)

| Método | Rota | Acesso |
|---|---|---|
| POST | `/auth/login` | público |
| POST | `/usuarios` | ADMIN |
| POST | `/pesquisas` · PATCH `/pesquisas/{id}` | ADMIN |
| POST | `/pesquisas/{id}/publicar` · `/pausar` · `/arquivar` · `/links` | ADMIN |
| GET/POST | `/public/respostas/{token}` | público |
| GET | `/pesquisas/{id}/nps` · `/nps/historico` | ANALYST/ADMIN |
| GET | `/pesquisas/{id}/exportacao` | ANALYST/ADMIN |
| GET | `/pesquisas/{id}/analises-feedback` | ANALYST/ADMIN |
| PATCH | `/analises-feedback/{id}` | ANALYST |
| GET | `/modelos-ia` · POST `/modelos-ia/{id}/ativar` | ADMIN |
| GET/POST | `/golden-set/avaliacoes` | ADMIN |
| PUT | `/ia/limite-custo` · GET `/ia/circuit-breaker/eventos` · GET `/ia/telemetria` | ADMIN |
| GET | `/log-auditoria` | ADMIN |

**Códigos:** 422 validação (nada gravado) · 409 token usado/duplicado · 403 pesquisa não publicada ou papel insuficiente · 401 sem login · 429 excesso por IP.

## Fora de escopo

Resumo automático de ciclo, clustering de comentários, multi-tenant, integração CRM, app nativo, IA respondendo ao cliente, tradução, modelo self-hosted, qualquer IA alterando nota/NPS.

## Testes

pytest. Obrigatório cobrir: cálculo de NPS (só promotores, só detratores, só neutros, 1 resposta, 0 respostas), duplicidade, mascaramento de PII em vários formatos, casos adversariais de prompt injection e falha do provedor sem impacto no NPS.
