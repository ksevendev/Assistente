#!/usr/bin/env bash
# =============================================================================
# k7-core | install.sh — Instalador Inteligente v3.0
# Repositório: https://github.com/ksevendev/Assistente
#
# Suporte: Debian 12, Ubuntu 24.04, Arch Linux, macOS, Android (Termux)
#
# INSTALAÇÃO RÁPIDA:
#   curl -fsSL https://raw.githubusercontent.com/ksevendev/Assistente/main/install.sh | bash
#
# INSTALAÇÃO LOCAL:
#   chmod +x install.sh && ./install.sh
#
# FLAGS (não-interativo / CI):
#   --version  2|3          Versão a instalar (padrão: interativo)
#   --node     seven|spark|mobile
#   --mode     master|worker
#   --dir      CAMINHO
#   --branch   NOME
#   --no-voice              Sem microfone/espeak
#   --no-ssh                Sem chave SSH
#   --yes                   Aceita tudo sem perguntar
#   --termux                Força modo Termux
# =============================================================================

set -euo pipefail
IFS=$'\n\t'

# ── Cores ────────────────────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' C='\033[0;96m'
B='\033[0;94m' M='\033[0;35m' BOLD='\033[1m' DIM='\033[2m' RST='\033[0m'

p()      { printf "%s" "$*"; }
pn()     { printf "%s\n" "$*"; }
info()   { printf "  ${C}•${RST}  %s\n" "$*"; }
ok()     { printf "  ${G}✓${RST}  %s\n" "$*"; }
warn()   { printf "  ${Y}⚠${RST}  %s\n" "$*"; }
err()    { printf "  ${R}✗${RST}  %s\n" "$*" >&2; }
step()   { printf "\n${BOLD}${C}  ━━━  %s${RST}\n\n" "$*"; }
ask()    { printf "  ${B}?${RST}  %s " "$*"; }
hr()     { printf "  ${DIM}%s${RST}\n" "────────────────────────────────────────────"; }

# ── Banner ────────────────────────────────────────────────────────────────────
banner() {
printf "\n${BOLD}${C}"
cat << 'BANNER'
  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗
  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝
  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗
  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝
BANNER
printf "${RST}"
printf "  ${BOLD}Assistente Virtual Distribuído${RST}\n"
printf "  ${DIM}https://github.com/ksevendev/Assistente${RST}\n"
printf "  ${DIM}https://ksevendev.github.io/Assistente/${RST}\n\n"
}

# ── Defaults ─────────────────────────────────────────────────────────────────
K7_VERSION=""          # 2 ou 3 — preenchido pelo wizard
NODE_TYPE=""           # seven | spark | mobile
NODE_MODE=""           # master | worker
INSTALL_DIR=""
GIT_BRANCH="main"
GIT_REPO="https://github.com/ksevendev/Assistente.git"
NO_VOICE=false
NO_SSH=false
AUTO_YES=false
FORCE_TERMUX=false
IS_TERMUX=false
IS_MACOS=false
IS_ARCH=false
PIP_CMD=""
PYTHON_CMD=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"

# Variáveis do wizard — config.py
W_ASSISTANT_NAME=""
W_ASSISTANT_IP_SEVEN=""
W_ASSISTANT_MAC_SEVEN=""
W_ASSISTANT_IP_SPARK=""
W_ASSISTANT_MAC_SPARK=""
W_ASSISTANT_IP_MOBILE=""
W_API_SECRET=""
W_ADMIN_SECRET=""
W_FLASK_KEY=""
W_DASH_USER="mestre"
W_DASH_PASS="k7mestre"
W_SSH_USER=""
W_GH_USER=""
W_GH_TOKEN=""
W_GH_REPO=""
W_OLLAMA_URL="http://localhost:11434"
W_OLLAMA_MODEL="llama3"
W_GEMINI_KEY=""
W_VOICE_ENGINE="espeak"

# ── Parse flags ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)   K7_VERSION="$2";    shift 2 ;;
    --node)      NODE_TYPE="$2";     shift 2 ;;
    --mode)      NODE_MODE="$2";     shift 2 ;;
    --dir)       INSTALL_DIR="$2";   shift 2 ;;
    --branch)    GIT_BRANCH="$2";    shift 2 ;;
    --no-voice)  NO_VOICE=true;      shift ;;
    --no-ssh)    NO_SSH=true;        shift ;;
    --yes|-y)    AUTO_YES=true;      shift ;;
    --termux)    FORCE_TERMUX=true;  shift ;;
    --help|-h)
      banner
      printf "  Flags:\n"
      printf "    --version  2|3       Versão a instalar\n"
      printf "    --node     seven|spark|mobile\n"
      printf "    --mode     master|worker\n"
      printf "    --dir      CAMINHO   Diretório de instalação\n"
      printf "    --yes                Sem confirmações interativas\n"
      printf "    --no-voice           Sem PyAudio/espeak\n"
      printf "    --no-ssh             Sem chave SSH\n"
      printf "    --termux             Força modo Termux\n\n"
      exit 0 ;;
    *) warn "Flag desconhecida: $1"; shift ;;
  esac
