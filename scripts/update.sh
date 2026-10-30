#!/bin/sh
# Atualização da versão: rebuild das imagens e subida do container.
# Antes de rodar: copie os arquivos novos para a pasta do projeto (mantenha .env e data/).
# Uso:  sh scripts/update.sh
# Sem backup: o cache de capas é regenerável (ver docs/deploy-synology.md).
set -eu
. "$(dirname "$0")/common.sh"

compose build --pull
compose up -d
compose ps
echo "Atualização concluída. Confira o health do container com 'compose ps' (deve estar healthy)."
