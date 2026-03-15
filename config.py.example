# =============================================================================
# k7-core | config.py  — v3 (Distributed Nodes)
# Edite este arquivo para configurar cada instância da rede.
#
# INSTÂNCIAS DA REDE:
#   NODE_TYPE = "seven"   → Notebook   (paleta Ciano)
#   NODE_TYPE = "spark"   → PC Desktop (paleta Laranja/Vermelho)
#   NODE_TYPE = "mobile"  → Android/Termux (paleta Violeta, TTS nativo)
# =============================================================================

import os
import platform

# =============================================================================
# ❶  IDENTIDADE DO NÓ — ALTERE PARA CADA INSTÂNCIA
# =============================================================================

# Tipo deste nó — determina comportamentos, paleta visual e capabilities
# Valores aceitos: "seven" | "spark" | "mobile"
NODE_TYPE: str = "seven"

# Nome do assistente neste nó (pode diferir por instância)
ASSISTANT_NAME: str = "Seven"

# Idioma de voz / reconhecimento
ASSISTANT_LANG: str = "pt-BR"

# =============================================================================
# ❷  PALETAS DE COR POR NÓ  (usadas no dashboard e logs coloridos)
# =============================================================================

NODE_PALETTES: dict = {
    "seven":  {"primary": "\033[96m",  "secondary": "\033[36m",  "label": "CYAN",   "hex": "#00FFFF"},
    "spark":  {"primary": "\033[91m",  "secondary": "\033[33m",  "label": "ORANGE", "hex": "#FF6600"},
    "mobile": {"primary": "\033[95m",  "secondary": "\033[35m",  "label": "VIOLET", "hex": "#AA00FF"},
}

def get_palette() -> dict:
    """Retorna a paleta do nó atual."""
    return NODE_PALETTES.get(NODE_TYPE, NODE_PALETTES["seven"])

# =============================================================================
# ❸  API SERVER — porta onde este nó escuta comandos remotos
# =============================================================================

API_HOST: str = "0.0.0.0"   # escuta em todas as interfaces
API_PORT: int = 7007         # porta padrão para todos os nós
API_SECRET: str = "k7-secret-local-network"  # token simples de autenticação

# =============================================================================
# ❹  MAPA DA REDE DE NÓS  { node_type: { ip, port, name } }
# Preencha com os IPs reais de cada dispositivo.
# =============================================================================

NETWORK_NODES: dict = {
    "seven": {
        "name":    "Seven",
        "ip":      "192.168.1.10",
        "port":    7007,
        "mac":     "AA:BB:CC:DD:EE:01",
    },
    "spark": {
        "name":    "Spark",
        "ip":      "192.168.1.11",
        "port":    7007,
        "mac":     "AA:BB:CC:DD:EE:02",
    },
    "mobile": {
        "name":    "Mobile",
        "ip":      "192.168.1.12",   # IP do celular na rede WiFi
        "port":    7007,
        "mac":     "",               # celular não tem WoL
    },
}

def get_node_info(node_type: str = None) -> dict:
    """Retorna as informações de um nó pelo tipo (padrão: nó atual)."""
    return NETWORK_NODES.get(node_type or NODE_TYPE, {})

def get_peer_nodes() -> dict:
    """Retorna todos os nós exceto o atual."""
    return {k: v for k, v in NETWORK_NODES.items() if k != NODE_TYPE}

# =============================================================================
# ❺  VOZ / TTS
# =============================================================================

# Engine: "espeak" | "gtts" | "termux" (auto-detectado no Android)
VOICE_ENGINE:  str = "espeak"
ESPEAK_VOICE:  str = "pt"
ESPEAK_SPEED:  int = 150
ESPEAK_VOLUME: int = 180

# =============================================================================
# ❻  SSH
# =============================================================================

SSH_USER:    str = "usuario"
SSH_KEY:     str = os.path.expanduser("~/.ssh/id_rsa")
SSH_TIMEOUT: int = 10
SSH_PORT:    int = 22

# PC principal legado (compatibilidade com v2)
PC_IP:  str = NETWORK_NODES["spark"]["ip"]
PC_MAC: str = NETWORK_NODES["spark"]["mac"]

# Mapa de PCs para WoL/SSH (alias → (ip, mac))
REMOTE_PCS: dict = {
    "spark":      (NETWORK_NODES["spark"]["ip"],  NETWORK_NODES["spark"]["mac"]),
    "seven":      (NETWORK_NODES["seven"]["ip"],  NETWORK_NODES["seven"]["mac"]),
    "desktop":    (NETWORK_NODES["spark"]["ip"],  NETWORK_NODES["spark"]["mac"]),
}

# =============================================================================
# ❼  WAKE-ON-LAN
# =============================================================================

WOL_PORT:      int = 9
WOL_BROADCAST: str = "255.255.255.255"

# =============================================================================
# ❽  RECONHECIMENTO DE VOZ
# =============================================================================

MIC_ENERGY_THRESHOLD:  int   = 400
MIC_TIMEOUT:           float = 5.0
MIC_PHRASE_TIME_LIMIT: float = 12.0
MIC_PAUSE_THRESHOLD:   float = 0.9

# =============================================================================
# ❾  DETECÇÃO DE AMBIENTE
# =============================================================================

def is_android() -> bool:
    """Detecta se está rodando no Android (Termux)."""
    return (
        "ANDROID_ROOT" in os.environ
        or "TERMUX_VERSION" in os.environ
        or os.path.exists("/data/data/com.termux")
    )

def is_headless() -> bool:
    """Detecta se não há display gráfico disponível."""
    return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")

# Cache das detecções (chamadas baratas, mas evita repetição)
IS_ANDROID:  bool = is_android()
IS_HEADLESS: bool = is_headless()

# No Android, força engine Termux
if IS_ANDROID:
    VOICE_ENGINE   = "termux"
    NODE_TYPE      = "mobile"
    ASSISTANT_NAME = NETWORK_NODES["mobile"]["name"]

# =============================================================================
# ❿  DIRETÓRIOS
# =============================================================================

BASE_DIR:     str = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR: str = os.path.join(BASE_DIR, "commands")
LOG_DIR:      str = os.path.join(BASE_DIR, "logs")
TEMP_DIR:     str = os.path.join(BASE_DIR, "tmp")
LOG_FILE:     str = os.path.join(LOG_DIR, f"{NODE_TYPE}.log")

# =============================================================================
# ⓫  LOGGING
# =============================================================================

LOG_LEVEL:       str  = "INFO"
LOG_TO_FILE:     bool = True
LOG_TO_CONSOLE:  bool = True

# =============================================================================
# Cria diretórios necessários
# =============================================================================
for _d in (LOG_DIR, TEMP_DIR):
    os.makedirs(_d, exist_ok=True)
