# 🛡️ NPS KeyCore v1.0 — Backend API, Banco de Dados & IA Qualitativa

Plataforma corporativa **NPS KeyCore v1.0** desenvolvida em **Python · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · Google Gemini (Gratuito)**, 100% aderente ao **PRD NPS KeyCore v1.0** e ao **Diagrama Entidade-Relacionamento oficial de 16 tabelas**, pronta para integração com o Frontend (`Next.js`).

---

## 📋 Índice

1. [Como Rodar o Projeto (Passo a Passo)](#-1-como-rodar-o-projeto-passo-a-passo)
2. [Guia Rápido de Integração com o Frontend](#-2-guia-rápido-de-integração-com-o-frontend)
3. [Banco de Dados (16 Tabelas, PKs, FKs, Relacionamentos e IA)](#-3-banco-de-dados-16-tabelas-pks-fks-relacionamentos-e-ia)
4. [API REST — Lista Completa de Endpoints](#-4-api-rest--lista-completa-de-endpoints)
5. [Fluxo Completo (Frontend → API → Banco/IA → Resposta)](#-5-fluxo-completo-frontend--api--bancoia--resposta)
6. [Tratamento de Erros, Segurança e LGPD](#-6-tratamento-de-erros-segurança-e-lgpd)
7. [Suíte de Testes Automatizados (Segurança e PRD)](#-7-suíte-de-testes-automatizados-segurança-e-prd)

---

## 🚀 1. Como Rodar o Projeto (Passo a Passo)

### Pré-requisitos
- **Python 3.11+** instalado
- Chave gratuita do **Google Gemini** (gerada em 30 segundos em [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey))
  *(Obs.: Mesmo sem a chave configurada, todo o núcleo de pesquisas, submissões e cálculo determinístico do NPS funciona normalmente!)*

### Passo 1 — Clonar o repositório
```bash
git clone https://github.com/PortoCya/Banco_PORTO_2026.git
cd Banco_PORTO_2026
```

### Passo 2 — Criar e ativar o ambiente virtual
```bash
# Windows (PowerShell)
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Passo 3 — Instalar as dependências
```bash
pip install -r requirements.txt
```

### Passo 4 — Configurar variáveis de ambiente (`.env`)
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Abra o arquivo `.env` e preencha sua chave gratuita do Gemini:
```env
APP_NAME="NPS KeyCore v1.0"
APP_VERSION="1.0.0"
DEBUG=false

# Banco de dados (SQLite por padrão em dev; PostgreSQL pronto para produção)
DATABASE_URL=sqlite:///./ai_consulting.db
# Exemplo PostgreSQL: DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/nps_keycore

# Segurança (JWT e HMAC de IP)
SECRET_KEY=gere_uma_chave_segura_com_python_secrets_token_hex_32
ACCESS_TOKEN_EXPIRE_MINUTES=60

# IA Qualitativa — Google Gemini (Gratuito)
AI_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy_SUA_CHAVE_AQUI
GEMINI_MODEL=gemini-2.0-flash
```

### Passo 5 — Criar as 16 tabelas e popular dados iniciais (Seed)
```bash
python seed_db.py
```
O comando acima cria o banco e popula automaticamente:
- **Usuário ADMIN:** `admin@keycore.com.br` | Senha: `Admin@KeyCore2026!`
- **Usuário ANALYST:** `analista@keycore.com.br` | Senha: `Analista@KeyCore2026!`
- **Pesquisa ativa publicada:** *"Pesquisa Oficial de Satisfação NPS KeyCore 2026"*
- **Token público aberto para teste:** `nps-keycore-2026`
- **Modelo IA ativo:** `Google Gemini` (`gemini-2.0-flash`) + Prompt oficial + Golden Set

### Passo 6 — Iniciar o servidor da API
```bash
uvicorn main:app --reload --port 8000
```

Acesse no navegador:
- **Swagger UI (Testar endpoints interativamente):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc (Documentação completa):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 💻 2. Guia Rápido de Integração com o Frontend

O CORS já está pré-configurado em `main.py` para aceitar requisições de `http://localhost:3000` (Next.js local) e dos domínios `https://nps.keycore.com.br` / `https://apinps.keycore.com.br`.

### A. Fluxo Público Mobile-First (Respondente — Não exige login)
1. **Carregar a pesquisa ao abrir a URL pública (`/r/[token]`):**
   - `GET http://localhost:8000/api/v1/public/surveys/nps-keycore-2026`
   - Retorna o título, `texto_pergunta_nps`, `texto_pergunta_aberta` e escala `0..10`.
2. **Enviar resposta do cliente:**
   - `POST http://localhost:8000/api/v1/public/submissions`
   ```json
   {
     "token_link": "nps-keycore-2026",
     "nota_nps": 10,
     "texto_comentario": "Excelente plataforma, muito rápida!",
     "chave_idempotencia": "uuid-unico-gerado-no-front-001"
   }
   ```

### B. Fluxo Administrativo (Dashboard Admin / Analyst)
1. **Autenticar (`POST /api/v1/auth/login`):**
   - Envie `{"email": "admin@keycore.com.br", "senha": "Admin@KeyCore2026!"}`.
   - Salve o `access_token` retornado e envie nas próximas chamadas no header:
     `Authorization: Bearer <access_token>`
2. **Carregar Dashboard Geral (`GET /api/v1/analytics/overview`):**
   - Retorna o NPS determinístico (`valor_nps`, `% promotores`, `% neutros`, `% detratores`) e o agregado qualitativo da IA (sentimentos e temas).

---

## 🗄️ 3. Banco de Dados (16 Tabelas, PKs, FKs, Relacionamentos e IA)

### Diagrama Entidade-Relacionamento (Mermaid)

```mermaid
erDiagram
    USUARIO ||--o{ PESQUISA : "cria (criado_por)"
    USUARIO ||--o{ LOG_AUDITORIA : "executa acao"
    USUARIO ||--o{ LOG_EXPORTACAO : "solicita export"
    USUARIO ||--o{ ROTULO_GOLDEN_SET : "rotula"

    PESQUISA ||--o{ PESQUISA : "gera nova versao (id_pesquisa_pai)"
    PESQUISA ||--o{ LINK_PESQUISA : "possui"
    PESQUISA ||--o{ SUBMISSAO : "recebe"
    PESQUISA ||--o{ SNAPSHOT_NPS : "resume"
    PESQUISA ||--o{ LOG_EXPORTACAO : "origem"

    LINK_PESQUISA ||--o{ SUBMISSAO : "origina"

    SUBMISSAO ||--o{ JOB_IA : "processada em"
    SUBMISSAO ||--o{ ANALISE_FEEDBACK : "analisada por (versionada)"

    PROMPT ||--o{ VERSAO_MODELO : "usa"
    VERSAO_MODELO ||--o{ AVALIACAO_GOLDEN_SET : "avaliada em"
    VERSAO_MODELO ||--o{ ANALISE_FEEDBACK : "produz"

    COMENTARIO_GOLDEN_SET ||--o{ ROTULO_GOLDEN_SET : "rotulagem dupla + desempate"
```

### Detalhamento das 16 Entidades (`app/models/models.py`)

| # | Tabela | Chave Primária (PK) | Chaves Estrangeiras (FK) | UK / Constraints | Atributos e Papel |
|---|---|---|---|---|---|
| 1 | `usuario` | `id` (UUID) | — | `email` (UK) | `nome`, `email`, `senha_hash` (PBKDF2), `papel` (`ADMIN`\|`ANALYST`), `ativo`, `criado_em` |
| 2 | `pesquisa` | `id` (UUID) | `id_pesquisa_pai` → `pesquisa.id`, `criado_por` → `usuario.id` | — | `titulo`, `texto_pergunta_nps`, `texto_pergunta_aberta`, `status` (`RASCUNHO`\|`PUBLICADA`\|`PAUSADA`\|`ARQUIVADA`), `numero_versao`, `criada_em`, `atualizada_em` |
| 3 | `link_pesquisa` | `id` (UUID) | `id_pesquisa` → `pesquisa.id` | `token` (UK) | `tipo` (`NOMINAL`\|`ABERTO`), `token`, `usado_em` (nulo até 1ª submissão), `criado_em` |
| 4 | `submissao` | `id` (UUID) | `id_pesquisa` → `pesquisa.id`, `id_link_pesquisa` → `link_pesquisa.id` | `chave_idempotencia` (UK), `CHECK(nota_nps 0..10)` | `nota_nps` (dado primário), `texto_comentario`, `fingerprint_dispositivo`, `endereco_ip` (hash SHA-256), `status`, `status_mascaramento_pii`, `criada_em` |
| 5 | `snapshot_nps` | `id` (UUID) | `id_pesquisa` → `pesquisa.id` | `CHECK(valor_nps -100..100)` | `periodo_inicio`, `periodo_fim`, `valor_nps`, `total_respostas`, `qtd_promotores`, `qtd_neutros`, `qtd_detratores`, `calculado_em` |
| 6 | `prompt` | `id` (UUID) | — | — | `objetivo`, `contexto`, `saida_esperada`, `problemas_encontrados`, `criado_em` |
| 7 | `versao_modelo` | `id` (UUID) | `id_prompt` → `prompt.id` | `rotulo_versao` (UK) | `provedor`, `nome_modelo`, `rotulo_versao`, `ativa`, `promovida_em` |
| 8 | `job_ia` | `id` (UUID) | `id_submissao` → `submissao.id` | — | `status` (`NA_FILA`\|`PROCESSANDO`\|`CONCLUIDO`\|`FALHOU`\|`TENTANDO_NOVAMENTE`), `tentativas`, `ultimo_erro`, `proxima_tentativa_em`, `criado_em` |
| 9 | `analise_feedback` | `id` (UUID) | `id_submissao` → `submissao.id`, `id_versao_modelo` → `versao_modelo.id` | `CHECK(confianca 0..1)` | `sentimento` (`POSITIVO`\|`NEUTRO`\|`NEGATIVO`), `tema` (taxonomia fechada), `confianca`, `justificativa`, `sequencia_versao`, `status`, `criada_em`, `atualizada_em` |
| 10 | `avaliacao_golden_set` | `id` (UUID) | `id_versao_modelo` → `versao_modelo.id` | — | `acuracia_sentimento`, `acuracia_tema`, `taxa_falso_positivo`, `status` (`APROVADO`\|`REPROVADO`), `executada_em` |
| 11 | `comentario_golden_set` | `id` (UUID) | — | — | `texto_comentario`, `rotulo_sentimento_humano`, `rotulo_tema_humano`, `criado_em` |
| 12 | `rotulo_golden_set` | `id` (UUID) | `id_comentario_golden_set` → `comentario_golden_set.id`, `rotulado_por` → `usuario.id` | — | `eh_desempate`, `rotulo_sentimento`, `rotulo_tema` |
| 13 | `log_auditoria` | `id` (UUID) | `id_usuario_ator` → `usuario.id` | — | `acao`, `tipo_entidade`, `id_entidade`, `estado_antes` (JSON), `estado_depois` (JSON), `criado_em` |
| 14 | `log_exportacao` | `id` (UUID) | `id_analista` → `usuario.id`, `id_pesquisa` → `pesquisa.id` | — | `campos_exportados`, `anonimizado`, `criado_em` |
| 15 | `evento_circuit_breaker` | `id` (UUID) | — | — | `motivo`, `custo_acumulado`, `limite_custo`, `disparado_em`, `resolvido_em` |
| 16 | `snapshot_telemetria` | `id` (UUID) | — | — | `inicio_janela`, `fim_janela`, `latencia_p50_ms`, `latencia_p95_ms`, `taxa_erro_5xx`, `pct_descartado_ec12`, `pct_descartado_ec13`, `qtd_pii_mascaramento_falhou`, `status_circuit_breaker` |

---

## 🌐 4. API REST — Lista Completa de Endpoints

**Prefixo Base:** `/api/v1`

| Categoria | Método | Endpoint | Papel Exigido | Recebe | Retorna | Códigos HTTP |
|---|---|---|---|---|---|---|
| **Health** | `GET` | `/health` | Público | — | Status da aplicação e provedor IA | `200` |
| **Auth** | `POST` | `/api/v1/auth/login` | Público | `{email, senha}` | `{access_token, papel, expires_in_minutes}` | `200`, `401`, `422`, `429` |
| **Auth** | `POST` | `/api/v1/auth/logout` | Autenticado | Header `Bearer` | Confirmação de revogação do token | `200`, `401` |
| **Auth** | `GET` | `/api/v1/auth/me` | Autenticado | Header `Bearer` | Dados do usuário logado (sem `senha_hash`) | `200`, `401` |
| **Usuários** | `POST` | `/api/v1/usuarios` | `ADMIN` | `{nome, email, senha, papel}` | Usuário criado | `201`, `401`, `403`, `409`, `422` |
| **Usuários** | `GET` | `/api/v1/usuarios` | `ADMIN` | `?skip=0&limit=50` | Lista de usuários | `200`, `401`, `403` |
| **Usuários** | `PATCH` | `/api/v1/usuarios/{id}/desativar` | `ADMIN` | `id` no path | Usuário desativado + `LOG_AUDITORIA` | `200`, `401`, `403`, `404` |
| **Surveys** | `POST` | `/api/v1/surveys` | `ADMIN` | `{titulo, texto_pergunta_nps, texto_pergunta_aberta}` | Pesquisa criada (`RASCUNHO`) | `201`, `401`, `403`, `422` |
| **Surveys** | `GET` | `/api/v1/surveys` | `ADMIN`, `ANALYST` | `?status_filtro` | Lista de pesquisas | `200`, `401`, `403` |
| **Surveys** | `GET` | `/api/v1/surveys/{id}` | `ADMIN`, `ANALYST` | `id` no path | Detalhes da pesquisa | `200`, `401`, `403`, `404` |
| **Surveys** | `PATCH` | `/api/v1/surveys/{id}` | `ADMIN` | Campos atualizados | Atualiza ou cria `numero_versao + 1` se já houver respostas (RF-004) | `200`, `401`, `403`, `404` |
| **Surveys** | `POST` | `/api/v1/surveys/{id}/status/{status}` | `ADMIN` | `PUBLICADA\|PAUSADA\|ARQUIVADA` | Pesquisa atualizada + `LOG_AUDITORIA` | `200`, `400`, `403`, `404` |
| **Links** | `POST` | `/api/v1/surveys/{id}/links` | `ADMIN` | `{tipo: NOMINAL\|ABERTO, token_customizado}` | Link/convite criado | `201`, `403`, `404`, `409` |
| **Links** | `GET` | `/api/v1/surveys/{id}/links` | `ADMIN`, `ANALYST` | `id` no path | Lista de links da pesquisa | `200`, `401`, `403` |
| **Público** | `GET` | `/api/v1/public/surveys/{token}` | Público | `token` no path | Perguntas da pesquisa ativa | `200`, `400`, `404`, `409`, `429` |
| **Público** | `POST` | `/api/v1/public/submissions` | Público | `{token_link, nota_nps, texto_comentario, chave_idempotencia}` | Submissão criada + agenda `JOB_IA` | `201`, `400`, `404`, `409`, `422`, `429` |
| **Submissões** | `GET` | `/api/v1/submissions` | `ADMIN`, `ANALYST` | `?id_pesquisa&classificacao&busca` | Lista de submissões com PII mascarado | `200`, `401`, `403` |
| **Export CSV** | `GET` | `/api/v1/submissions/export/csv` | `ADMIN`, `ANALYST` | `?id_pesquisa&anonimizado=true` | Download CSV + grava `LOG_EXPORTACAO` | `200`, `401`, `403`, `404` |
| **Analytics** | `GET` | `/api/v1/analytics/overview` | `ADMIN`, `ANALYST` | `?data_inicio&data_fim` | NPS determinístico global + resumo IA | `200`, `401`, `403` |
| **Analytics** | `GET` | `/api/v1/analytics/surveys/{id}` | `ADMIN`, `ANALYST` | `?periodo_inicio&periodo_fim` | Calcula NPS e grava `SNAPSHOT_NPS` | `200`, `401`, `403`, `404` |
| **Analytics** | `GET` | `/api/v1/analytics/surveys/{id}/historico` | `ADMIN`, `ANALYST` | `id` no path | Série histórica de `SNAPSHOT_NPS` | `200`, `401`, `403` |
| **IA** | `POST` | `/api/v1/prompts` | `ADMIN` | `{objetivo, contexto, saida_esperada}` | Prompt criado | `201`, `401`, `403`, `422` |
| **IA** | `POST` | `/api/v1/versoes-modelo` | `ADMIN` | `{provedor, nome_modelo, rotulo_versao, id_prompt}` | Versão de modelo registrada | `201`, `401`, `403`, `409` |
| **IA** | `GET` | `/api/v1/ia/jobs` | `ADMIN`, `ANALYST` | `?status_filtro` | Fila de `JOB_IA` | `200`, `401`, `403` |
| **IA** | `POST` | `/api/v1/ia/jobs/{job_id}/reprocessar` | `ADMIN`, `ANALYST` | `job_id` no path | Reprocessa e gera nova `sequencia_versao` | `200`, `401`, `403`, `404` |
| **IA** | `GET` | `/api/v1/ia/analises-feedback` | `ADMIN`, `ANALYST` | `?id_submissao&sentimento&tema` | Lista de `ANALISE_FEEDBACK` | `200`, `401`, `403` |
| **Auditoria** | `GET` | `/api/v1/audit-logs` | `ADMIN` | `?acao&tipo_entidade` | Trilha imutável `LOG_AUDITORIA` | `200`, `401`, `403` |
| **Auditoria** | `GET` | `/api/v1/export-logs` | `ADMIN` | — | Histórico de exportações CSV (`LOG_EXPORTACAO`) | `200`, `401`, `403` |

---

## 🔄 5. Fluxo Completo (Frontend → API → Banco/IA → Resposta)

```mermaid
sequenceDiagram
    autonumber
    actor R as Frontend (Respondente Mobile)
    participant API as FastAPI (/api/v1/public/submissions)
    participant SEC as Segurança & LGPD (security.py)
    participant DB as Banco de Dados (SQLite / PostgreSQL)
    participant BG as Worker Assíncrono (JobIa)
    participant AI as Google Gemini (gemini-2.0-flash)

    R->>API: POST /public/submissions {token_link, nota_nps, texto_comentario, chave_idempotencia}
    API->>SEC: Valida Rate Limit, Tamanho do Payload (<=64KB), DTO estrito e Sanitiza XSS
    API->>DB: Verifica LinkPesquisa, Pesquisa == PUBLICADA, chave_idempotencia única e uso único se NOMINAL
    API->>SEC: Pseudonimiza IP (HMAC-SHA256) + Avalia Mascaramento de PII (CPF/Email/Telefone)
    API->>DB: Transação Única: INSERT SUBMISSAO + UPDATE LINK_PESQUISA.usado_em + INSERT JOB_IA (NA_FILA)
    API-->>R: 201 Created (Submissão persistida e classificada deterministicamente!)

    par Processamento Qualitativo Assíncrono (Desacoplado do cálculo de NPS)
        API-)BG: Agenda processar_job_ia_background(job_id)
        BG->>DB: Verifica se EVENTO_CIRCUIT_BREAKER está fechado
        BG->>SEC: Aplica mascarar_pii(texto_comentario) — aborta se FALHA_MASCARAMENTO_PII
        BG->>AI: Envia comentário sem PII para Gemini 2.0 Flash
        alt Sucesso na IA
            AI-->>BG: JSON {sentimento, tema, confianca, justificativa}
            BG->>DB: INSERT ANALISE_FEEDBACK (sequencia_versao + 1) & UPDATE JOB_IA = CONCLUIDO
        else Falha / Timeout / Sem chave
            AI-->>BG: Erro / Timeout
            BG->>DB: UPDATE JOB_IA = TENTANDO_NOVAMENTE (Submissão original permanece 100% intacta!)
        end
    end
```

---

## 🛡️ 6. Tratamento de Erros, Segurança e LGPD

Todas as respostas de erro seguem o contrato padronizado:
```json
{
  "error": {
    "code": "CODIGO_DO_ERRO",
    "message": "Mensagem clara e segura sem vazar detalhes internos",
    "correlation_id": "uuid-da-requisicao"
  }
}
```

| Cenário | Código HTTP | `error.code` | Camada de Proteção |
|---|---|---|---|
| **Dados inválidos / Nota fora de 0–10 / Mass Assignment** | `422` | `VALIDATION_ERROR` | Pydantic `StrictInputModel` (`extra="forbid"`) + `CheckConstraint` |
| **Pesquisa não publicada / Regra de negócio** | `400` | `BUSINESS_RULE_VIOLATION` | Validação determinística antes da persistência |
| **Não autenticado / Token expirado ou revogado** | `401` | `UNAUTHORIZED` | Validação de assinatura HMAC-SHA256 e lista de revogação |
| **Sem permissão para o recurso (RBAC)** | `403` | `FORBIDDEN` | Dependência `require_roles("ADMIN")` no backend |
| **Recurso não encontrado** | `404` | `NOT_FOUND` | Tratamento explícito nas rotas |
| **Duplicidade (`chave_idempotencia` ou token `NOMINAL` já usado)** | `409` | `CONFLICT` | Índices `UNIQUE` + validação transacional |
| **Payload acima de 64 KB** | `413` | `PAYLOAD_TOO_LARGE` | Middleware HTTP de proteção contra DoS |
| **Excesso de requisições (Rate Limit)** | `429` | `RATE_LIMIT_EXCEEDED` | Rate Limiter por hash de IP |
| **Banco de dados indisponível** | `503` | `DATABASE_UNAVAILABLE` | Handler global `OperationalError` (oculta SQL interno) |
| **API externa / IA indisponível ou resposta inesperada** | `502` | `EXTERNAL_API_ERROR` / `AI_ERROR` | Isolado no worker de `JobIa` com retry e Circuit Breaker |
| **Timeout no banco ou na IA** | `504` | `TIMEOUT` / `DATABASE_TIMEOUT` | Timeout configurável (`OPENAI_TIMEOUT_SECONDS=30`) |

---

## 🧪 7. Suíte de Testes Automatizados (Segurança e PRD)

Para rodar os 12 testes automatizados que verificam autenticação, RBAC, proteção contra Mass Assignment, sanitização XSS, mascaramento de PII no CSV, antiduplicidade, versionamento automático de pesquisa e cálculo determinístico do NPS:

```bash
python test_security_and_prd.py
```

Saída esperada:
```text
[PASS] 1. Bloqueio de acesso nao autenticado (401) + Headers de Seguranca HTTP
[PASS] 2. Autenticacao JWT PBKDF2-SHA256 e protecao contra vazamento de senha_hash
[PASS] 3. RBAC no backend: ANALYST bloqueado em operacoes exclusivas de ADMIN (403)
[PASS] 4. Protecao contra Mass Assignment (campos extras rejeitados com 422)
[PASS] 5. Regra de integridade 1: Pesquisa nao-PUBLICADA rejeita submissoes (400)
[PASS] 6. Coleta transacional, sanitizacao contra XSS, mascaramento PII e resiliencia a falha de IA
[PASS] 7. Antiduplicidade por chave_idempotencia (409 Conflict)
[PASS] 8. Token NOMINAL de uso unico bloqueia segunda resposta (409 Conflict)
[PASS] 9. Calculo deterministico oficial do NPS validado: valor_nps = +40
[PASS] 10. Exportacao CSV segura (CPF e E-mail mascarados) + LOG_EXPORTACAO gravado
[PASS] 11. RF-004: Edicao de pesquisa com respostas gera versao 2 preservando historico
[PASS] 12. Trilha de auditoria (LOG_AUDITORIA) ativa com 8 eventos registrados

TODOS OS 12 TESTES DE SEGURANCA, LGPD E REGRAS DO PRD PASSARAM COM SUCESSO!
```