done

# ── Detecção de ambiente ──────────────────────────────────────────────────────
detect_env() {
  if $FORCE_TERMUX || [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
    IS_TERMUX=true
    [[ -z "$NODE_TYPE" ]] && NODE_TYPE="mobile"
    [[ -z "$INSTALL_DIR" ]] && INSTALL_DIR="${HOME}/Assistente"
    return
  fi
  [[ "$(uname -s)" == "Darwin" ]] && IS_MACOS=true
  [[ -f "/etc/arch-release" ]] && IS_ARCH=true
  [[ -z "$INSTALL_DIR" ]] && INSTALL_DIR="${HOME}/Assistente"
}

# ── Gerador de secrets aleatórios ─────────────────────────────────────────────
gen_secret() {
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null \
    || openssl rand -base64 32 2>/dev/null \
    || cat /proc/sys/kernel/random/uuid 2>/dev/null \
    || echo "k7-$(date +%s%N | sha256sum | head -c 32)"
}

gen_flask_key() {
  python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
    || openssl rand -hex 32 2>/dev/null \
    || echo "k7flask$(date +%s%N | sha256sum | head -c 28)"
}

# ── Leitura interativa com default ────────────────────────────────────────────
read_input() {
  local prompt="$1" default="${2:-}" var_name="$3" secret="${4:-false}"
  if $AUTO_YES && [[ -n "$default" ]]; then
    eval "$var_name='$default'"
    return
  fi
  if [[ -n "$default" ]]; then
    ask "${prompt} [${DIM}${default}${RST}]:"
  else
    ask "${prompt}:"
  fi
  local val=""
  if [[ "$secret" == "true" ]]; then
    IFS= read -rs val 2>/dev/null || read -r val
    echo
  else
    IFS= read -r val 2>/dev/null || read -r val
  fi
  val="${val:-$default}"
  eval "$var_name='$val'"
}

# ════════════════════════════════════════════════════════════════════════════
# WIZARD INTERATIVO
# ════════════════════════════════════════════════════════════════════════════
run_wizard() {
  banner

  # ── Escolha de versão ──────────────────────────────────────────────────
  if [[ -z "$K7_VERSION" ]]; then
    pn ""
    printf "  ${BOLD}Escolha a versão a instalar:${RST}\n\n"
    printf "  ${C}[2]${RST} ${BOLD}v2.0${RST} — Assistente Distribuído\n"
    printf "      ${DIM}Dashboard · mDNS · Terminal remoto · Auto-update${RST}\n\n"
    printf "  ${C}[3]${RST} ${BOLD}v3.0${RST} — Amigo Consciente ${Y}(recomendado)${RST}\n"
    printf "      ${DIM}v2.0 + IA com RAG · Memória de projetos · Chat de Mentoria${RST}\n"
    printf "      ${DIM}Requer: Ollama ou Gemini API + ~300 MB extras${RST}\n\n"
    ask "Versão [2/3]:"
    read -r K7_VERSION
    K7_VERSION="${K7_VERSION:-3}"
  fi

  if [[ "$K7_VERSION" != "2" ]] && [[ "$K7_VERSION" != "3" ]]; then
    err "Versão inválida: '$K7_VERSION'. Use 2 ou 3."
    exit 1
  fi

  hr

  # ── Escolha do nó ──────────────────────────────────────────────────────
  if [[ -z "$NODE_TYPE" ]]; then
    pn ""
    printf "  ${BOLD}Qual nó está sendo instalado?${RST}\n\n"
    printf "  ${C}[1]${RST} ${BOLD}Seven${RST}  — Notebook/PC principal ${C}(Ciano · Master)${RST}\n"
    printf "      ${DIM}Dashboard completo · STT · Auto-update · mDNS${RST}\n\n"
    printf "  ${M}[2]${RST} ${BOLD}Spark${RST}  — PC secundário ${M}(Laranja · Worker)${RST}\n"
    printf "      ${DIM}API headless · SSH · playerctl${RST}\n\n"
    printf "  ${B}[3]${RST} ${BOLD}Mobile${RST} — Android/Termux ${B}(Violeta · Worker)${RST}\n"
    printf "      ${DIM}TTS nativo · Notificações · Vibração${RST}\n\n"
    ask "Nó [1=seven, 2=spark, 3=mobile]:"
    read -r _choice
    case "${_choice:-1}" in
      1|seven)  NODE_TYPE="seven"  ;;
      2|spark)  NODE_TYPE="spark"  ;;
      3|mobile) NODE_TYPE="mobile" ;;
      *) NODE_TYPE="seven" ;;
    esac
  fi

  # Nome e modo baseados no nó
  case "$NODE_TYPE" in
    seven)  W_ASSISTANT_NAME="Seven"; [[ -z "$NODE_MODE" ]] && NODE_MODE="master" ;;
    spark)  W_ASSISTANT_NAME="Spark"; [[ -z "$NODE_MODE" ]] && NODE_MODE="worker" ;;
    mobile) W_ASSISTANT_NAME="Mobile";NODE_MODE="worker"; NO_VOICE=true ;;
  esac

  hr

  # ── Informações de rede ────────────────────────────────────────────────
  step "Configuração de Rede"
  pn "  ${DIM}Deixe em branco para usar descoberta automática via mDNS.${RST}"
  pn ""

  read_input "IP do nó Seven (ou deixe vazio)" "" W_ASSISTANT_IP_SEVEN
  if [[ "$NODE_TYPE" != "mobile" ]]; then
    read_input "MAC do nó Seven (para Wake-on-LAN)" "AA:BB:CC:DD:EE:01" W_ASSISTANT_MAC_SEVEN
    read_input "IP do nó Spark (ou deixe vazio)"    ""                  W_ASSISTANT_IP_SPARK
    read_input "MAC do nó Spark (para Wake-on-LAN)" "AA:BB:CC:DD:EE:02" W_ASSISTANT_MAC_SPARK
  fi

  # ── Segredos ───────────────────────────────────────────────────────────
  step "Segredos e Autenticação"
  pn "  ${DIM}Geraremos valores seguros automaticamente. Você pode personalizar.${RST}"
  pn ""

  local _api_default; _api_default="$(gen_secret)"
  local _adm_default; _adm_default="$(gen_secret)"
  local _fls_default; _fls_default="$(gen_flask_key)"

  if ! $AUTO_YES; then
    ask "Gerar segredos automaticamente? [S/n]:"
    read -r _auto_secrets
    if [[ "${_auto_secrets,,}" == "n" ]]; then
      read_input "API_SECRET (token inter-nós)"      "$_api_default" W_API_SECRET
      read_input "ADMIN_SECRET (operações root)"     "$_adm_default" W_ADMIN_SECRET
      read_input "FLASK_SECRET_KEY"                  "$_fls_default" W_FLASK_KEY
    else
      W_API_SECRET="$_api_default"
      W_ADMIN_SECRET="$_adm_default"
      W_FLASK_KEY="$_fls_default"
      ok "Segredos gerados automaticamente."
    fi
  else
    W_API_SECRET="$_api_default"
    W_ADMIN_SECRET="$_adm_default"
    W_FLASK_KEY="$_fls_default"
  fi

  pn ""
  read_input "Usuário do dashboard"   "mestre"   W_DASH_USER
  read_input "Senha do dashboard"     "k7mestre" W_DASH_PASS "true"

  # ── SSH ────────────────────────────────────────────────────────────────
  if ! $NO_SSH && ! $IS_TERMUX; then
    pn ""
    read_input "Usuário SSH nos nós remotos" "${USER:-usuario}" W_SSH_USER
  fi

  # ── Auto-update GitHub ─────────────────────────────────────────────────
  step "Auto-Update GitHub (opcional)"
  pn "  ${DIM}Configure para updates automáticos do repositório privado.${RST}"
  pn ""

  if ! $AUTO_YES; then
    ask "Configurar auto-update GitHub? [s/N]:"
    read -r _gh_choice
  else
    _gh_choice="n"
  fi

  if [[ "${_gh_choice,,}" == "s" ]]; then
    read_input "Usuário GitHub"             ""              W_GH_USER
    read_input "Personal Access Token"      ""              W_GH_TOKEN "true"
    read_input "Repositório (owner/repo)"   "ksevendev/Assistente" W_GH_REPO
  else
    W_GH_USER="ksevendev"
    W_GH_TOKEN=""
    W_GH_REPO="ksevendev/Assistente"
    info "Auto-update desabilitado (pode ser configurado depois em config.py)."
  fi

  # ── Configurações de IA (apenas v3) ────────────────────────────────────
  if [[ "$K7_VERSION" == "3" ]]; then
    step "Inteligência Artificial (v3.0)"
    pn "  ${DIM}Escolha o motor de IA para o Chat de Mentoria.${RST}\n"
    printf "  ${C}[1]${RST} ${BOLD}Ollama${RST} ${G}(recomendado)${RST} — local, privado, grátis\n"
    printf "      ${DIM}Instale: curl -fsSL https://ollama.com/install.sh | sh${RST}\n\n"
    printf "  ${C}[2]${RST} ${BOLD}Gemini API${RST} — Google, requer chave API\n"
    printf "      ${DIM}https://aistudio.google.com/app/apikey${RST}\n\n"
    printf "  ${C}[3]${RST} ${BOLD}Fallback${RST} — só RAG, sem LLM (resposta limitada)\n\n"

    if ! $AUTO_YES; then
      ask "Motor de IA [1/2/3]:"
      read -r _ia_choice
    else
      _ia_choice="1"
    fi

    case "${_ia_choice:-1}" in
      1)
        read_input "URL do Ollama"   "http://localhost:11434" W_OLLAMA_URL
        read_input "Modelo Ollama"   "llama3"                 W_OLLAMA_MODEL
        ;;
      2)
        read_input "Chave Gemini API" "" W_GEMINI_KEY "true"
        ;;
      3)
        info "Usando fallback RAG sem LLM."
        ;;
    esac
  fi

  # ── Diretório ─────────────────────────────────────────────────────────
  pn ""
  read_input "Diretório de instalação" "$INSTALL_DIR" INSTALL_DIR
}

