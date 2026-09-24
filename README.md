# 🤖 AI Consulting Platform — Banco_PORTO_2026

Plataforma de consultoria com Inteligência Artificial construída com **Python · FastAPI · SQLAlchemy · Pydantic v2 · OpenAI**.

Baseado em modelagem relacional completa com 16 entidades, endpoints RESTful, orquestração de IA (SOA_IA), análise de sentimento e tratamento robusto de erros.

---

## 📋 Índice

- [Arquitetura](#arquitetura)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Rodando o projeto](#rodando-o-projeto)
- [Banco de dados](#banco-de-dados)
- [API — Endpoints](#api--endpoints)
- [Fluxo de funcionamento](#fluxo-de-funcionamento)
- [Tratamento de erros](#tratamento-de-erros)
- [Estrutura de pastas](#estrutura-de-pastas)
- [Estruturas de IA](#estruturas-de-ia)

---

## Arquitetura

```
Frontend  →  FastAPI (REST)  →  SQLAlchemy ORM  →  SQLite / PostgreSQL
                    ↓
              OpenAI API  (gpt-4o)
                    ↓
           Análise de Feedback (background)
```

**Stack:**
| Camada | Tecnologia |
|---|---|
| Framework Web | FastAPI 0.111+ |
| ORM | SQLAlchemy 2.0 |
| Validação | Pydantic v2 |
| IA | OpenAI SDK (gpt-4o) |
| Banco (dev) | SQLite |
| Banco (prod) | PostgreSQL |
| Servidor ASGI | Uvicorn |

---

## Pré-requisitos

- **Python 3.11+**
- **pip**
- Conta na [OpenAI](https://platform.openai.com/) com API Key (para usar os endpoints de IA)
- *(Opcional)* PostgreSQL para ambiente de produção

---

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/PortoCya/Banco_PORTO_2026.git
cd Banco_PORTO_2026
```

### 2. Crie o ambiente virtual

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

---

## Configuração

### 4. Copie o arquivo de variáveis de ambiente

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

### 5. Edite o `.env` com suas configurações

```env
# Banco de dados
DATABASE_URL=sqlite:///./ai_consulting.db
# Para PostgreSQL: postgresql+psycopg2://user:senha@localhost:5432/ai_consulting

# IA — OpenAI (obrigatório para endpoints de IA)
OPENAI_API_KEY=sk-...

# Segurança
SECRET_KEY=gere_uma_chave_segura_aqui
```

> **Gerar SECRET_KEY segura:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Rodando o projeto

### 6. Criar tabelas e dados iniciais

```bash
python seed_db.py
```

Saída esperada:
```
INFO: Criando tabelas...
INFO: Tabelas criadas.
INFO: Dados iniciais inseridos com sucesso.
```

Isso cria automaticamente:
- 16 tabelas no banco
- Modelo de IA padrão (`gpt-4o`)
- Tutor base e prompt do sistema
- Usuário admin (`admin@consultoria.ai`)

### 7. Iniciar o servidor

```bash
# Desenvolvimento (com reload automático)
uvicorn main:app --reload --port 8000

# Produção
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 8. Acessar a documentação interativa

| Interface | URL |
|---|---|
| **Swagger UI** (interativo) | http://localhost:8000/docs |
| **ReDoc** (documentação) | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |

---

## Banco de Dados

### Diagrama de Entidades (ER)

```
VIDEO_MODELO ──────────── TUTOR_CIRCUITO_TREINADO
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
          AVALIACAO_CIRCUITO    PROMPT    CONFIGURAR_CIRCUITO_SET
                                                    │
                                          TEMPLATE_ELEMENTOS

USUARIO ──┬──── CONVERSA ──── LOA_PUNICAO ──── MATRIZ_PUNICAO_SET
          │
          └──── GERENCIACAO ──┬── SOA_IA
                              ├── LINHA_RACIOCINIO
                              ├── DIMENSOES_KPIS
                              ├── LOG_DIRECIONAR
                              └── ANALISE_FEEDBACK ──── VIDEO_MODELO
```

### 16 Entidades

| # | Tabela | Descrição |
|---|---|---|
| 1 | `video_modelo` | Registro dos LLMs (OpenAI, Anthropic…) |
| 2 | `tutor_circuito_treinado` | Circuito de treinamento do tutor IA |
| 3 | `template_elementos` | Templates de resposta |
| 4 | `avaliacao_circuito_set` | Avaliações de benchmark do circuito |
| 5 | `prompt` | Engenharia de prompts do sistema |
| 6 | `configurar_circuito_set` | Configuração fina do circuito |
| 7 | `usuario` | Usuários (ADMIN / ANALISTA / PT) |
| 8 | `conversa` | Sessões de conversa com a IA |
| 9 | `loa_punicao` | Atributos e punições de entrada |
| 10 | `matriz_punicao_set` | Matriz de pontuação e relevância |
| 11 | `linha_raciocinio` | Chain-of-Thought da IA (auditoria) |
| 12 | `dimensoes_kpis` | Dimensões e métricas de KPI |
| 13 | `log_direcionar` | Log de redirecionamentos |
| 14 | `gerenciacao` | Hub central de sessões de processamento |
| 15 | `soa_ia` | Orquestrador de chamadas IA (fila/status) |
| 16 | `analise_feedback` | Análise de sentimento gerada pela IA |

### Chaves e Restrições

| Tipo | Detalhes |
|---|---|
| **PK** | UUID v4 (`String(36)`) gerado automaticamente em todas as tabelas |
| **FK** | `CASCADE` em relações pai-filho; `SET NULL` em relações opcionais |
| **UK** | `usuario.email`, `gerenciacao.chave_referencia` |
| **INDEX** | `usuario.email`, `gerenciacao.chave_referencia` |
| **ENUM** | `usuario.role` (ADMIN/ANALISTA/PT), `soa_ia.status` (NA/FILA/PROCESSANDO/CONCLUIDO/FALHA/TIMEOUT/REMANENTE), `analise_feedback.sentimento` (POSITIVO/NEUTRO/NEGATIVO) |

### Verificar banco criado

```bash
python check_db.py
```

---

## API — Endpoints

**Base URL:** `http://localhost:8000/api/v1`

### Health
| Método | Endpoint | Retorna |
|---|---|---|
| `GET` | `/health` | `{"status": "ok", "version": "1.0.0"}` |

### Usuários
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/usuarios` | `{nome, email, role}` | Usuário criado | 201, 409, 422 |
| `GET` | `/usuarios` | `?skip=0&limit=50` | Lista de usuários | 200 |
| `GET` | `/usuarios/{uuid}` | — | Usuário | 200, 404 |
| `DELETE` | `/usuarios/{uuid}` | — | — | 204, 404 |

### Modelos de IA (VideoModelo)
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/video-modelos` | `{provider, nome_modelo, status_ativo, is_current}` | Modelo criado | 201, 422 |
| `GET` | `/video-modelos` | — | Lista de modelos | 200 |
| `PATCH` | `/video-modelos/{uuid}/ativar` | — | Modelo ativado como current | 200, 404 |

### Conversas
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/conversas` | `{fk_usuario, titulo, tipo_consultor, configuracoes}` | Conversa criada | 201, 422 |
| `GET` | `/conversas` | `?fk_usuario&status&skip&limit` | Lista paginada | 200 |
| `GET` | `/conversas/{uuid}` | — | Conversa | 200, 404 |

### ⭐ Consulta IA (endpoint principal)
| Método | Endpoint | Body | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/conversas/consultar` | `{conversa_uuid, mensagem, tipo_consultor}` | Resposta da IA + metadados | 200, 404, 422, 502, 504 |

**Exemplo de request:**
```json
POST /api/v1/conversas/consultar
{
  "conversa_uuid": "uuid-da-conversa",
  "mensagem": "Qual é a melhor estratégia para reduzir custos operacionais?",
  "tipo_consultor": "financeiro"
}
```

**Exemplo de response:**
```json
{
  "gerenciacao_uuid": "abc-123",
  "soa_ia_uuid": "def-456",
  "resposta": "Para reduzir custos operacionais, recomendo...",
  "tokens_entrada": 120,
  "tokens_saida": 350,
  "modelo_utilizado": "gpt-4o",
  "finish_reason": "stop",
  "created_at": "2026-09-24T19:00:00"
}
```

### LOA / Punição
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/loa-punicao` | `{fk_conversa_set, tipo, boolean_status, valor, metodo_ativo}` | LOA criada | 201, 422 |
| `GET` | `/loa-punicao/{conversa_uuid}` | — | Lista de LOAs | 200, 404 |

### Gerenciação
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/gerenciacoes` | `{fk_pessoa, tipo_pot, fingerprint_dispositivo, credencial_ip}` | Gerenciação criada | 201, 422 |
| `GET` | `/gerenciacoes` | `?fk_pessoa&status_filtro&skip&limit` | Lista paginada | 200 |
| `GET` | `/gerenciacoes/{uuid}` | — | Gerenciação | 200, 404 |
| `PATCH` | `/gerenciacoes/{uuid}/status` | `?novo_status=CONCLUIDO` | Atualizado | 200, 404, 422 |

### SOA_IA
| Método | Endpoint | Retorna | Códigos |
|---|---|---|---|
| `GET` | `/soa-ia/{uuid}` | Objeto SOA_IA com status | 200, 404 |
| `GET` | `/soa-ia/gerenciacao/{gerenciacao_uuid}` | SOA_IA da gerenciação | 200, 404 |

### Prompts
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/prompts` | `{fk_video_modelo, conteudo, contexto, status_ativo}` | Prompt criado | 201, 422 |
| `GET` | `/prompts` | `?apenas_ativos=true` | Lista de prompts | 200 |
| `PATCH` | `/prompts/{uuid}/desativar` | — | Prompt desativado | 200, 404 |

### Dimensões KPIs
| Método | Endpoint | Retorna | Códigos |
|---|---|---|---|
| `GET` | `/dimensoes-kpis/{gerenciacao_uuid}` | Lista de KPIs | 200, 404 |

### Análise de Feedback
| Método | Endpoint | Body / Params | Retorna | Códigos |
|---|---|---|---|---|
| `POST` | `/analises-feedback` | `{fk_gerenciacao, texto_para_analisar}` | Análise criada | 201, 422, 502 |
| `GET` | `/analises-feedback` | `?fk_gerenciacao&sentimento&skip&limit` | Lista paginada | 200 |

---

## Fluxo de Funcionamento

```
Frontend
   │
   │  POST /api/v1/conversas/consultar
   │  { conversa_uuid, mensagem }
   ▼
FastAPI (main.py)
   │
   ├─ [1] Valida schema Pydantic → 422 se inválido
   ├─ [2] Busca CONVERSA no banco → 404 se não existe
   ├─ [3] Registra LOA_PUNICAO (atributos de entrada)
   ├─ [4] Cria GERENCIACAO (status = PROCESSANDO)
   ├─ [5] Cria SOA_IA (status = PROCESSANDO)
   ├─ [6] Busca PROMPT ativo (VideoModelo.is_current = true)
   ├─ [7] Chama OpenAI API → 504 timeout / 502 erro IA
   ├─ [8] Atualiza SOA_IA e GERENCIACAO (status = CONCLUIDO)
   ├─ [9] Retorna resposta ao Frontend  ◄──────────────────
   │
   └─ [10] Background Task (assíncrono, não bloqueia)
            ├─ Chama IA para análise de sentimento
            └─ Salva ANALISE_FEEDBACK no banco
```

---

## Tratamento de Erros

Todos os erros retornam no formato padronizado:

```json
{
  "error": {
    "code": "CODIGO_DO_ERRO",
    "message": "Descrição legível do erro",
    "details": { ... }
  }
}
```

### Tabela de erros

| Cenário | HTTP | Código |
|---|---|---|
| Campo obrigatório ausente / tipo errado | 422 | `VALIDATION_ERROR` |
| Recurso não encontrado | 404 | `NOT_FOUND` |
| E-mail duplicado / chave única violada | 409 | `CONFLICT` |
| Banco de dados indisponível | 503 | `DATABASE_UNAVAILABLE` |
| Timeout de consulta no banco | 504 | `DATABASE_TIMEOUT` |
| API externa (OpenAI) indisponível | 502 | `EXTERNAL_API_ERROR` |
| Timeout na chamada à IA | 504 | `TIMEOUT` |
| Quota da IA excedida (rate limit) | 502 | `AI_QUOTA_EXCEEDED` |
| Conteúdo bloqueado pelo filtro da IA | 422 | `AI_CONTENT_FILTER` |
| Resposta da IA vazia ou malformada | 502 | `AI_ERROR` |
| Erro interno não tratado | 500 | `INTERNAL_ERROR` |

### Resiliência configurável (`.env`)

```env
OPENAI_TIMEOUT_SECONDS=30    # timeout por chamada
OPENAI_MAX_RETRIES=3         # retries automáticos com backoff
MAX_TOKENS_RESPONSE=2048     # limite de tokens da resposta
```

---

## Estrutura de Pastas

```
Banco_PORTO_2026/
│
├── main.py                         # Ponto de entrada FastAPI
├── seed_db.py                      # Cria tabelas + dados iniciais
├── check_db.py                     # Verifica tabelas criadas
├── requirements.txt                # Dependências Python
├── .env.example                    # Template de variáveis de ambiente
├── .gitignore
│
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── router.py           # Agrega todos os routers
│   │       └── endpoints/
│   │           ├── usuarios.py     # Usuários + VideoModelo
│   │           ├── conversas.py    # Conversas + Consulta IA + LOA + Feedback
│   │           └── gerenciacao.py  # Gerenciação + SOA_IA + Prompts + KPIs
│   │
│   ├── core/
│   │   ├── config.py               # Pydantic Settings (.env)
│   │   ├── database.py             # Engine, Session, Base
│   │   └── errors.py               # Exceções customizadas + handlers
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py               # 16 entidades SQLAlchemy
│   │
│   ├── schemas/
│   │   └── schemas.py              # Schemas Pydantic request/response
│   │
│   └── services/
│       └── ia_service.py           # Integração OpenAI + análise sentimento
│
└── ai_consulting.db                # Banco SQLite (gerado pelo seed_db.py)
```

---

## Estruturas de IA

| Entidade | Papel |
|---|---|
| `video_modelo` | Registro dos LLMs. `is_current=True` define o modelo ativo |
| `tutor_circuito_treinado` | Circuito de treinamento com benchmarks e documentos base |
| `prompt` | Engenharia de prompt — define o comportamento do consultor IA |
| `configurar_circuito_set` | Configuração fina: forma de resposta, certificação humanizada |
| `soa_ia` | Orquestrador SOA — rastreia fila, processamento e conclusão |
| `linha_raciocinio` | Persiste Chain-of-Thought para auditoria e debugging |
| `analise_feedback` | Análise de sentimento (POSITIVO/NEUTRO/NEGATIVO) com confiança e sugestões |
| `loa_punicao` + `matriz_punicao_set` | Sistema de pontuação que modula o comportamento da IA |

---

## Usando PostgreSQL em produção

1. Instale o driver:
```bash
pip install psycopg2-binary
```

2. Atualize o `.env`:
```env
DATABASE_URL=postgresql+psycopg2://usuario:senha@localhost:5432/ai_consulting
```

3. Rode as migrações:
```bash
python seed_db.py
```

---

## Exemplos com curl

### Criar usuário
```bash
curl -X POST http://localhost:8000/api/v1/usuarios \
  -H "Content-Type: application/json" \
  -d '{"nome": "João Silva", "email": "joao@empresa.com", "role": "ANALISTA"}'
```

### Criar conversa
```bash
curl -X POST http://localhost:8000/api/v1/conversas \
  -H "Content-Type: application/json" \
  -d '{"fk_usuario": "<uuid-do-usuario>", "titulo": "Consultoria Financeira"}'
```

### Consultar a IA
```bash
curl -X POST http://localhost:8000/api/v1/conversas/consultar \
  -H "Content-Type: application/json" \
  -d '{
    "conversa_uuid": "<uuid-da-conversa>",
    "mensagem": "Como posso reduzir custos operacionais em 20%?"
  }'
```

---

## Licença

MIT License — livre para uso, modificação e distribuição.

---

*Desenvolvido com Python 3.12 · FastAPI · SQLAlchemy 2 · OpenAI*
