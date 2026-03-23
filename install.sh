#!/usr/bin/env bash
# =============================================================================
# k7-core v2.0 | install.sh
# Instalador unificado — Debian 12, Ubuntu 24.04, Arch, macOS e Termux (Android)
#
# Uso:
#   curl -fsSL https://raw.githubusercontent.com/SEU_USER/k7-core/main/install.sh | bash
#   # ou localmente:
#   chmod +x install.sh && ./install.sh [opções]
#
# Opções:
#   --node seven|spark|mobile   Define o tipo de nó (padrão: seven)
#   --dir  CAMINHO              Diretório de instalação (padrão: ~/k7-core)
#   --branch NOME               Branch do git (padrão: main)
#   --no-voice                  Pula PyAudio e espeak (servidor headless)
#   --no-ssh-key                Não gera chave SSH
#   --termux                    Força modo Termux
#   --dev                       Instala dependências de desenvolvimento
#   --help                      Exibe esta ajuda
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ─── Cores ───────────────────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;96m'
B='\033[0;34m'; M='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; RST='\033[0m'

log_info()    { printf "${C}[INFO]${RST}  %s\n" "$*"; }
log_ok()      { printf "${G}[ OK ]${RST}  %s\n" "$*"; }
log_warn()    { printf "${Y}[WARN]${RST}  %s\n" "$*"; }
log_error()   { printf "${R}[ERRO]${RST}  %s\n" "$*" >&2; }
log_step()    { printf "\n${BOLD}${C}━━━ %s ${RST}\n" "$*"; }
log_section() { printf "\n${BOLD}${B}▶ %s${RST}\n" "$*"; }

# ─── Banner ───────────────────────────────────────────────────────────────────
banner() {
printf "${BOLD}${C}"
cat << 'EOF'

  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗
  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝
  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗
  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝

EOF
printf "${RST}"
printf "  ${BOLD}k7-core v2.0${RST} ${DIM}— Assistente Virtual Distribuído${RST}\n"
printf "  ${DIM}Instalador Unificado Linux / macOS / Termux${RST}\n\n"
}

# ─── Defaults ─────────────────────────────────────────────────────────────────
NODE_TYPE="seven"
INSTALL_DIR="${HOME}/k7-core"
GIT_BRANCH="main"
GIT_REPO="https://github.com/SEU_USER/k7-core.git"
NO_VOICE=false
NO_SSH_KEY=false
FORCE_TERMUX=false
DEV_MODE=false
IS_TERMUX=false
IS_MACOS=false
IS_ARCH=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)    NODE_TYPE="$2";    shift 2 ;;
    --dir)     INSTALL_DIR="$2";  shift 2 ;;
    --branch)  GIT_BRANCH="$2";   shift 2 ;;
    --no-voice)   NO_VOICE=true;  shift ;;
    --no-ssh-key) NO_SSH_KEY=true; shift ;;
    --termux)  FORCE_TERMUX=true; shift ;;
    --dev)     DEV_MODE=true;     shift ;;
    --help|-h)
      banner
      printf "Opções:\n"
      printf "  --node seven|spark|mobile   Tipo de nó (padrão: seven)\n"
      printf "  --dir  CAMINHO              Diretório de instalação (padrão: ~/k7-core)\n"
      printf "  --branch NOME               Branch git (padrão: main)\n"
      printf "  --no-voice                  Sem PyAudio/espeak\n"
      printf "  --no-ssh-key                Não gera chave SSH\n"
      printf "  --termux                    Força modo Termux\n"
      printf "  --dev                       Dependências de desenvolvimento\n"
      exit 0 ;;
    *) log_error "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