# ════════════════════════════════════════════════════════════════════════════
# GERAÇÃO DO config.py
# ════════════════════════════════════════════════════════════════════════════
generate_config() {
  local cfg_path="${INSTALL_DIR}/config.py"
  info "Gerando ${cfg_path}..."

  # Gera GH_CREDENTIAL em Base64 (se credenciais fornecidas)
  local gh_cred=""
  if [[ -n "$W_GH_USER" ]] && [[ -n "$W_GH_TOKEN" ]] && [[ -n "$W_GH_REPO" ]]; then
    gh_cred="$(python3 -c "
import base64
raw = '${W_GH_USER}:${W_GH_TOKEN}:${W_GH_REPO}'
print(base64.b64encode(raw.encode()).decode())
" 2>/dev/null || echo "")"
  fi
  [[ -z "$gh_cred" ]] && gh_cred="CONFIGURE_AQUI_COM_python_updater_py_gen-cred"

  local enable_update="True"
  [[ -z "$W_GH_TOKEN" ]] && enable_update="False"

  # Specs baseados no nó
  local node_specs=""
  case "$NODE_TYPE" in
    seven)  node_specs="Notebook · $(uname -s 2>/dev/null || echo Linux)" ;;
    spark)  node_specs="PC Desktop · Worker" ;;
    mobile) node_specs="Android · Termux" ;;
  esac

  local enable_dashboard="True"
  [[ "$NODE_MODE" == "worker" ]] && enable_dashboard="False"
  [[ "$NODE_TYPE" == "mobile" ]] && enable_dashboard="False"

  # Configurações de IA (v3)
  local v3_block=""
  if [[ "$K7_VERSION" == "3" ]]; then
    v3_block="
