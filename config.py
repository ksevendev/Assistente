# =============================================================================
# k7-core | config.py  — v2.0 (Dynamic Discovery + Auto-Update)
#
# FONTES ÚNICAS DE VERDADE:
#   NODE_PALETTES  → cores para logs ANSI e dashboard web
#   NETWORK_NODES  → topologia estática (seeds / fallback para mDNS)
#   NODE_MODE      → determina o que o Flask carrega ao subir
#   GH_CREDENTIAL  → blob opaco Base64 com credenciais do repositório privado
#
# SOBRE GH_CREDENTIAL:
#   Armazena "usuario:token:owner/repositorio" codificado em Base64.
#   Este arquivo NÃO contém nenhuma lógica de decodificação — toda a
#   lógica de separação dos campos vive exclusivamente em updater.py,
#   distribuída em três funções independentes entre si.
#
#   Como gerar o valor:
#       python3 -c "
#       import base64
#       raw = 'meu_user:ghp_TokenAqui:meu_user/k7-core'
#       print(base64.b64encode(raw.encode()).decode())
#       "
# =============================================================================

import os
import socket

# =============================================================================
# ❶  IDENTIDADE DO NÓ
# =============================================================================

NODE_TYPE:      str = "seven"   # "seven" | "spark" | "mobile"
ASSISTANT_NAME: str = "Seven"
ASSISTANT_LANG: str = "pt-BR"

# =============================================================================
# ❷  MODO DE OPERAÇÃO
# =============================================================================

NODE_MODE:        str  = "master"   # "master" | "worker"
ENABLE_DASHBOARD: bool = True

def is_master() -> bool:
    return ENABLE_DASHBOARD and NODE_MODE == "master"

def is_worker() -> bool:
    return not is_master()

# =============================================================================
# ❸  DESCOBERTA mDNS / Zeroconf
# =============================================================================

DISCOVERY_SERVICE_TYPE:   str   = "_k7core._tcp.local."
DISCOVERY_NODE_NAME:      str   = ""
DISCOVERY_TTL:            int   = 60
DISCOVERY_BOOT_WAIT:      float = 2.0
DISCOVERY_RECHECK_INTERVAL: int = 30

def get_discovery_name() -> str:
    base = DISCOVERY_NODE_NAME or f"k7-{NODE_TYPE}"
    return f"{base}.{DISCOVERY_SERVICE_TYPE}"

# =============================================================================
# ❹  API SERVER
# =============================================================================

API_HOST:     str = "0.0.0.0"
API_PORT:     int = 2026
API_SECRET:   str = "k7-secret-local-network"
ADMIN_SECRET: str = "k7-admin-secret-change-this"

# =============================================================================
# ❺  PALETAS DE COR
# =============================================================================

NODE_PALETTES: dict = {
    "seven": {
        "label":          "Cyan",
        "ansi_primary":   "\033[96m",
        "ansi_secondary": "\033[36m",
        "hex_primary":    "#00E5FF",
        "hex_secondary":  "#00B8D4",
        "hex_bg":         "#00E5FF14",
        "hex_glow":       "#00E5FF40",
    },
    "spark": {
        "label":          "Orange",
        "ansi_primary":   "\033[91m",
        "ansi_secondary": "\033[33m",
        "hex_primary":    "#FF6D00",
        "hex_secondary":  "#E65100",
        "hex_bg":         "#FF6D0014",
        "hex_glow":       "#FF6D0040",
    },
    "mobile": {
        "label":          "Violet",
        "ansi_primary":   "\033[95m",
        "ansi_secondary": "\033[35m",
        "hex_primary":    "#AA00FF",
        "hex_secondary":  "#7B00D4",
        "hex_bg":         "#AA00FF14",
        "hex_glow":       "#AA00FF40",
    },
    "default": {
        "label":          "Gray",
        "ansi_primary":   "\033[97m",
        "ansi_secondary": "\033[37m",
        "hex_primary":    "#90A4AE",
        "hex_secondary":  "#607D8B",
        "hex_bg":         "#90A4AE14",
        "hex_glow":       "#90A4AE30",
    },
}

def get_palette(node_type: str = None) -> dict:
    return NODE_PALETTES.get(node_type or NODE_TYPE, NODE_PALETTES["default"])

