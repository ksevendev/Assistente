#!/usr/bin/env bash
# Inicializa especificamente como nó SEVEN
cd "$(dirname "$(realpath "$0")")"
source ".venv/bin/activate"

# Patch rápido do NODE_TYPE sem editar config.py
python3 -c "
import config
config.NODE_TYPE = 'seven'
config.ASSISTANT_NAME = config.NETWORK_NODES['seven']['name']
import core
core.main()
"
