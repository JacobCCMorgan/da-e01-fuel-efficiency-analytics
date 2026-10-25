#!/usr/bin/env bash
# Optional native local PostgreSQL lifecycle. Runs as the current non-root user.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
pg_data="${FLEET_PG_DATA:-$project_root/data/postgres}"
pg_socket="${FLEET_PG_SOCKET:-$project_root/data/postgres_socket}"
pg_port="${FLEET_PG_PORT:-55432}"
case "${1:-status}" in
  start)
    if [ "$(id -u)" -eq 0 ]; then
      echo "PostgreSQL requires a regular OS user. Run this script as your normal local account." >&2
      exit 2
    fi
    for binary in initdb pg_ctl createdb psql; do
      command -v "$binary" >/dev/null || { echo "Missing PostgreSQL binary: $binary" >&2; exit 2; }
    done
    mkdir -p "$pg_socket"
    chmod 700 "$pg_socket"
    if [ ! -f "$pg_data/PG_VERSION" ]; then
      initdb -D "$pg_data" --auth-local=trust --auth-host=reject --encoding=UTF8 --no-locale
    fi
    if ! pg_ctl -D "$pg_data" status >/dev/null 2>&1; then
      pg_ctl -D "$pg_data" -l "$pg_data/server.log" -o "-k '$pg_socket' -p $pg_port -c listen_addresses=''" start
    fi
    if ! psql -h "$pg_socket" -p "$pg_port" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='fleet_fuel'" | grep -q 1; then
      createdb -h "$pg_socket" -p "$pg_port" fleet_fuel
    fi
    echo "Local database ready. FUEL_POSTGRES_DSN=dbname=fleet_fuel host=$pg_socket port=$pg_port"
    ;;
  stop) pg_ctl -D "$pg_data" stop -m fast ;;
  status) pg_ctl -D "$pg_data" status ;;
  *) echo "Usage: $0 {start|stop|status}" >&2; exit 2 ;;
esac
