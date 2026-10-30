#!/bin/sh
# Funções comuns dos scripts de operação. Carregado com ". scripts/common.sh" a partir da pasta do projeto.

# Pasta do projeto = pai desta pasta, para funcionar de qualquer diretório.
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.synology.yml}"

# Carrega o .env (LIB_PSWD, LIVROS_HOST_DIR...). Senha: sem espaços nem aspas.
if [ ! -f .env ]; then
    echo "Arquivo .env não encontrado em $PROJECT_DIR." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

# Docker Compose v2 (plugin) ou o binário antigo docker-compose.
if docker compose version >/dev/null 2>&1; then
    compose() { docker compose -f "$COMPOSE_FILE" "$@"; }
else
    compose() { docker-compose -f "$COMPOSE_FILE" "$@"; }
fi