# =============================================================================
# ❻  TOPOLOGIA ESTÁTICA (seeds / fallback — IPs opcionais)
# =============================================================================

NETWORK_NODES: dict = {
    "seven": {
        "name":  "Seven",
        "ip":    "",
        "port":  2026,
        "mac":   "AA:BB:CC:DD:EE:01",
        "type":  "desktop",
        "specs": "Notebook · Debian 12",
        "icon":  "laptop",
    },
    "spark": {
        "name":  "Spark",
        "ip":    "",
        "port":  2026,
        "mac":   "AA:BB:CC:DD:EE:02",
        "type":  "desktop",
        "specs": "PC Desktop · 16GB RAM",
        "icon":  "desktop_windows",
    },
    "mobile": {
        "name":  "Mobile",
        "ip":    "",
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
    for node_type, node_info in NETWORK_NODES.items():
        palette = NODE_PALETTES.get(node_type, NODE_PALETTES["default"])
        entry   = {"node_type": node_type, **node_info}
        for k, v in palette.items():
            if k.startswith("hex_") or k == "label":
                entry[f"color_{k}"] = v
        result.append(entry)
    return result

# =============================================================================
# ❼  AUTENTICAÇÃO DO DASHBOARD
# =============================================================================

AUTH_DB_PATH:     str = ""   # resolvido após BASE_DIR
FLASK_SECRET_KEY: str = "k7-dashboard-secret-change-in-production-abc123xyz"
DEFAULT_USER:     str = "mestre"
DEFAULT_PASSWORD: str = "k7mestre"
SESSION_LIFETIME: int = 3600 * 8

# =============================================================================
# ❽  AUTO-UPDATE — repositório privado GitHub
#
# GH_CREDENTIAL é um blob Base64 puro. Este arquivo não decodifica, não
# separa, não interpreta os campos. Toda essa lógica está em updater.py,
# dividida em funções propositalmente separadas e em locais distintos
# dentro do arquivo, dificultando a leitura do segredo como um todo.
#
# Formato antes de codificar: "usuario:token:owner/repositorio"
# Os dois primeiros ':' são os separadores de campo.
# O repositório pode conter '/' (ex: "myuser/my-repo") sem problema.
# =============================================================================

# ── blob opaco ── troque pelo valor gerado por: python updater.py --gen-cred
GH_CREDENTIAL: str = "bXlfdXNlcjpnaHBfVG9rZW5BcXVpOm15X3VzZXIvazctY29yZQ=="

# Liga/desliga o sistema de update sem apagar a credencial
ENABLE_AUTO_UPDATE:   bool = True

# Branch alvo do repositório
GH_BRANCH:            str  = "main"

# Segundos entre verificações periódicas automáticas (0 = somente manual)
GH_CHECK_INTERVAL:    int  = 3600

# Reiniciar o processo Python após aplicar o update com sucesso?
GH_RESTART_ON_UPDATE: bool = True

# Path do file-lock (preenchido após BASE_DIR estar definido)
GH_LOCK_FILE:         str  = ""

# =============================================================================
# ❾  VOZ / TTS
# =============================================================================

VOICE_ENGINE:  str = "espeak"
ESPEAK_VOICE:  str = "pt"
ESPEAK_SPEED:  int = 150
ESPEAK_VOLUME: int = 180

# =============================================================================
# ❿  SSH
# =============================================================================

SSH_USER:    str = "usuario"
SSH_KEY:     str = os.path.expanduser("~/.ssh/id_rsa")
SSH_TIMEOUT: int = 10
SSH_PORT:    int = 22

PC_IP:  str = NETWORK_NODES["spark"].get("ip", "")
PC_MAC: str = NETWORK_NODES["spark"].get("mac", "")

REMOTE_PCS: dict = {
    k: (v.get("ip", ""), v.get("mac", ""))
    for k, v in NETWORK_NODES.items()
    if v.get("mac")
}

# =============================================================================
# ⓫  WAKE-ON-LAN
# =============================================================================

WOL_PORT:      int = 9
WOL_BROADCAST: str = "255.255.255.255"

# =============================================================================
# ⓬  RECONHECIMENTO DE VOZ
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

# =============================================================================
# Cria diretórios necessários ao importar
# =============================================================================
for _d in (LOG_DIR, TEMP_DIR, DATA_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)
