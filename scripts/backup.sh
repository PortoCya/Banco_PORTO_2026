#!/usr/bin/env bash
# Backup do PostgreSQL (pg_dump, formato custom, comprimido).
#
#   DATABASE_URL=postgresql+psycopg://... scripts/backup.sh
#
# Variáveis:
#   DATABASE_URL    banco a copiar (a mesma da aplicação)
#   BACKUP_DIR      destino (padrão: ./backups — fora do git)
#   BACKUP_RETENCAO quantos dumps manter (padrão: 14)
#
# Um backup só vale depois de restaurado: rode scripts/restore_teste.sh no
# arquivo gerado (agende os dois juntos). O dump contém dados pessoais —
# guarde-o cifrado e fora do servidor do banco.
set -euo pipefail

: "${DATABASE_URL:?defina DATABASE_URL}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
BACKUP_RETENCAO="${BACKUP_RETENCAO:-14}"

# A app usa o prefixo do SQLAlchemy (postgresql+psycopg://); o pg_dump quer o da libpq.
URL_LIBPQ="$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')"
case "$URL_LIBPQ" in
  postgresql://*) ;;
  *) echo "backup.sh só funciona com PostgreSQL" >&2; exit 2 ;;
esac

umask 077                                   # dump legível só pelo dono
mkdir -p "$BACKUP_DIR"
ARQUIVO="$BACKUP_DIR/nps_$(date -u +%Y%m%dT%H%M%SZ).dump"

# Escreve em arquivo temporário e renomeia no final: um backup interrompido
# nunca fica com cara de backup válido.
PGCONNECT_TIMEOUT=10 pg_dump --format=custom --no-owner --no-privileges \
  --lock-wait-timeout=30000 --file="$ARQUIVO.parcial" "$URL_LIBPQ"
pg_restore --list "$ARQUIVO.parcial" > /dev/null    # o arquivo é legível?
mv "$ARQUIVO.parcial" "$ARQUIVO"
sha256sum "$ARQUIVO" > "$ARQUIVO.sha256"

# Retenção: mantém os N mais recentes
ls -1t "$BACKUP_DIR"/nps_*.dump 2>/dev/null | tail -n +"$((BACKUP_RETENCAO + 1))" | while read -r antigo; do
  rm -f "$antigo" "$antigo.sha256"
done

echo "$ARQUIVO"
