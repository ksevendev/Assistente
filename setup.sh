#!/usr/bin/env bash
# =============================================================================
# k7-core | setup.sh  — v3 (Distributed Nodes)
# Instala dependências para Debian 12 CLI, Ubuntu 24.04 e Termux (Android).
#
# Uso normal (Linux):
#   chmod +x setup.sh && ./setup.sh
#
# Uso no Termux (Android):
#   chmod +x setup.sh && ./setup.sh --termux
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;96m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERRO]${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}${CYAN}══ $* ${RESET}"; }

# ---------------------------------------------------------------------------
# Detecta ambiente
# ---------------------------------------------------------------------------
IS_TERMUX=false
IS_ANDROID=false

if [[ "${1:-}" == "--termux" ]] || [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
    IS_TERMUX=true
    IS_ANDROID=true
fi

echo -e "${BOLD}"
cat <<'BANNER'
  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗
  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝
  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗
  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝
  v3 — Distributed Nodes Setup
BANNER
echo -e "${RESET}"

if $IS_TERMUX; then
    info "Modo Termux (Android) detectado."
else
    info "Modo Linux Desktop detectado."
fi

SCRIPT_DIR="$(dirname "$(realpath "$0")")"

# ===========================================================================
# CAMINHO A: TERMUX (Android)
# ===========================================================================
if $IS_TERMUX; then

    step "Atualizando repositórios do Termux"
    pkg update -y

    step "Instalando pacotes Termux"
    pkg install -y python python-pip

    step "Instalando Termux:API (se não instalado)"
    info "Instale o app 'Termux:API' da F-Droid se ainda não o fez."
    pkg install -y termux-api 2>/dev/null || warn "termux-api não disponível — notificações e vibração podem não funcionar."

    step "Instalando bibliotecas Python (Termux)"
    # No Termux, PyAudio requer portaudio compilado — instalamos sem ele
    pip install --upgrade pip -q

    TERMUX_PACKAGES=(
        "flask>=3.0.0"
        "requests>=2.31.0"
        "paramiko>=3.4.0"      # SSH (compilação pode falhar em alguns devices)
    )

    for pkg_name in "${TERMUX_PACKAGES[@]}"; do
        info "Instalando: ${pkg_name}"
        pip install "$pkg_name" -q || warn "Falha ao instalar $pkg_name — continuando..."
    done

    success "Setup Termux concluído."

    cat > "${SCRIPT_DIR}/run.sh" <<'RUNSCRIPT'
#!/usr/bin/env bash
# k7-core | run.sh (Termux)
cd "$(dirname "$(realpath "$0")")"
exec python core.py "$@"
RUNSCRIPT
    chmod +x "${SCRIPT_DIR}/run.sh"

    echo ""
    echo -e "${BOLD}${GREEN}"
    cat <<'EOF'
  ╔══════════════════════════════════════════════╗
  ║     Setup Termux concluído!                  ║
  ║                                              ║
  ║  1. Instale o app 'Termux:API' (F-Droid)    ║
  ║  2. Edite config.py: NODE_TYPE = "mobile"   ║
  ║  3. Execute: python core.py                  ║
  ╚══════════════════════════════════════════════╝
EOF
    echo -e "${RESET}"
    exit 0
fi

# ===========================================================================
# CAMINHO B: LINUX DESKTOP (Debian 12 / Ubuntu 24.04)
# ===========================================================================

step "Verificando ambiente Linux"

OS_ID="$(grep -oP '(?<=^ID=).+' /etc/os-release | tr -d '"')"
OS_VER="$(grep -oP '(?<=^VERSION_ID=).+' /etc/os-release | tr -d '"')"
info "Sistema: ${OS_ID} ${OS_VER}"

PYTHON_BIN="$(command -v python3)"
PYTHON_VER="$("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')"
PYTHON_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')"
info "Python: ${PYTHON_BIN} (${PYTHON_VER})"

if [[ "$PYTHON_MINOR" -lt 10 ]]; then
    error "Python 3.10+ necessário. Versão atual: 3.${PYTHON_MINOR}"
    exit 1
fi

step "Instalando dependências do sistema (apt)"

DEBIAN_FRONTEND=noninteractive sudo apt-get update -qq

APT_PACKAGES=(
    python3 python3-pip python3-venv python3-dev
    espeak espeak-ng espeak-ng-data
    portaudio19-dev libportaudio2 libportaudiocpp0
    alsa-utils libasound2-dev
    build-essential gcc
    openssh-client net-tools
    playerctl
    ffmpeg
    curl
)

DEBIAN_FRONTEND=noninteractive sudo apt-get install -y "${APT_PACKAGES[@]}" \
    --no-install-recommends -qq 2>&1 | grep -E "(Instala|Erro|error)" || true
success "Pacotes do sistema instalados."

step "Criando ambiente virtual Python (.venv/)"

VENV_DIR="${SCRIPT_DIR}/.venv"

if [[ -d "$VENV_DIR" ]]; then
    warn "Ambiente virtual já existe."
    read -rp "  Recriar? [s/N] " REPLY
    if [[ "${REPLY,,}" == "s" ]]; then
        rm -rf "$VENV_DIR"
    fi
fi

[[ ! -d "$VENV_DIR" ]] && "$PYTHON_BIN" -m venv "$VENV_DIR"
VENV_PIP="${VENV_DIR}/bin/pip"
VENV_PYTHON="${VENV_DIR}/bin/python"

step "Instalando bibliotecas Python"

"$VENV_PIP" install --upgrade pip setuptools wheel -q

PY_PACKAGES=(
    "SpeechRecognition>=3.10.0"
    "PyAudio>=0.2.14"
    "paramiko>=3.4.0"
    "flask>=3.0.0"
    "requests>=2.31.0"
    "gTTS>=2.5.0"
    "pygame>=2.5.0"
)

for pkg_name in "${PY_PACKAGES[@]}"; do
    info "Instalando: ${pkg_name}"
    "$VENV_PIP" install "$pkg_name" -q
done

step "Verificando imports críticos"
"$VENV_PYTHON" -c "import speech_recognition; print('  ✓ SpeechRecognition', speech_recognition.__version__)"
"$VENV_PYTHON" -c "import pyaudio;           print('  ✓ PyAudio')"
"$VENV_PYTHON" -c "import paramiko;          print('  ✓ Paramiko',          paramiko.__version__)"
"$VENV_PYTHON" -c "import flask;             print('  ✓ Flask',             flask.__version__)"
"$VENV_PYTHON" -c "import requests;          print('  ✓ Requests',          requests.__version__)"
success "Todos os imports verificados."

step "Configurando chave SSH"

SSH_KEY="$HOME/.ssh/id_rsa"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"

if [[ ! -f "$SSH_KEY" ]]; then
    ssh-keygen -t rsa -b 4096 -f "$SSH_KEY" -N "" -C "k7-core-$(hostname)" -q
    chmod 600 "${SSH_KEY}" && chmod 644 "${SSH_KEY}.pub"
    success "Chave RSA gerada: ${SSH_KEY}"
    echo ""
    info "Copie para os outros nós:"
    echo -e "  ${BOLD}ssh-copy-id -i ${SSH_KEY}.pub USUARIO@IP_DO_NO${RESET}"
else
    info "Chave SSH já existe: ${SSH_KEY}"
fi

step "Gerando script de inicialização (run.sh)"

cat > "${SCRIPT_DIR}/run.sh" <<RUNSCRIPT
#!/usr/bin/env bash
# k7-core | run.sh — Inicialização rápida
SCRIPT_DIR="\$(dirname "\$(realpath "\$0")")"
source "\${SCRIPT_DIR}/.venv/bin/activate"
cd "\$SCRIPT_DIR"
NODE_TYPE="\${NODE_TYPE:-seven}"
info_msg="Iniciando k7-core | Nó: \$NODE_TYPE | Porta: 7007"
echo "\$info_msg"
exec python core.py "\$@"
RUNSCRIPT
chmod +x "${SCRIPT_DIR}/run.sh"
success "run.sh criado."

# Gera scripts por instância
for NODE in seven spark; do
    cat > "${SCRIPT_DIR}/run_${NODE}.sh" <<NODESCRIPT
#!/usr/bin/env bash
# Inicializa especificamente como nó ${NODE^^}
cd "\$(dirname "\$(realpath "\$0")")"
source ".venv/bin/activate"

# Patch rápido do NODE_TYPE sem editar config.py
python3 -c "
import config
config.NODE_TYPE = '${NODE}'
config.ASSISTANT_NAME = config.NETWORK_NODES['${NODE}']['name']
import core
core.main()
"
NODESCRIPT
    chmod +x "${SCRIPT_DIR}/run_${NODE}.sh"
    info "Script criado: run_${NODE}.sh"
done

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}"
cat <<'EOF'
  ╔════════════════════════════════════════════════════════╗
  ║               Setup v3 concluído!                      ║
  ╠════════════════════════════════════════════════════════╣
  ║  Instâncias disponíveis:                               ║
  ║                                                        ║
  ║  Nó Seven (Notebook):   ./run_seven.sh                ║
  ║  Nó Spark (PC):         ./run_spark.sh                ║
  ║  Nó Mobile (Android):   python core.py  (no Termux)   ║
  ║                                                        ║
  ║  Antes de iniciar, edite config.py:                   ║
  ║    NETWORK_NODES com os IPs reais de cada dispositivo ║
  ║                                                        ║
  ║  Testar a API manualmente:                             ║
  ║    curl -X POST http://localhost:7007/cmd \            ║
  ║      -H "Content-Type: application/json" \            ║
  ║      -d '{"command":"speak","text":"Olá!",            ║
  ║            "secret":"k7-secret-local-network",        ║
  ║            "origin":"test"}'                          ║
  ╚════════════════════════════════════════════════════════╝
EOF
echo -e "${RESET}"
