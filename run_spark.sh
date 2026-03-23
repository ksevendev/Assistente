#!/usr/bin/env bash
# Inicializa especificamente como nó SPARK
cd "$(dirname "$(realpath "$0")")"
source ".venv/bin/activate"

# Patch rápido do NODE_TYPE sem editar config.py
python3 -c "
import config
config.NODE_TYPE = 'spark'
config.ASSISTANT_NAME = config.NETWORK_NODES['spark']['name']
import core
core.main()
"
