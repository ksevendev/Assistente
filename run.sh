#!/usr/bin/env bash
# k7-core | run.sh — Inicialização rápida
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
source "${SCRIPT_DIR}/.venv/bin/activate"
cd "$SCRIPT_DIR"
NODE_TYPE="${NODE_TYPE:-seven}"
info_msg="Iniciando k7-core | Nó: $NODE_TYPE | Porta: 7007"
echo "$info_msg"
exec python core.py "$@"