# ─── Detecção de ambiente ─────────────────────────────────────────────────────
detect_env() {
  if $FORCE_TERMUX || [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
    IS_TERMUX=true
    NODE_TYPE="mobile"
    INSTALL_DIR="${HOME}/k7-core"
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    IS_MACOS=true
  elif [[ -f "/etc/arch-release" ]]; then
    IS_ARCH=true
  fi
}

# ─── Verificações de prerequisito ─────────────────────────────────────────────
check_prerequisites() {
  log_section "Verificando pré-requisitos"

  # Python 3.10+
  local py_bin
  py_bin="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
  if [[ -z "$py_bin" ]]; then
    log_error "Python 3 não encontrado."
    if $IS_MACOS;   then log_info "Instale com: brew install python3"; fi
    if $IS_TERMUX;  then log_info "Execute: pkg install python"; fi
    if ! $IS_MACOS && ! $IS_TERMUX; then
      log_info "Execute: sudo apt install python3"
    fi
    exit 1
  fi

  local py_ver py_minor
  py_ver="$("$py_bin" --version 2>&1 | awk '{print $2}')"
  py_minor="$("$py_bin" -c 'import sys; print(sys.version_info.minor)')"

  if [[ "$py_minor" -lt 10 ]]; then
    log_error "Python 3.10+ é necessário. Encontrado: Python ${py_ver}"
    exit 1
  fi
  log_ok "Python ${py_ver} (${py_bin})"

  # git (apenas para clone remoto)
  if ! command -v git &>/dev/null; then
    log_warn "git não encontrado — será instalado automaticamente."
  else
    log_ok "git $(git --version | awk '{print $3}')"
  fi

  # Espaço em disco (mínimo 500 MB)
  local free_mb
  if command -v df &>/dev/null; then
    free_mb=$(df -m "${HOME}" 2>/dev/null | awk 'NR==2 {print $4}' || echo "9999")
    if [[ "${free_mb:-0}" -lt 500 ]]; then
      log_warn "Pouco espaço em disco: ${free_mb} MB livres. Recomendado: 500 MB."
    fi
  fi

  # Permissão sudo (Linux não-Termux)
  if ! $IS_TERMUX && ! $IS_MACOS; then
    if ! sudo -n true 2>/dev/null; then
      log_warn "sudo pode solicitar senha durante a instalação."
    else
      log_ok "sudo disponível"
    fi
  fi
}

# ─── Instalação de dependências de sistema ─────────────────────────────────────
install_system_deps() {
  log_section "Instalando dependências de sistema"

  if $IS_TERMUX; then
    pkg update -y -q
    local termux_pkgs=(python python-pip git)
    pkg install -y "${termux_pkgs[@]}" -q
    pkg install -y termux-api 2>/dev/null \
      || log_warn "termux-api falhou — instale o app Termux:API pela F-Droid."
    log_ok "Pacotes Termux instalados."
    return
  fi

  if $IS_MACOS; then
    if ! command -v brew &>/dev/null; then
      log_info "Instalando Homebrew..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew update -q
    local brew_pkgs=(python3 git portaudio ffmpeg espeak)
    for p in "${brew_pkgs[@]}"; do
      brew list "$p" &>/dev/null || brew install "$p" -q
    done
    log_ok "Pacotes Homebrew instalados."
    return
  fi

  if $IS_ARCH; then
    sudo pacman -Sy --noconfirm --needed \
      python python-pip git espeak-ng portaudio ffmpeg openssh playerctl base-devel \
      2>&1 | grep -E "instalando|error|erro" || true
    log_ok "Pacotes Arch instalados."
    return
  fi

  # Debian / Ubuntu
  DEBIAN_FRONTEND=noninteractive sudo apt-get update -qq

  local apt_pkgs=(
    python3 python3-pip python3-venv python3-dev
    git curl wget
    espeak espeak-ng espeak-ng-data
    portaudio19-dev libportaudio2 libportaudiocpp0
    alsa-utils libasound2-dev
    build-essential gcc pkg-config
    openssh-client net-tools
    playerctl
    ffmpeg
  )

  DEBIAN_FRONTEND=noninteractive sudo apt-get install -y "${apt_pkgs[@]}" \
    --no-install-recommends -qq 2>&1 | grep -E "^(Get:|Inst|Err)" | head -20 || true
  log_ok "Pacotes apt instalados."
}

# ─── Obter o código ────────────────────────────────────────────────────────────
get_code() {
  log_section "Obtendo código-fonte"

  # Se o install.sh está dentro do próprio projeto, apenas usa o diretório atual
  if [[ -f "${SCRIPT_DIR}/core.py" ]] && [[ -f "${SCRIPT_DIR}/config.py" ]]; then
    log_info "Código encontrado no diretório atual: ${SCRIPT_DIR}"
    INSTALL_DIR="${SCRIPT_DIR}"
    return
  fi

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    log_info "Repositório já existe em ${INSTALL_DIR}. Atualizando..."
    git -C "${INSTALL_DIR}" fetch origin "${GIT_BRANCH}" -q
    git -C "${INSTALL_DIR}" reset --hard "origin/${GIT_BRANCH}" -q
    log_ok "Código atualizado (branch: ${GIT_BRANCH})"
    return
  fi

  if [[ -d "${INSTALL_DIR}" ]] && [[ -f "${INSTALL_DIR}/core.py" ]]; then
    log_info "Instalação existente em ${INSTALL_DIR} (sem git). Mantendo arquivos."
    return
  fi

  log_info "Clonando repositório em ${INSTALL_DIR}..."
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone --depth 1 --branch "${GIT_BRANCH}" "${GIT_REPO}" "${INSTALL_DIR}" -q
  log_ok "Repositório clonado (branch: ${GIT_BRANCH})"
}

# ─── Ambiente virtual Python ───────────────────────────────────────────────────
setup_venv() {
  log_section "Configurando ambiente Python"

  local venv_dir="${INSTALL_DIR}/.venv"
  local py_bin
  py_bin="$(command -v python3 2>/dev/null || command -v python)"

  if $IS_TERMUX; then
    log_info "Termux usa Python global — sem venv."
    PIP_CMD="pip"
    PYTHON_CMD="python"
  else
    if [[ -d "${venv_dir}" ]]; then
      log_info "Ambiente virtual existente em ${venv_dir}."
    else
      log_info "Criando .venv em ${venv_dir}..."
      "$py_bin" -m venv "${venv_dir}"
      log_ok ".venv criado."
    fi
    PIP_CMD="${venv_dir}/bin/pip"
    PYTHON_CMD="${venv_dir}/bin/python"
  fi

  log_info "Atualizando pip, setuptools e wheel..."
  "$PIP_CMD" install --upgrade pip setuptools wheel -q
  log_ok "pip atualizado: $("$PIP_CMD" --version | awk '{print $2}')"
}

# ─── Dependências Python ───────────────────────────────────────────────────────
install_python_deps() {
  log_section "Instalando bibliotecas Python"

  local pkgs_core=(
    "flask>=3.0.0"
    "flask-login>=0.6.3"
    "werkzeug>=3.0.0"
    "requests>=2.31.0"
    "zeroconf>=0.131.0"
    "paramiko>=3.4.0"
  )

  local pkgs_voice=(
    "SpeechRecognition>=3.10.0"
    "PyAudio>=0.2.14"
    "gTTS>=2.5.0"
    "pygame>=2.5.0"
  )

  local pkgs_dev=(
    "pytest>=7.0.0"
    "black>=24.0.0"
    "mypy>=1.0.0"
    "ruff>=0.1.0"
  )

  local all_pkgs=("${pkgs_core[@]}")
  if ! $NO_VOICE && ! $IS_TERMUX; then
    all_pkgs+=("${pkgs_voice[@]}")
  fi
  if $DEV_MODE; then
    all_pkgs+=("${pkgs_dev[@]}")
  fi

  local total=${#all_pkgs[@]}
  local count=0
  for pkg in "${all_pkgs[@]}"; do
    count=$((count + 1))
    printf "  [%2d/%2d] %-40s" "$count" "$total" "$pkg"
    if "$PIP_CMD" install "$pkg" -q 2>/dev/null; then
      printf "${G}✓${RST}\n"
    else
      printf "${Y}⚠ falhou — continuando${RST}\n"
    fi
  done

  log_ok "Bibliotecas Python instaladas."
}

# ─── Verificação pós-instalação ────────────────────────────────────────────────
verify_install() {
  log_section "Verificando instalação"

  local checks=(
    "flask"
    "flask_login"
    "werkzeug"
    "requests"
    "zeroconf"
    "paramiko"
  )

  if ! $NO_VOICE && ! $IS_TERMUX; then
    checks+=("speech_recognition" "gtts" "pygame")
  fi

  local ok=true
  for mod in "${checks[@]}"; do
    if "$PYTHON_CMD" -c "import ${mod}" 2>/dev/null; then
      local ver
      ver="$("$PYTHON_CMD" -c "import ${mod}; print(getattr(${mod}, '__version__', 'ok'))" 2>/dev/null || echo "ok")"
      printf "  ${G}✓${RST} %-30s %s\n" "${mod}" "${ver}"
    else
      printf "  ${R}✗${RST} %-30s ${R}FALHOU${RST}\n" "${mod}"
      ok=false
    fi
  done

  if $ok; then
    log_ok "Todas as verificações passaram."
  else
    log_warn "Algumas verificações falharam — a instalação pode estar incompleta."
  fi
}

# ─── Chave SSH ─────────────────────────────────────────────────────────────────
setup_ssh() {
  if $NO_SSH_KEY || $IS_TERMUX; then return; fi

  log_section "Configurando chave SSH"

  local ssh_key="${HOME}/.ssh/id_rsa"
  mkdir -p "${HOME}/.ssh" && chmod 700 "${HOME}/.ssh"

  if [[ -f "${ssh_key}" ]]; then
    log_info "Chave SSH já existe: ${ssh_key}"
  else
    log_info "Gerando chave RSA 4096 bits..."
    ssh-keygen -t rsa -b 4096 -f "${ssh_key}" -N "" -C "k7-core@$(hostname)" -q
    chmod 600 "${ssh_key}" && chmod 644 "${ssh_key}.pub"
    log_ok "Chave gerada: ${ssh_key}"
    log_info "Chave pública:"
    printf "  ${DIM}%s${RST}\n" "$(cat "${ssh_key}.pub")"
    printf "\n  ${BOLD}Para distribuir:${RST} ssh-copy-id -i ${ssh_key}.pub USUARIO@IP_DO_NO\n"
  fi
}

# ─── Configura config.py ───────────────────────────────────────────────────────
configure_node() {
  log_section "Configurando nó"

  local cfg="${INSTALL_DIR}/config.py"
  if [[ ! -f "${cfg}" ]]; then
    log_warn "config.py não encontrado em ${INSTALL_DIR} — pule esta etapa."
    return
  fi

  # Patch do NODE_TYPE se diferente do padrão
  if [[ "${NODE_TYPE}" != "seven" ]]; then
    log_info "Configurando NODE_TYPE = \"${NODE_TYPE}\"..."
    if command -v sed &>/dev/null; then
      sed -i.bak "s/^NODE_TYPE:.*= .*/NODE_TYPE: str = \"${NODE_TYPE}\"/" "${cfg}"
      local names=("Seven" "Spark" "Mobile")
      local types=("seven" "spark" "mobile")
      local new_name="Seven"
      for i in "${!types[@]}"; do
        if [[ "${types[$i]}" == "${NODE_TYPE}" ]]; then
          new_name="${names[$i]}"
        fi
      done
      sed -i.bak "s/^ASSISTANT_NAME:.*= .*/ASSISTANT_NAME: str = \"${new_name}\"/" "${cfg}"
      rm -f "${cfg}.bak"
    fi
    log_ok "NODE_TYPE definido como: ${NODE_TYPE}"
  else
    log_ok "NODE_TYPE: seven (padrão)"
  fi
}

# ─── Scripts de execução ───────────────────────────────────────────────────────
create_run_scripts() {
  log_section "Criando scripts de execução"

  # run.sh genérico
  cat > "${INSTALL_DIR}/run.sh" << 'RUNSH'
#!/usr/bin/env bash
# k7-core | run.sh — Inicia o assistente
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  source ".venv/bin/activate"
fi

echo "k7-core v2.0 | $(python core.py --version 2>/dev/null || echo 'iniciando...')"
exec python core.py "$@"
RUNSH
  chmod +x "${INSTALL_DIR}/run.sh"

  # run_seven.sh
  cat > "${INSTALL_DIR}/run_seven.sh" << 'RUNSH'
#!/usr/bin/env bash
# k7-core | run_seven.sh — Inicia como nó Seven (Master)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f ".venv/bin/activate" ]] && source ".venv/bin/activate"
NODE_OVERRIDE=seven
python3 - "$@" << 'PYEOF'
import sys, config
config.NODE_TYPE      = "seven"
config.ASSISTANT_NAME = "Seven"
config.NODE_MODE      = "master"
import core; core.main()
PYEOF
RUNSH
  chmod +x "${INSTALL_DIR}/run_seven.sh"

  # run_spark.sh
  cat > "${INSTALL_DIR}/run_spark.sh" << 'RUNSH'
#!/usr/bin/env bash
# k7-core | run_spark.sh — Inicia como nó Spark (Worker)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f ".venv/bin/activate" ]] && source ".venv/bin/activate"
python3 - "$@" << 'PYEOF'
import sys, config
config.NODE_TYPE        = "spark"
config.ASSISTANT_NAME   = "Spark"
config.NODE_MODE        = "worker"
config.ENABLE_DASHBOARD = False
import core; core.main()
PYEOF
RUNSH
  chmod +x "${INSTALL_DIR}/run_spark.sh"

  # Serviço systemd (Linux não-Termux)
  if ! $IS_TERMUX && ! $IS_MACOS && command -v systemctl &>/dev/null; then
    local svc_file="${HOME}/.config/systemd/user/k7core.service"
    mkdir -p "$(dirname "${svc_file}")"
    cat > "${svc_file}" << SVCEOF
[Unit]
Description=k7-core Assistente Virtual v2.0
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/core.py
Restart=on-failure
RestartSec=10
StandardOutput=append:${INSTALL_DIR}/logs/${NODE_TYPE}.log
StandardError=append:${INSTALL_DIR}/logs/${NODE_TYPE}.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
SVCEOF
    systemctl --user daemon-reload 2>/dev/null || true
    log_ok "Serviço systemd criado: ${svc_file}"
    log_info "Para ativar: systemctl --user enable --now k7core"
  fi

  log_ok "Scripts de execução criados."
}

# ─── Resumo final ─────────────────────────────────────────────────────────────
print_summary() {
  local port=2026
  local dashboard_url="http://localhost:${port}/dashboard"

  printf "\n${BOLD}${G}"
  cat << 'EOF'
  ╔═══════════════════════════════════════════════════════╗
  ║          k7-core v2.0 instalado com sucesso!          ║
  ╚═══════════════════════════════════════════════════════╝
EOF
  printf "${RST}"

  printf "\n  ${BOLD}Diretório:${RST} %s\n" "${INSTALL_DIR}"
  printf "  ${BOLD}Nó:${RST}        %s\n" "${NODE_TYPE}"
  printf "  ${BOLD}Dashboard:${RST} %s\n\n" "${dashboard_url}"

  printf "  ${BOLD}Próximos passos:${RST}\n"
  printf "  ${C}1.${RST} Edite ${BOLD}config.py${RST} com seus IPs, MACs e segredos\n"
  printf "  ${C}2.${RST} Gere a credencial GitHub: ${BOLD}python updater.py --gen-cred${RST}\n"
  printf "  ${C}3.${RST} Crie seu usuário: ${BOLD}python manage_auth.py create-user${RST}\n"
  printf "  ${C}4.${RST} Inicie: ${BOLD}./run.sh${RST} ou ${BOLD}./run_${NODE_TYPE}.sh${RST}\n"

  if command -v systemctl &>/dev/null && ! $IS_TERMUX && ! $IS_MACOS; then
    printf "  ${C}5.${RST} Ou como serviço: ${BOLD}systemctl --user enable --now k7core${RST}\n"
  fi

  printf "\n  ${DIM}Credenciais padrão do dashboard: mestre / k7mestre${RST}\n\n"
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
  banner
  detect_env

  log_info "Sistema: $(uname -s -r)"
  log_info "Nó alvo: ${NODE_TYPE}"
  log_info "Diretório: ${INSTALL_DIR}"
  printf "\n"

  check_prerequisites
  install_system_deps
  get_code
  setup_venv
  install_python_deps
  verify_install
  setup_ssh
  configure_node
  create_run_scripts
  print_summary
}

main "$@"
