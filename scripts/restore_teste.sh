#!/usr/bin/env bash
# Teste de restore: restaura um dump em um banco TEMPORÁRIO e confere o
# resultado contra o banco de origem. Nunca toca no banco de produção.
#
#   DATABASE_URL=postgresql+psycopg://... scripts/restore_teste.sh backups/nps_....dump
#
# O usuário precisa de CREATEDB. Confere:
#   1. integridade do arquivo (sha256);
#   2. pg_restore sem nenhum erro;
#   3. mesma revisão do Alembic do banco de origem;
#   4. todas as tabelas presentes, com constraints e índices;
#   5. contagem de linhas por tabela (>= à do momento do dump não dá para
#      saber; por isso compara com a origem e só reclama se o restore tiver
#      MAIS linhas ou se uma tabela não vier).
# Sai com código 0 só se tudo conferir.
set -euo pipefail

ARQUIVO="${1:?uso: restore_teste.sh <arquivo.dump>}"
: "${DATABASE_URL:?defina DATABASE_URL (banco de origem, para comparar)}"

URL_LIBPQ="$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"
BASE="${URL_LIBPQ%/*}"                       # tudo antes de /<banco>
SUFIXO="${URL_LIBPQ##*/}"                    # <banco>?<parâmetros>
PARAMETROS=""; case "$SUFIXO" in *\?*) PARAMETROS="?${SUFIXO#*\?}" ;; esac
TEMP_DB="nps_restore_teste_$(date -u +%Y%m%d%H%M%S)_$$"
URL_TEMP="$BASE/$TEMP_DB$PARAMETROS"
export PGCONNECT_TIMEOUT=10

sql() { psql --no-psqlrc --quiet --tuples-only --no-align -v ON_ERROR_STOP=1 "$1" -c "$2"; }

limpar() { sql "$URL_LIBPQ" "DROP DATABASE IF EXISTS \"$TEMP_DB\"" > /dev/null 2>&1 || true; }
trap limpar EXIT

echo "1/5 integridade do arquivo"
if [ -f "$ARQUIVO.sha256" ]; then
  (cd "$(dirname "$ARQUIVO")" && sha256sum --check --quiet "$(basename "$ARQUIVO").sha256")
else
  echo "    (sem .sha256 ao lado do dump; pulando)"
fi

echo "2/5 restaurando em $TEMP_DB"
sql "$URL_LIBPQ" "CREATE DATABASE \"$TEMP_DB\""
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$URL_TEMP" "$ARQUIVO"

echo "3/5 revisão do Alembic"
REV_ORIGEM="$(sql "$URL_LIBPQ" "SELECT version_num FROM alembic_version")"
REV_RESTORE="$(sql "$URL_TEMP" "SELECT version_num FROM alembic_version")"
[ -n "$REV_RESTORE" ] || { echo "ERRO: restore sem alembic_version" >&2; exit 1; }
[ "$REV_ORIGEM" = "$REV_RESTORE" ] || echo "    aviso: origem está em $REV_ORIGEM, dump em $REV_RESTORE (dump anterior a uma migration)"

echo "4/5 estrutura"
ESTRUTURA="SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public')
  || ' tabelas, ' || (SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public')
  || ' constraints, ' || (SELECT count(*) FROM pg_indexes WHERE schemaname='public') || ' índices'"
EST_RESTORE="$(sql "$URL_TEMP" "$ESTRUTURA")"
echo "    $EST_RESTORE"
if [ "$REV_ORIGEM" = "$REV_RESTORE" ] && [ "$(sql "$URL_LIBPQ" "$ESTRUTURA")" != "$EST_RESTORE" ]; then
  echo "ERRO: estrutura restaurada difere da origem" >&2; exit 1
fi

echo "5/5 contagem de linhas"
FALHOU=0
for TABELA in $(sql "$URL_LIBPQ" "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1"); do
  # Os nomes vêm do catálogo do próprio banco e vão entre aspas (quote_ident).
  CONSULTA="SELECT count(*) FROM $(sql "$URL_LIBPQ" "SELECT quote_ident('$TABELA')")"
  N_ORIGEM="$(sql "$URL_LIBPQ" "$CONSULTA")"
  N_RESTORE="$(sql "$URL_TEMP" "$CONSULTA" 2>/dev/null || echo AUSENTE)"
  printf '    %-26s origem=%-8s restore=%s\n' "$TABELA" "$N_ORIGEM" "$N_RESTORE"
  if [ "$N_RESTORE" = "AUSENTE" ] || [ "$N_RESTORE" -gt "$N_ORIGEM" ]; then FALHOU=1; fi
done
[ "$FALHOU" -eq 0 ] || { echo "ERRO: contagens não conferem" >&2; exit 1; }

echo "OK: restore testado com sucesso ($ARQUIVO)"
