# =============================================================================
# k7-core | config.py  — v4 (Dashboard + Auth)
#
# FONTE ÚNICA DE VERDADE:
#   NETWORK_NODES  →  toda a topologia da rede (IPs, portas, MACs)
#   NODE_PALETTES  →  cores usadas em logs, dashboard web e bordas dos cards
#
# O dashboard lê diretamente config.NETWORK_NODES e config.NODE_PALETTES
# para renderizar os cards — nenhuma cor ou IP é hardcoded no HTML.
# =============================================================================

import os

# =============================================================================
# ❶  IDENTIDADE DO NÓ  — altere para cada instância
# =============================================================================

NODE_TYPE:      str = "spark"       # "seven" | "spark" | "mobile"
ASSISTANT_NAME: str = "Spark"
ASSISTANT_LANG: str = "pt-BR"

# =============================================================================
# ❷  PALETAS DE COR  ← fonte única para logs E dashboard web
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
}

def get_palette(node_type: str = None) -> dict:
    return NODE_PALETTES.get(node_type or NODE_TYPE, NODE_PALETTES["seven"])

# =============================================================================
# ❸  TOPOLOGIA DA REDE  ← fonte única para API, engine e dashboard
# =============================================================================

NETWORK_NODES: dict = {
    "seven": {
        "name":  "Seven",
        "ip":    "192.168.3.12",
        "port":  7007,
        "mac":   "54:27:1E:8C:36:70",
        "type":  "desktop",
        "specs": "Notebook · 4GB RAM · Debian 12",
        "icon":  "laptop",
    },
    "spark": {
        "name":  "Spark",
        "ip":    "192.168.3.6",
        "port":  7007,
        "mac":   "00:E0:24:7E:14:E5",
        "type":  "desktop",
        "specs": "PC Desktop · 16GB RAM · Ubuntu 25.04",
        "icon":  "desktop_windows",
    },
    "mobile": {
        "name":  "Mobile",
        "ip":    "192.168.3.24",
        "port":  7007,
        "mac":   "C2:B5:22:C9:D0:40",
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
    """
    Funde NETWORK_NODES + NODE_PALETTES em uma lista de dicts.
    Consumido pelo dashboard para renderizar cards sem lógica no template.
    """
    result = []
    for node_type, node_info in NETWORK_NODES.items():
        palette = NODE_PALETTES.get(node_type, NODE_PALETTES["seven"])
        entry = {"node_type": node_type, **node_info}
        for k, v in palette.items():
            entry[f"color_{k}"] = v
        result.append(entry)
    return result

# =============================================================================
# ❹  API SERVER
# =============================================================================

API_HOST:       str = "0.0.0.0"
API_PORT:       int = 7007
API_SECRET:     str = "kseven-com-br"
DASHBOARD_PORT: int = 7007

# =============================================================================
# ❺  AUTENTICAÇÃO DO DASHBOARD
# =============================================================================

AUTH_DB_PATH:     str = ""   # resolvido após BASE_DIR
FLASK_SECRET_KEY: str = "kseven-com-br-spark"
DEFAULT_USER:     str = "mestre"
DEFAULT_PASSWORD: str = "k7mestre"
SESSION_LIFETIME: int = 3600 * 8

# =============================================================================
# ❻  VOZ / TTS
# =============================================================================

VOICE_ENGINE:  str = "espeak"
ESPEAK_VOICE:  str = "pt"
ESPEAK_SPEED:  int = 150
ESPEAK_VOLUME: int = 180

# =============================================================================
# ❼  SSH
# =============================================================================

SSH_USER:    str = "root"
SSH_KEY:     str = os.path.expanduser("~/.ssh/id_rsa")
SSH_TIMEOUT: int = 10
SSH_PORT:    int = 22

PC_IP:  str = NETWORK_NODES["spark"]["ip"]
PC_MAC: str = NETWORK_NODES["spark"]["mac"]

REMOTE_PCS: dict = {
    k: (v["ip"], v["mac"])
    for k, v in NETWORK_NODES.items()
    if v.get("mac")
}

# =============================================================================
# ❽  WAKE-ON-LAN
# =============================================================================

WOL_PORT:      int = 9
WOL_BROADCAST: str = "255.255.255.255"

# =============================================================================
# ❾  RECONHECIMENTO DE VOZ
# =============================================================================

MIC_ENERGY_THRESHOLD:  int   = 400
MIC_TIMEOUT:           float = 5.0
MIC_PHRASE_TIME_LIMIT: float = 12.0
MIC_PAUSE_THRESHOLD:   float = 0.9

# =============================================================================
# ❿  DETECÇÃO DE AMBIENTE
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
    VOICE_ENGINE   = "termux"
    NODE_TYPE      = "mobile"
    ASSISTANT_NAME = NETWORK_NODES["mobile"]["name"]

# =============================================================================
# ⓫  DIRETÓRIOS
# =============================================================================

BASE_DIR:      str = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR:  str = os.path.join(BASE_DIR, "commands")
TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
LOG_DIR:       str = os.path.join(BASE_DIR, "logs")
TEMP_DIR:      str = os.path.join(BASE_DIR, "tmp")
DATA_DIR:      str = os.path.join(BASE_DIR, "data")
LOG_FILE:      str = os.path.join(LOG_DIR, f"{NODE_TYPE}.log")
AUTH_DB_PATH        = os.path.join(DATA_DIR, "k7auth.db")

# =============================================================================
# ⓬  LOGGING
# =============================================================================

LOG_LEVEL:      str  = "INFO"
LOG_TO_FILE:    bool = True
LOG_TO_CONSOLE: bool = True

# =============================================================================
# Cria diretórios necessários
# =============================================================================
for _d in (LOG_DIR, TEMP_DIR, DATA_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)
