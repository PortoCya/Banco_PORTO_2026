# Migrations (Alembic)

O schema do banco só muda por migration versionada. A aplicação **não** cria
nem altera tabelas ao subir.

```bash
alembic upgrade head                          # aplica o que falta
alembic revision --autogenerate -m "descricao" # gera a migration a partir dos modelos
alembic check                                  # falha se modelos e migrations divergirem
alembic upgrade head --sql                     # só mostra o SQL, para revisão
alembic downgrade -1                           # desfaz a última
```

O teste `tests/test_infra.py::test_migrations_criam_exatamente_o_schema_dos_modelos`
quebra se alguém mudar um modelo e esquecer a migration.

## Regra: não se apaga coluna no mesmo deploy

Durante um deploy, código velho e código novo rodam ao mesmo tempo contra o
mesmo banco. Por isso toda mudança incompatível é feita em **dois deploys**
(expandir → contrair):

| Quero... | Deploy 1 (expandir) | Deploy 2 (contrair) |
|---|---|---|
| Remover coluna/tabela | O código para de ler e escrever | Migration com o `DROP` |
| Renomear coluna | Cria a nova, escreve nas duas, copia os dados | Código usa só a nova; depois `DROP` da antiga |
| Tornar coluna `NOT NULL` | Adiciona nullable + código sempre preenche + backfill | `ALTER ... SET NOT NULL` |
| Adicionar coluna obrigatória | Adiciona com `server_default` (ou nullable) | Remove o default, se for o caso |

Uma migration com `drop_column`/`drop_table` no `upgrade()` precisa declarar
qual deploy anterior parou de usar aquilo:

```python
def upgrade() -> None:
    # contrato: PR #123 (parou de usar submissao.campo_antigo, em produção desde 2026-12-01)
    op.drop_column("submissao", "campo_antigo")
```

Sem a linha `# contrato: ...` o teste
`test_migration_nao_remove_coluna_ou_tabela_sem_marcacao` falha.

## Checklist de PR com migration

- [ ] `upgrade()` e `downgrade()` testados localmente em PostgreSQL.
- [ ] A migration não importa código de `app/` (ela precisa funcionar daqui a um ano).
- [ ] Coluna nova usada em `WHERE`/`JOIN`/`ORDER BY` tem índice.
- [ ] Índice em tabela grande: `postgresql_concurrently=True` dentro de `autocommit_block()`.
- [ ] Nada de `DROP`/rename no mesmo deploy que para de usar (tabela acima).
- [ ] Tabela nova da camada de IA? Atualize `scripts/permissoes_worker.sql`.
- [ ] Backup recente com restore testado antes de aplicar em produção.

## Banco criado antes das migrations

Bancos locais criados pelo antigo `Base.metadata.create_all()` têm outro
schema (não havia produção). Apague o arquivo SQLite / recrie o banco e rode
`alembic upgrade head`.