# =============================================================================
# ⓰  INTELIGÊNCIA ARTIFICIAL (v3.0)
# =============================================================================

# Motor LLM — configurado pelo instalador
# Prioridade: Ollama → Gemini → Fallback RAG
OLLAMA_URL:   str = \"${W_OLLAMA_URL}\"
OLLAMA_MODEL: str = \"${W_OLLAMA_MODEL}\"
GEMINI_API_KEY: str = \"${W_GEMINI_KEY}\"

# Projetos para indexar (edite com seus caminhos reais)
import pathlib as _pathlib
_HOME = str(_pathlib.Path.home())
AI_PROJECTS: list = [
    {\"name\": \"k7-core\",  \"path\": BASE_DIR,                         \"description\": \"Assistente Virtual Distribuído\",     \"tech_stack\": [\"python\",\"flask\",\"zeroconf\"]},
    {\"name\": \"K7 Barber\",\"path\": _HOME + \"/projetos/k7-barber\",   \"description\": \"Sistema de agendamento barbearia\",   \"tech_stack\": [\"python\",\"django\",\"postgresql\"]},
    {\"name\": \"KSigner\",  \"path\": _HOME + \"/projetos/ksigner\",     \"description\": \"Assinatura digital de documentos\",   \"tech_stack\": [\"python\",\"fastapi\",\"jwt\"]},
    {\"name\": \"SYNAP\",    \"path\": _HOME + \"/projetos/synap\",       \"description\": \"Análise de padrões neurológicos\",    \"tech_stack\": [\"python\",\"numpy\",\"pytorch\"]},
    {\"name\": \"Keryon\",   \"path\": _HOME + \"/projetos/keryon\",      \"description\": \"Orquestração de tarefas distribuídas\",\"tech_stack\": [\"python\",\"asyncio\",\"docker\"]},
]
"
  fi

  cat > "$cfg_path" << CFGEOF
# =============================================================================
# k7-core | config.py  — v${K7_VERSION}.0
# Gerado pelo instalador em $(date '+%Y-%m-%d %H:%M:%S')
# Nó: ${NODE_TYPE} | Modo: ${NODE_MODE}
#
# EDITE ESTE ARQUIVO para personalizar o sistema.
# Referência completa: https://ksevendev.github.io/Assistente/
# =============================================================================

import os
import socket

# =============================================================================
# ❶  IDENTIDADE DO NÓ
# =============================================================================

NODE_TYPE:      str = "${NODE_TYPE}"
ASSISTANT_NAME: str = "${W_ASSISTANT_NAME}"
ASSISTANT_LANG: str = "pt-BR"
K7_VERSION:     str = "${K7_VERSION}.0"

# =============================================================================
# ❷  MODO DE OPERAÇÃO
# =============================================================================

NODE_MODE:        str  = "${NODE_MODE}"
ENABLE_DASHBOARD: bool = ${enable_dashboard}

def is_master() -> bool:
    return ENABLE_DASHBOARD and NODE_MODE == "master"

def is_worker() -> bool:
    return not is_master()

# =============================================================================
# ❸  DESCOBERTA mDNS / Zeroconf
# =============================================================================

DISCOVERY_SERVICE_TYPE:     str   = "_k7core._tcp.local."
DISCOVERY_NODE_NAME:        str   = ""
DISCOVERY_TTL:              int   = 60
DISCOVERY_BOOT_WAIT:        float = 2.0
DISCOVERY_RECHECK_INTERVAL: int   = 30

def get_discovery_name() -> str:
    base = DISCOVERY_NODE_NAME or f"k7-{NODE_TYPE}"
    return f"{base}.{DISCOVERY_SERVICE_TYPE}"

# =============================================================================
# ❹  API SERVER
# =============================================================================

API_HOST:     str = "0.0.0.0"
API_PORT:     int = 2026
API_SECRET:   str = "${W_API_SECRET}"
ADMIN_SECRET: str = "${W_ADMIN_SECRET}"

# =============================================================================
# ❺  PALETAS DE COR
# =============================================================================

NODE_PALETTES: dict = {
    "seven":   {"label":"Cyan",   "ansi_primary":"\033[96m","ansi_secondary":"\033[36m","hex_primary":"#00E5FF","hex_secondary":"#00B8D4","hex_bg":"#00E5FF14","hex_glow":"#00E5FF40"},
    "spark":   {"label":"Orange", "ansi_primary":"\033[91m","ansi_secondary":"\033[33m","hex_primary":"#FF6D00","hex_secondary":"#E65100","hex_bg":"#FF6D0014","hex_glow":"#FF6D0040"},
    "mobile":  {"label":"Violet", "ansi_primary":"\033[95m","ansi_secondary":"\033[35m","hex_primary":"#AA00FF","hex_secondary":"#7B00D4","hex_bg":"#AA00FF14","hex_glow":"#AA00FF40"},
    "default": {"label":"Gray",   "ansi_primary":"\033[97m","ansi_secondary":"\033[37m","hex_primary":"#90A4AE","hex_secondary":"#607D8B","hex_bg":"#90A4AE14","hex_glow":"#90A4AE30"},
}

def get_palette(node_type: str = None) -> dict:
    return NODE_PALETTES.get(node_type or NODE_TYPE, NODE_PALETTES["default"])

# =============================================================================
# ❻  TOPOLOGIA DE REDE
# =============================================================================

NETWORK_NODES: dict = {
    "seven": {
        "name":  "Seven",
        "ip":    "${W_ASSISTANT_IP_SEVEN}",
        "port":  2026,
        "mac":   "${W_ASSISTANT_MAC_SEVEN}",
        "type":  "desktop",
        "specs": "${node_specs}",
        "icon":  "laptop",
    },
    "spark": {
        "name":  "Spark",
        "ip":    "${W_ASSISTANT_IP_SPARK}",
        "port":  2026,
        "mac":   "${W_ASSISTANT_MAC_SPARK}",
        "type":  "desktop",
        "specs": "PC Desktop · Worker",
        "icon":  "desktop_windows",
    },
    "mobile": {
        "name":  "Mobile",
        "ip":    "${W_ASSISTANT_IP_MOBILE}",
        "port":  2026,
        "mac":   "",
        "type":  "mobile",
        "specs": "Android · Termux",
        "icon":  "smartphone",
    },
}

def get_node_info(node_type: str = None) -> dict:
    return NETWORK_NODES.get(node_type or NODE_TYPE, {})

def get_peer_nodes() -> dict:
    return {k: v for k, v in NETWORK_NODES.items() if k != NODE_TYPE}

def get_nodes_with_palette() -> list:
    result = []
    for nt, ni in NETWORK_NODES.items():
        palette = NODE_PALETTES.get(nt, NODE_PALETTES["default"])
        entry   = {"node_type": nt, **ni}
        for k, v in palette.items():
            if k.startswith("hex_") or k == "label":
                entry[f"color_{k}"] = v
        result.append(entry)
    return result

# =============================================================================
# ❼  AUTENTICAÇÃO DO DASHBOARD
# =============================================================================

AUTH_DB_PATH:     str = ""
FLASK_SECRET_KEY: str = "${W_FLASK_KEY}"
DEFAULT_USER:     str = "${W_DASH_USER}"
DEFAULT_PASSWORD: str = "${W_DASH_PASS}"
SESSION_LIFETIME: int = 3600 * 8

# =============================================================================
# ❽  AUTO-UPDATE — GitHub
# =============================================================================

GH_CREDENTIAL:        str  = "${gh_cred}"
ENABLE_AUTO_UPDATE:   bool = ${enable_update}
GH_BRANCH:            str  = "${GIT_BRANCH}"
GH_CHECK_INTERVAL:    int  = 3600
GH_RESTART_ON_UPDATE: bool = True
GH_LOCK_FILE:         str  = ""

# =============================================================================
# ❾  VOZ / TTS
# =============================================================================

VOICE_ENGINE:  str = "${W_VOICE_ENGINE}"
ESPEAK_VOICE:  str = "pt"
ESPEAK_SPEED:  int = 150
ESPEAK_VOLUME: int = 180

# =============================================================================
# ❿  SSH
# =============================================================================

SSH_USER:    str = "${W_SSH_USER:-usuario}"
SSH_KEY:     str = os.path.expanduser("~/.ssh/id_rsa")
SSH_TIMEOUT: int = 10
SSH_PORT:    int = 22

PC_IP:  str = NETWORK_NODES["spark"].get("ip", "")
PC_MAC: str = NETWORK_NODES["spark"].get("mac", "")
REMOTE_PCS: dict = {
    k: (v.get("ip", ""), v.get("mac", ""))
    for k, v in NETWORK_NODES.items() if v.get("mac")
}

# =============================================================================
# ⓫  WAKE-ON-LAN
# =============================================================================

WOL_PORT:      int = 9
WOL_BROADCAST: str = "255.255.255.255"

# =============================================================================
# ⓬  MICROFONE / STT
# =============================================================================

MIC_ENERGY_THRESHOLD:  int   = 400
MIC_TIMEOUT:           float = 5.0
MIC_PHRASE_TIME_LIMIT: float = 12.0
MIC_PAUSE_THRESHOLD:   float = 0.9

# =============================================================================
# ⓭  DETECÇÃO DE AMBIENTE
# =============================================================================

def is_android() -> bool:
    return (
        "ANDROID_ROOT" in os.environ
        or "TERMUX_VERSION" in os.environ
        or os.path.exists("/data/data/com.termux")
    )

def is_headless() -> bool:
    return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")

IS_ANDROID:  bool = is_android()
IS_HEADLESS: bool = is_headless()

if IS_ANDROID:
    VOICE_ENGINE     = "termux"
    NODE_TYPE        = "mobile"
    ASSISTANT_NAME   = NETWORK_NODES["mobile"]["name"]
    NODE_MODE        = "worker"
    ENABLE_DASHBOARD = False

# =============================================================================
# ⓮  DIRETÓRIOS
# =============================================================================

BASE_DIR:      str = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR:  str = os.path.join(BASE_DIR, "commands")
TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
LOG_DIR:       str = os.path.join(BASE_DIR, "logs")
TEMP_DIR:      str = os.path.join(BASE_DIR, "tmp")
DATA_DIR:      str = os.path.join(BASE_DIR, "data")
LOG_FILE:      str = os.path.join(LOG_DIR, f"{NODE_TYPE}.log")
AUTH_DB_PATH        = os.path.join(DATA_DIR, "k7auth.db")
GH_LOCK_FILE        = os.path.join(DATA_DIR, ".update.lock")

# =============================================================================
# ⓯  LOGGING
# =============================================================================

LOG_LEVEL:      str  = "INFO"
LOG_TO_FILE:    bool = True
LOG_TO_CONSOLE: bool = True
${v3_block}
# =============================================================================
# Cria diretórios ao importar
# =============================================================================
for _d in (LOG_DIR, TEMP_DIR, DATA_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)
CFGEOF

  ok "config.py gerado."
}

# ════════════════════════════════════════════════════════════════════════════
# DEPS DE SISTEMA
# ════════════════════════════════════════════════════════════════════════════
install_system_deps() {
  step "Dependências do Sistema"

  if $IS_TERMUX; then
    info "Modo Termux — atualizando pacotes..."
    pkg update -y -q
    pkg install -y python python-pip git -q
    pkg install -y termux-api 2>/dev/null || warn "Termux:API não disponível — instale pela F-Droid."
    ok "Pacotes Termux instalados."
    return
  fi

  if $IS_MACOS; then
    command -v brew &>/dev/null || {
      info "Instalando Homebrew..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    }
    brew update -q
    for p in python3 git portaudio ffmpeg espeak; do
      brew list "$p" &>/dev/null || brew install "$p" -q
    done
    ok "Pacotes Homebrew instalados."
    return
  fi

  if $IS_ARCH; then
    sudo pacman -Sy --noconfirm --needed \
      python python-pip git espeak-ng portaudio ffmpeg openssh playerctl base-devel 2>/dev/null | tail -1 || true
    ok "Pacotes Arch instalados."
    return
  fi

  # Debian / Ubuntu
  DEBIAN_FRONTEND=noninteractive sudo apt-get update -qq

  local pkgs=(
    python3 python3-pip python3-venv python3-dev
    git curl espeak espeak-ng espeak-ng-data
    portaudio19-dev libportaudio2 alsa-utils libasound2-dev
    build-essential gcc pkg-config
    openssh-client net-tools playerctl ffmpeg
  )
  DEBIAN_FRONTEND=noninteractive sudo apt-get install -y "${pkgs[@]}" \
    --no-install-recommends -qq 2>&1 | grep -E "^(Get:|Inst|Err)" | head -10 || true
  ok "Pacotes apt instalados."
}

# ════════════════════════════════════════════════════════════════════════════
# CLONAR / ATUALIZAR REPOSITÓRIO
# ════════════════════════════════════════════════════════════════════════════
get_code() {
  step "Código-fonte"

  if [[ -f "${SCRIPT_DIR}/core.py" ]]; then
    info "Usando código do diretório atual: ${SCRIPT_DIR}"
    INSTALL_DIR="${SCRIPT_DIR}"
    return
  fi

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    info "Atualizando repositório em ${INSTALL_DIR}..."
    git -C "${INSTALL_DIR}" fetch origin "${GIT_BRANCH}" -q
    git -C "${INSTALL_DIR}" reset --hard "origin/${GIT_BRANCH}" -q
    ok "Repositório atualizado."
    return
  fi

  info "Clonando ${GIT_REPO}..."
  mkdir -p "$(dirname "${INSTALL_DIR}")"
  git clone --depth 1 --branch "${GIT_BRANCH}" "${GIT_REPO}" "${INSTALL_DIR}" -q
  ok "Repositório clonado."
}

# ════════════════════════════════════════════════════════════════════════════
# VENV + PYTHON DEPS
# ════════════════════════════════════════════════════════════════════════════
setup_venv() {
  step "Ambiente Python"
  local py; py="$(command -v python3 2>/dev/null || command -v python)"

  if $IS_TERMUX; then
    PIP_CMD="pip"; PYTHON_CMD="python"
  else
    local venv="${INSTALL_DIR}/.venv"
    [[ -d "$venv" ]] || { info "Criando .venv..."; "$py" -m venv "$venv"; }
    PIP_CMD="${venv}/bin/pip"
    PYTHON_CMD="${venv}/bin/python"
  fi

  "$PIP_CMD" install --upgrade pip setuptools wheel -q
  ok "pip $($PIP_CMD --version | awk '{print $2}')"
}

install_python_deps() {
  step "Bibliotecas Python"

  local core=(
    "flask>=3.0.0" "flask-login>=0.6.3" "werkzeug>=3.0.0"
    "requests>=2.31.0" "zeroconf>=0.131.0" "paramiko>=3.4.0"
  )
  local voice=(
    "SpeechRecognition>=3.10.0" "PyAudio>=0.2.14"
    "gTTS>=2.5.0" "pygame>=2.5.0"
  )
  local ai=(
    "chromadb>=0.5.0"
    "sentence-transformers>=3.0.0"
  )

  local pkgs=("${core[@]}")
  ! $NO_VOICE && ! $IS_TERMUX && pkgs+=("${voice[@]}")
  [[ "$K7_VERSION" == "3" ]] && ! $IS_TERMUX && pkgs+=("${ai[@]}")

  local total=${#pkgs[@]} count=0
  for pkg in "${pkgs[@]}"; do
    count=$((count+1))
    printf "  [%2d/%2d] %-42s" "$count" "$total" "$pkg"
    if "$PIP_CMD" install "$pkg" -q 2>/dev/null; then
      printf "${G}✓${RST}\n"
    else
      printf "${Y}⚠${RST}\n"
    fi
  done
  ok "Bibliotecas instaladas."
}

# ════════════════════════════════════════════════════════════════════════════
# CHAVE SSH
# ════════════════════════════════════════════════════════════════════════════
setup_ssh() {
  $NO_SSH && return
  $IS_TERMUX && return
  step "Chave SSH"
  local key="${HOME}/.ssh/id_rsa"
  mkdir -p "${HOME}/.ssh" && chmod 700 "${HOME}/.ssh"
  if [[ -f "$key" ]]; then
    info "Chave SSH já existe: $key"
  else
    ssh-keygen -t rsa -b 4096 -f "$key" -N "" -C "k7@$(hostname)" -q
    chmod 600 "$key" && chmod 644 "$key.pub"
    ok "Chave RSA gerada: $key"
    printf "\n  ${DIM}Chave pública (copie para os outros nós):\n"
    printf "  %s${RST}\n" "$(cat "$key.pub")"
    printf "  Comando: ${BOLD}ssh-copy-id -i $key.pub ${W_SSH_USER}@IP_DO_NO${RST}\n\n"
  fi
}

# ════════════════════════════════════════════════════════════════════════════
# SCRIPTS DE EXECUÇÃO
# ════════════════════════════════════════════════════════════════════════════
create_run_scripts() {
  step "Scripts de Execução"

  # run.sh genérico
  cat > "${INSTALL_DIR}/run.sh" << 'EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
[[ -f ".venv/bin/activate" ]] && source ".venv/bin/activate"
exec python core.py "$@"
EOF
  chmod +x "${INSTALL_DIR}/run.sh"

  # Scripts por nó
  for _node in seven spark; do
    local _name; _name="$(echo "${_node}" | sed 's/./\u&/')" 2>/dev/null || _name="${_node}"
    local _mode="master"; [[ "$_node" == "spark" ]] && _mode="worker"
    cat > "${INSTALL_DIR}/run_${_node}.sh" << EOF
#!/usr/bin/env bash
cd "\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
[[ -f ".venv/bin/activate" ]] && source ".venv/bin/activate"
python3 -c "
import config
config.NODE_TYPE = '${_node}'
config.ASSISTANT_NAME = '$(echo ${_node} | awk '{print toupper(substr($0,1,1))tolower(substr($0,2))}')'
config.NODE_MODE = '${_mode}'
import core; core.main()
" "\$@"
EOF
    chmod +x "${INSTALL_DIR}/run_${_node}.sh"
    ok "run_${_node}.sh criado."
  done

  # Serviço systemd (Linux)
  if command -v systemctl &>/dev/null && ! $IS_TERMUX && ! $IS_MACOS; then
    local svc="${HOME}/.config/systemd/user/k7core.service"
    mkdir -p "$(dirname "$svc")"
    cat > "$svc" << EOF
[Unit]
Description=k7-core v${K7_VERSION}.0 — ${W_ASSISTANT_NAME}
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/core.py
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload 2>/dev/null || true
    ok "Serviço systemd: $svc"
    info "Para ativar: systemctl --user enable --now k7core"
  fi
}

# ════════════════════════════════════════════════════════════════════════════
# INDEXAÇÃO v3
# ════════════════════════════════════════════════════════════════════════════
run_indexing() {
  [[ "$K7_VERSION" != "3" ]] && return
  [[ ! -f "${INSTALL_DIR}/knowledge_base.py" ]] && return

  step "Indexação de Conhecimento (v3.0)"
  info "Indexando projetos em background (pode demorar alguns minutos)..."
  cd "${INSTALL_DIR}"
  "$PYTHON_CMD" knowledge_base.py --index 2>&1 | tail -5 || warn "Indexação falhou — execute manualmente: python knowledge_base.py --index"
  ok "Indexação iniciada."
}

# ════════════════════════════════════════════════════════════════════════════
# RESUMO FINAL
# ════════════════════════════════════════════════════════════════════════════
print_summary() {
  local col="${C}"
  [[ "$NODE_TYPE" == "spark" ]]  && col="${M}"
  [[ "$NODE_TYPE" == "mobile" ]] && col="${B}"

  printf "\n${BOLD}${G}"
  cat << 'EOF'
  ╔══════════════════════════════════════════════════════════╗
  ║             k7-core instalado com sucesso!               ║
  ╚══════════════════════════════════════════════════════════╝
EOF
  printf "${RST}"
  printf "\n  ${BOLD}Versão:${RST}     v${K7_VERSION}.0\n"
  printf "  ${BOLD}Nó:${RST}         ${col}${W_ASSISTANT_NAME}${RST} (${NODE_TYPE} · ${NODE_MODE})\n"
  printf "  ${BOLD}Diretório:${RST}  ${INSTALL_DIR}\n"
  printf "  ${BOLD}Dashboard:${RST}  http://localhost:2026/dashboard\n"
  printf "  ${BOLD}Login:${RST}      ${W_DASH_USER} / [senha configurada]\n\n"
  printf "  ${BOLD}Próximos passos:${RST}\n"
  printf "  ${C}1${RST} Revise ${BOLD}config.py${RST} — especialmente IPs e MACs\n"
  printf "  ${C}2${RST} Inicie: ${BOLD}./run.sh${RST}  ou  ${BOLD}./run_${NODE_TYPE}.sh${RST}\n"
  [[ "$K7_VERSION" == "3" ]] && printf "  ${C}3${RST} Instale Ollama: ${BOLD}ollama pull llama3 && ollama serve${RST}\n"
  printf "\n  ${DIM}Docs: https://ksevendev.github.io/Assistente/${RST}\n\n"
}

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
main() {
  detect_env
  run_wizard
  install_system_deps
  get_code
  setup_venv
  install_python_deps
  generate_config
  setup_ssh
  create_run_scripts
  run_indexing
  print_summary
}

main "$@"
