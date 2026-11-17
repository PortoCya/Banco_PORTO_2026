# Operação — guia de plantão

Para quem estiver de guarda. Tudo aqui foi executado ao menos uma vez em
PostgreSQL 16 + Redis 7 locais (ver "O que foi testado" no fim).

## Sinais vitais

| O quê | Como ver | Saudável |
|---|---|---|
| API de pé | `GET /health/live` | 200 |
| API + banco | `GET /health` (faz `SELECT 1`) | 200; **503** = banco fora |
| Fila da IA | `GET /api/v1/ia/jobs?status=NA_FILA` (ADMIN) | lista curta |
| Jobs falhando | `GET /api/v1/ia/jobs?status=FALHOU` | `ultimo_erro` diz o motivo |
| Orçamento da IA | `GET /api/v1/ia/limite-custo` | `circuit_breaker_aberto: false` |
| Uma requisição específica | `grep request_id=<id>` nos logs | — |

Todo erro devolve `error.correlation_id` e o cabeçalho `X-Request-ID`: peça
esse id a quem reportou o problema e procure-o nos logs da API. No worker o
campo é `job-<id>` ou `avaliacao-<id>`.

## O que cada código significa

| Código | Causa | Ação |
|---|---|---|
| 429 `TOO_MANY_REQUESTS` | rate limit por IP/e-mail (login, rotas públicas) | normal; ver `Retry-After` |
| 429 `SERVER_BUSY` | pool de conexões esgotado (servidor saturado) | ver consultas lentas; subir `DB_POOL_SIZE` só se o banco aguentar |
| 503 `DATABASE_UNAVAILABLE` | banco fora, `statement_timeout` ou `lock_timeout` | conferir o PostgreSQL |
| 503 em `/ia/limite-custo` ou `/golden-set/avaliacoes` | Redis fora | só a camada de IA é afetada; a coleta segue |
| 409 em `/public/respostas` | resposta duplicada (por projeto) | nenhuma |
| 500 `INTERNAL_ERROR` | bug | `grep request_id=...` e abrir issue |

## Regra de ouro em incidente

**A coleta de respostas e o NPS não dependem da IA nem do Redis.** Se a IA
estiver dando problema, pode desligar o worker sem medo: as respostas
continuam entrando, os jobs ficam `NA_FILA` no banco e são processados quando
o worker voltar.

- Provedor de IA fora do ar → jobs em `TENTANDO_NOVAMENTE` com backoff; depois de `IA_MAX_TENTATIVAS` viram `FALHOU`. Reprocessar: `POST /api/v1/ia/jobs/{id}/reprocessar`.
- Orçamento estourado → `EVENTO_CIRCUIT_BREAKER` aberto, nada sai para o provedor. Resolver: `PUT /api/v1/ia/limite-custo` com um limite acima do custo acumulado (fica auditado).
- Redis fora → rate limit cai para contagem por processo; worker segue pela varredura do banco, **sem enviar nada ao provedor** (não consegue conferir o orçamento).
- Worker morreu no meio de um job → o job fica `PROCESSANDO` e é retomado sozinho após `IA_LEASE_SEGUNDOS`.

## Backup e restore

```bash
# backup (pg_dump comprimido + sha256, retenção de 14 arquivos)
DATABASE_URL=postgresql+psycopg://... scripts/backup.sh

# teste de restore: restaura num banco TEMPORÁRIO, compara com a origem e apaga
DATABASE_URL=postgresql+psycopg://... scripts/restore_teste.sh backups/nps_<data>.dump
```

- Agende os dois juntos (ex.: cron diário). **Backup que nunca foi restaurado não é backup**; o `restore_teste.sh` sai com código ≠ 0 se algo não conferir — ligue isso a um alerta.
- O dump tem dados pessoais (comentários, e-mails de usuários): guarde cifrado e fora do servidor do banco.
- Redis não precisa de backup: a fila é reconstruída a partir de `JOB_IA`; perde-se apenas o contador de custo do mês e o limite configurado (volta para `IA_LIMITE_CUSTO_PADRAO`).

### Restore de verdade (desastre)

```bash
createdb nps_novo
pg_restore --exit-on-error --no-owner --dbname=postgresql://.../nps_novo backups/nps_<data>.dump
psql postgresql://.../nps_novo -v senha="'<senha>'" -f scripts/permissoes_worker.sql   # como superusuário
DATABASE_URL=postgresql+psycopg://.../nps_novo alembic upgrade head   # se o dump for anterior a alguma migration
# aponte DATABASE_URL da API e do worker para nps_novo e reinicie
```

Respostas recebidas entre o último backup e o desastre se perdem (RPO = intervalo do backup). Se isso não for aceitável, ligue arquivamento de WAL/PITR no PostgreSQL — não está configurado aqui.

## Deploy

1. Backup + `restore_teste.sh` verde.
2. `alembic upgrade head` (antes de subir o código novo; migrations são sempre compatíveis com o código anterior — ver `alembic/README.md`).
3. Subir API e worker. Conferir `GET /health`.
4. Rollback de código é seguro a qualquer momento; `alembic downgrade` só se a migration não tiver apagado nada.

Sexta-feira: migration que mexe em tabela grande ou muda o worker espera segunda.

## Segredos

- Só em variável de ambiente (`.env` fora do git). A app não sobe sem `SECRET_KEY`.
- Trocar `SECRET_KEY` derruba todos os logins (tokens antigos deixam de valer) e muda o hash de IP gravado dali em diante.
- Chave do provedor de IA vazou? Revogue no painel do provedor, gere outra, atualize `IA_API_KEY` e reinicie só o worker.

## O que foi testado (2026-11-16, ambiente local)

- Suíte `pytest` em SQLite e em PostgreSQL 16 (`TEST_DATABASE_URL=...`), incluindo corrida real de respostas simultâneas.
- `alembic upgrade head` / `check` / `downgrade base` em PostgreSQL e SQLite.
- `scripts/permissoes_worker.sql`: o usuário `nps_worker` não consegue ler `usuario` nem alterar `submissao.nota_nps` ou `snapshot_nps`.
- API + worker (usuário restrito) + Redis reais, com um provedor de IA **simulado** em HTTP local.
- `scripts/backup.sh` + `scripts/restore_teste.sh`, inclusive a rejeição de um dump corrompido.

**Não testado:** `docker compose up` (sem Docker no ambiente em que isto foi escrito) e chamadas a um provedor de IA real (sem chave).
