# =============================================================================
# k7-core | install.ps1 — Instalador Inteligente Windows
# Repositório: https://github.com/ksevendev/Assistente
# Site:        https://ksevendev.github.io/Assistente/
#
# Uso (PowerShell como Administrador):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install.ps1
#
# Instalação rápida via web:
#   irm https://raw.githubusercontent.com/ksevendev/Assistente/main/install.ps1 | iex
#
# Flags (não-interativo):
#   -Version  2|3
#   -Node     seven|spark|mobile
#   -Mode     master|worker
#   -Dir      CAMINHO
#   -Yes      (sem confirmações)
#   -NoVoice
#   -NoSSH
# =============================================================================

[CmdletBinding()]
param(
    [string]$Version  = "",
    [string]$Node     = "",
    [string]$Mode     = "",
    [string]$Dir      = "$env:USERPROFILE\Assistente",
    [string]$Branch   = "main",
    [string]$Repo     = "https://github.com/ksevendev/Assistente.git",
    [switch]$Yes,
    [switch]$NoVoice,
    [switch]$NoSSH
)

$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "k7-core Instalador"

# ── Helpers ──────────────────────────────────────────────────────────────────
function Write-Banner {
    Write-Host ""
    Write-Host "  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗" -ForegroundColor Cyan
    Write-Host "  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝" -ForegroundColor Cyan
    Write-Host "  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗  " -ForegroundColor Cyan
    Write-Host "  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝  " -ForegroundColor Cyan
    Write-Host "  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗" -ForegroundColor Cyan
    Write-Host "  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Assistente Virtual Distribuído" -ForegroundColor White
    Write-Host "  https://github.com/ksevendev/Assistente" -ForegroundColor DarkGray
    Write-Host "  https://ksevendev.github.io/Assistente/"  -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step($msg)   { Write-Host "`n  ━━━ $msg" -ForegroundColor Cyan }
function Write-Info($msg)   { Write-Host "  •  $msg" -ForegroundColor Cyan }
function Write-OK($msg)     { Write-Host "  ✓  $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "  ⚠  $msg" -ForegroundColor Yellow }
function Write-Err($msg)    { Write-Host "  ✗  $msg" -ForegroundColor Red }
function Write-HR           { Write-Host "  $(('-' * 46))" -ForegroundColor DarkGray }

function Read-Default($prompt, $default, [switch]$Secret) {
    if ($Yes -and $default) { return $default }
    if ($default) { Write-Host "  ?  $prompt [$default]: " -ForegroundColor Blue -NoNewline }
    else          { Write-Host "  ?  $prompt`: "           -ForegroundColor Blue -NoNewline }
    if ($Secret) {
        $ss = Read-Host -AsSecureString
        $val = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss))
    } else {
        $val = Read-Host
    }
    if (-not $val) { $val = $default }
    return $val
}

function New-Secret {
    try {
        $bytes = New-Object byte[] 32
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        return [Convert]::ToBase64String($bytes) -replace '[+/=]','' | Select-Object -First 1
    } catch {
        return "k7-$(Get-Date -Format 'yyyyMMddHHmmss')-$(Get-Random -Maximum 99999)"
    }
}

function New-FlaskKey {
    try {
        $bytes = New-Object byte[] 32
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        return ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
    } catch { return "k7flask$(Get-Random -Maximum 999999999999)" }
}

# ════════════════════════════════════════════════════════════════════════════
# VARIÁVEIS DO WIZARD
# ════════════════════════════════════════════════════════════════════════════
$W = @{
    Version         = $Version
    Node            = $Node
    NodeName        = ""
    Mode            = $Mode
    InstallDir      = $Dir
    ApiSecret       = ""
    AdminSecret     = ""
    FlaskKey        = ""
    DashUser        = "mestre"
    DashPass        = "k7mestre"
    SshUser         = $env:USERNAME
    IpSeven         = ""
    IpSpark         = ""
    IpMobile        = ""
    MacSeven        = "AA:BB:CC:DD:EE:01"
    MacSpark        = "AA:BB:CC:DD:EE:02"
    GhUser          = ""
    GhToken         = ""
    GhRepo          = "ksevendev/Assistente"
    GhCred          = "CONFIGURE_COM_python_updater_py_gen-cred"
    EnableAutoUpdate= $false
    OllamaUrl       = "http://localhost:11434"
    OllamaModel     = "llama3"
    GeminiKey       = ""
    VoiceEngine     = "espeak"
}
$PythonCmd = "python"
$PipCmd    = "pip"

# ════════════════════════════════════════════════════════════════════════════
# WIZARD
# ════════════════════════════════════════════════════════════════════════════
function Invoke-Wizard {
    Write-Banner

    # ── Versão ──────────────────────────────────────────────────────────
    if (-not $W.Version) {
        Write-Host ""
        Write-Host "  Escolha a versão:" -ForegroundColor White
        Write-Host ""
        Write-Host "  [2] v2.0  — Assistente Distribuído" -ForegroundColor Cyan
        Write-Host "      Dashboard · mDNS · Terminal remoto · Auto-update" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [3] v3.0  — Amigo Consciente  (recomendado)" -ForegroundColor Cyan
        Write-Host "      v2.0 + IA com RAG · Memória de projetos · Chat de Mentoria" -ForegroundColor DarkGray
        Write-Host "      Requer: Ollama ou Gemini API + ~300 MB extras" -ForegroundColor DarkGray
        Write-Host ""
        $W.Version = Read-Default "Versão [2/3]" "3"
    }
    if ($W.Version -ne "2" -and $W.Version -ne "3") {
        Write-Err "Versão inválida: '$($W.Version)'. Use 2 ou 3."
        exit 1
    }

    Write-HR

    # ── Nó ──────────────────────────────────────────────────────────────
    if (-not $W.Node) {
        Write-Host ""
        Write-Host "  Qual nó está sendo instalado?" -ForegroundColor White
        Write-Host ""
        Write-Host "  [1] Seven  — PC principal (Ciano · Master)"      -ForegroundColor Cyan
        Write-Host "      Dashboard completo · STT · Auto-update"      -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [2] Spark  — PC secundário (Laranja · Worker)"   -ForegroundColor DarkYellow
        Write-Host "      API headless · SSH · playerctl"               -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  [3] Mobile — Android/Termux (Violeta · Worker)"  -ForegroundColor Magenta
        Write-Host "      TTS nativo · Notificações · Vibração"         -ForegroundColor DarkGray
        Write-Host ""
        $choice = Read-Default "Nó [1=seven, 2=spark, 3=mobile]" "1"
        switch ($choice) {
            "2" { $W.Node = "spark"  }
            "3" { $W.Node = "mobile" }
            default { $W.Node = "seven" }
        }
    }

    switch ($W.Node) {
        "seven"  { $W.NodeName = "Seven";  if (-not $W.Mode) { $W.Mode = "master" } }
        "spark"  { $W.NodeName = "Spark";  if (-not $W.Mode) { $W.Mode = "worker" } }
        "mobile" { $W.NodeName = "Mobile"; $W.Mode = "worker"; $NoVoice = $true }
    }

    Write-HR

    # ── Rede ─────────────────────────────────────────────────────────────
    Write-Step "Configuração de Rede"
    Write-Host "  Deixe em branco para usar descoberta automática via mDNS." -ForegroundColor DarkGray
    Write-Host ""
    $W.IpSeven  = Read-Default "IP do nó Seven (ou vazio para mDNS)" ""
    if ($W.Node -ne "mobile") {
        $W.MacSeven = Read-Default "MAC do nó Seven (Wake-on-LAN)"   "AA:BB:CC:DD:EE:01"
        $W.IpSpark  = Read-Default "IP do nó Spark (ou vazio para mDNS)" ""
        $W.MacSpark = Read-Default "MAC do nó Spark (Wake-on-LAN)"   "AA:BB:CC:DD:EE:02"
    }

    # ── Segredos ─────────────────────────────────────────────────────────
    Write-Step "Segredos e Autenticação"
    $genAuto = if ($Yes) { "s" } else { Read-Default "Gerar segredos automaticamente? [S/n]" "s" }
    if ($genAuto -eq "n") {
        $W.ApiSecret   = Read-Default "API_SECRET"       (New-Secret)
        $W.AdminSecret = Read-Default "ADMIN_SECRET"     (New-Secret)
        $W.FlaskKey    = Read-Default "FLASK_SECRET_KEY" (New-FlaskKey)
    } else {
        $W.ApiSecret   = New-Secret
        $W.AdminSecret = New-Secret
        $W.FlaskKey    = New-FlaskKey
        Write-OK "Segredos gerados automaticamente."
    }
    Write-Host ""
    $W.DashUser = Read-Default "Usuário do dashboard" "mestre"
    $W.DashPass = Read-Default "Senha do dashboard"   "k7mestre" -Secret
    if (-not $NoSSH) { $W.SshUser = Read-Default "Usuário SSH nos nós remotos" $env:USERNAME }

    # ── GitHub ───────────────────────────────────────────────────────────
    Write-Step "Auto-Update GitHub (opcional)"
    $ghChoice = if ($Yes) { "n" } else { Read-Default "Configurar auto-update GitHub? [s/N]" "n" }
    if ($ghChoice -eq "s") {
        $W.GhUser  = Read-Default "Usuário GitHub"              ""
        $W.GhToken = Read-Default "Personal Access Token"       "" -Secret
        $W.GhRepo  = Read-Default "Repositório (owner/repo)"    "ksevendev/Assistente"
        if ($W.GhUser -and $W.GhToken -and $W.GhRepo) {
            $raw = "$($W.GhUser):$($W.GhToken):$($W.GhRepo)"
            $W.GhCred = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($raw))
            $W.EnableAutoUpdate = $true
        }
    } else {
        Write-Info "Auto-update desabilitado (configure depois em config.py)."
    }

    # ── IA (v3) ─────────────────────────────────────────────────────────
    if ($W.Version -eq "3") {
        Write-Step "Inteligência Artificial (v3.0)"
        Write-Host "  [1] Ollama (recomendado) — local, privado, grátis" -ForegroundColor Cyan
        Write-Host "  [2] Gemini API — Google, requer chave"             -ForegroundColor Cyan
        Write-Host "  [3] Fallback — só RAG, sem LLM"                   -ForegroundColor Cyan
        Write-Host ""
        $iaChoice = if ($Yes) { "1" } else { Read-Default "Motor de IA [1/2/3]" "1" }
        switch ($iaChoice) {
            "1" {
                $W.OllamaUrl   = Read-Default "URL Ollama"   "http://localhost:11434"
                $W.OllamaModel = Read-Default "Modelo Ollama" "llama3"
            }
            "2" { $W.GeminiKey = Read-Default "Chave Gemini API" "" -Secret }
            default { Write-Info "Usando fallback RAG sem LLM." }
        }
    }

    # ── Diretório ────────────────────────────────────────────────────────
    Write-Host ""
    $W.InstallDir = Read-Default "Diretório de instalação" $W.InstallDir
}

# ════════════════════════════════════════════════════════════════════════════
# GERA config.py
# ════════════════════════════════════════════════════════════════════════════
function New-ConfigPy {
    $cfgPath = Join-Path $W.InstallDir "config.py"
    Write-Info "Gerando $cfgPath..."

    $enableDash   = if ($W.Mode -eq "master") { "True" } else { "False" }
    $enableUpdate = if ($W.EnableAutoUpdate) { "True" } else { "False" }
    $nowStr       = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $v3Block = ""
    if ($W.Version -eq "3") {
        $v3Block = @"

# =============================================================================
# ⓰  INTELIGÊNCIA ARTIFICIAL (v3.0)
# =============================================================================

OLLAMA_URL:     str = "$($W.OllamaUrl)"
OLLAMA_MODEL:   str = "$($W.OllamaModel)"
GEMINI_API_KEY: str = "$($W.GeminiKey)"

import pathlib as _pathlib
_HOME = str(_pathlib.Path.home())
AI_PROJECTS: list = [
    {"name": "k7-core",   "path": BASE_DIR,                          "description": "Assistente Virtual",          "tech_stack": ["python","flask","zeroconf"]},
    {"name": "K7 Barber", "path": _HOME + "/projetos/k7-barber",     "description": "Agendamento barbearia",        "tech_stack": ["python","django"]},
    {"name": "KSigner",   "path": _HOME + "/projetos/ksigner",       "description": "Assinatura digital",           "tech_stack": ["python","fastapi"]},
    {"name": "SYNAP",     "path": _HOME + "/projetos/synap",         "description": "Análise neurológica",          "tech_stack": ["python","numpy"]},
    {"name": "Keryon",    "path": _HOME + "/projetos/keryon",        "description": "Orquestração distribuída",     "tech_stack": ["python","asyncio"]},
]
"@
    }

    $cfg = @"
# =============================================================================
# k7-core | config.py  — v$($W.Version).0
# Gerado pelo instalador em $nowStr
# Nó: $($W.Node) | Modo: $($W.Mode)
#
# EDITE ESTE ARQUIVO para personalizar o sistema.
# Referência: https://ksevendev.github.io/Assistente/
# =============================================================================

import os
import socket

# ❶ Identidade
NODE_TYPE:      str = "$($W.Node)"
ASSISTANT_NAME: str = "$($W.NodeName)"
ASSISTANT_LANG: str = "pt-BR"
K7_VERSION:     str = "$($W.Version).0"

# ❷ Modo
NODE_MODE:        str  = "$($W.Mode)"
ENABLE_DASHBOARD: bool = $enableDash

def is_master() -> bool:
    return ENABLE_DASHBOARD and NODE_MODE == "master"
def is_worker() -> bool:
    return not is_master()

# ❸ mDNS
DISCOVERY_SERVICE_TYPE:     str   = "_k7core._tcp.local."
DISCOVERY_NODE_NAME:        str   = ""
DISCOVERY_TTL:              int   = 60
DISCOVERY_BOOT_WAIT:        float = 2.0
DISCOVERY_RECHECK_INTERVAL: int   = 30

def get_discovery_name() -> str:
    base = DISCOVERY_NODE_NAME or f"k7-{NODE_TYPE}"
    return f"{base}.{DISCOVERY_SERVICE_TYPE}"

# ❹ API
API_HOST:     str = "0.0.0.0"
API_PORT:     int = 2026
API_SECRET:   str = "$($W.ApiSecret)"
ADMIN_SECRET: str = "$($W.AdminSecret)"

# ❺ Paletas
NODE_PALETTES: dict = {
    "seven":   {"label":"Cyan",   "ansi_primary":"\033[96m","ansi_secondary":"\033[36m","hex_primary":"#00E5FF","hex_secondary":"#00B8D4","hex_bg":"#00E5FF14","hex_glow":"#00E5FF40"},
    "spark":   {"label":"Orange", "ansi_primary":"\033[91m","ansi_secondary":"\033[33m","hex_primary":"#FF6D00","hex_secondary":"#E65100","hex_bg":"#FF6D0014","hex_glow":"#FF6D0040"},
    "mobile":  {"label":"Violet", "ansi_primary":"\033[95m","ansi_secondary":"\033[35m","hex_primary":"#AA00FF","hex_secondary":"#7B00D4","hex_bg":"#AA00FF14","hex_glow":"#AA00FF40"},
    "default": {"label":"Gray",   "ansi_primary":"\033[97m","ansi_secondary":"\033[37m","hex_primary":"#90A4AE","hex_secondary":"#607D8B","hex_bg":"#90A4AE14","hex_glow":"#90A4AE30"},
}

def get_palette(node_type: str = None) -> dict:
    return NODE_PALETTES.get(node_type or NODE_TYPE, NODE_PALETTES["default"])

# ❻ Topologia
NETWORK_NODES: dict = {
    "seven":  {"name":"Seven",  "ip":"$($W.IpSeven)", "port":2026,"mac":"$($W.MacSeven)","type":"desktop","specs":"Windows · v$($W.Version).0","icon":"laptop"},
    "spark":  {"name":"Spark",  "ip":"$($W.IpSpark)", "port":2026,"mac":"$($W.MacSpark)","type":"desktop","specs":"PC Desktop · Worker","icon":"desktop_windows"},
    "mobile": {"name":"Mobile", "ip":"",               "port":2026,"mac":"",               "type":"mobile", "specs":"Android · Termux","icon":"smartphone"},
}

def get_node_info(node_type: str = None) -> dict:
    return NETWORK_NODES.get(node_type or NODE_TYPE, {})
def get_peer_nodes() -> dict:
    return {k: v for k, v in NETWORK_NODES.items() if k != NODE_TYPE}
def get_nodes_with_palette() -> list:
    result = []
    for nt, ni in NETWORK_NODES.items():
        palette = NODE_PALETTES.get(nt, NODE_PALETTES["default"])
        entry = {"node_type": nt, **ni}
        for k, v in palette.items():
            if k.startswith("hex_") or k == "label":
                entry[f"color_{k}"] = v
        result.append(entry)
    return result

# ❼ Auth
AUTH_DB_PATH:     str = ""
FLASK_SECRET_KEY: str = "$($W.FlaskKey)"
DEFAULT_USER:     str = "$($W.DashUser)"
DEFAULT_PASSWORD: str = "$($W.DashPass)"
SESSION_LIFETIME: int = 3600 * 8

# ❽ Auto-Update
GH_CREDENTIAL:        str  = "$($W.GhCred)"
ENABLE_AUTO_UPDATE:   bool = $enableUpdate
GH_BRANCH:            str  = "$Branch"
GH_CHECK_INTERVAL:    int  = 3600
GH_RESTART_ON_UPDATE: bool = True
GH_LOCK_FILE:         str  = ""

# ❾ Voz
VOICE_ENGINE:  str = "espeak"
ESPEAK_VOICE:  str = "pt"
ESPEAK_SPEED:  int = 150
ESPEAK_VOLUME: int = 180

# ❿ SSH
SSH_USER:    str = "$($W.SshUser)"
SSH_KEY:     str = os.path.expanduser("~/.ssh/id_rsa")
SSH_TIMEOUT: int = 10
SSH_PORT:    int = 22
PC_IP:  str = NETWORK_NODES["spark"].get("ip", "")
PC_MAC: str = NETWORK_NODES["spark"].get("mac", "")
REMOTE_PCS: dict = {k:(v.get("ip",""),v.get("mac","")) for k,v in NETWORK_NODES.items() if v.get("mac")}

# ⓫ WoL
WOL_PORT:      int = 9
WOL_BROADCAST: str = "255.255.255.255"

# ⓬ Microfone
MIC_ENERGY_THRESHOLD:  int   = 400
MIC_TIMEOUT:           float = 5.0
MIC_PHRASE_TIME_LIMIT: float = 12.0
MIC_PAUSE_THRESHOLD:   float = 0.9

# ⓭ Ambiente
def is_android() -> bool:
    return "ANDROID_ROOT" in os.environ or "TERMUX_VERSION" in os.environ
def is_headless() -> bool:
    return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")

IS_ANDROID:  bool = is_android()
IS_HEADLESS: bool = is_headless()

# ⓮ Diretórios
BASE_DIR:      str = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR:  str = os.path.join(BASE_DIR, "commands")
TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
LOG_DIR:       str = os.path.join(BASE_DIR, "logs")
TEMP_DIR:      str = os.path.join(BASE_DIR, "tmp")
DATA_DIR:      str = os.path.join(BASE_DIR, "data")
LOG_FILE:      str = os.path.join(LOG_DIR, f"{NODE_TYPE}.log")
AUTH_DB_PATH        = os.path.join(DATA_DIR, "k7auth.db")
GH_LOCK_FILE        = os.path.join(DATA_DIR, ".update.lock")

# ⓯ Logging
LOG_LEVEL:      str  = "INFO"
LOG_TO_FILE:    bool = True
LOG_TO_CONSOLE: bool = True
$v3Block

for _d in (LOG_DIR, TEMP_DIR, DATA_DIR, TEMPLATES_DIR):
    os.makedirs(_d, exist_ok=True)
"@

    Set-Content -Path $cfgPath -Value $cfg -Encoding UTF8
    Write-OK "config.py gerado."
}

# ════════════════════════════════════════════════════════════════════════════
# SISTEMA, VENV, DEPS
# ════════════════════════════════════════════════════════════════════════════
function Install-SystemDeps {
    Write-Step "Dependências do Sistema"

    # Python
    foreach ($cmd in @("python","python3","py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)" -and [int]$Matches[2] -ge 10) {
                $script:PythonCmd = $cmd; break
            }
        } catch {}
    }
    if (-not $script:PythonCmd) {
        Write-Err "Python 3.10+ não encontrado."
        Write-Info "Baixe em: https://www.python.org/downloads/"
        if (-not $Yes) {
            if ((Read-Default "Abrir página de download? [s/N]" "s") -eq "s") {
                Start-Process "https://www.python.org/downloads/"
            }
        }
        exit 1
    }
    Write-OK "Python encontrado: $script:PythonCmd"

    # git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Info "Instalando git via winget..."
            winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements 2>$null
            $env:Path += ";$env:ProgramFiles\Git\cmd"
        } else {
            Write-Err "git não encontrado. Instale em: https://git-scm.com/download/win"
            exit 1
        }
    }
    Write-OK "git disponível."

    # espeak-ng
    if (-not $NoVoice) {
        if (-not (Get-Command espeak-ng -ErrorAction SilentlyContinue)) {
            if (Get-Command winget -ErrorAction SilentlyContinue) {
                Write-Info "Instalando espeak-ng..."
                winget install --id eSpeak.eSpeak-ng -e --silent --accept-package-agreements 2>$null
            } else {
                Write-Warn "espeak-ng não instalado. TTS via gTTS (requer internet)."
            }
        }
    }
}

function Setup-Venv {
    Write-Step "Ambiente Python"
    $venvDir = Join-Path $W.InstallDir ".venv"
    if (-not (Test-Path $venvDir)) {
        Write-Info "Criando .venv..."
        & $script:PythonCmd -m venv $venvDir
    }
    $script:PipCmd    = Join-Path $venvDir "Scripts\pip.exe"
    $script:PythonCmd = Join-Path $venvDir "Scripts\python.exe"
    & $script:PipCmd install --upgrade pip setuptools wheel --quiet
    Write-OK ".venv configurado."
}

function Install-PythonDeps {
    Write-Step "Bibliotecas Python"

    $core  = @("flask>=3.0.0","flask-login>=0.6.3","werkzeug>=3.0.0",
               "requests>=2.31.0","zeroconf>=0.131.0","paramiko>=3.4.0")
    $voice = @("SpeechRecognition>=3.10.0","gTTS>=2.5.0","pygame>=2.5.0")
    $ai    = @("chromadb>=0.5.0","sentence-transformers>=3.0.0")

    $pkgs = $core
    if (-not $NoVoice) { $pkgs += $voice }
    if ($W.Version -eq "3") { $pkgs += $ai }

    $total = $pkgs.Count; $count = 0
    foreach ($pkg in $pkgs) {
        $count++
        Write-Host "  [$("{0,2}" -f $count)/$total] $("{0,-44}" -f $pkg)" -NoNewline
        try {
            & $script:PipCmd install $pkg --quiet 2>$null
            Write-Host " ✓" -ForegroundColor Green
        } catch {
            Write-Host " ⚠" -ForegroundColor Yellow
        }
    }

    # PyAudio Windows
    if (-not $NoVoice) {
        Write-Host "  [   ] $("{0,-44}" -f 'PyAudio')" -NoNewline
        $ok = $false
        try { & $script:PipCmd install PyAudio --quiet 2>$null; $ok = $true } catch {}
        if (-not $ok) {
            try {
                & $script:PipCmd install pipwin --quiet 2>$null
                & $script:PythonCmd -m pipwin install pyaudio 2>$null
                $ok = $true
            } catch {}
        }
        if ($ok) { Write-Host " ✓" -ForegroundColor Green }
        else     { Write-Host " ⚠ (instale manualmente)" -ForegroundColor Yellow }
    }

    Write-OK "Bibliotecas instaladas."
}

# ════════════════════════════════════════════════════════════════════════════
# CÓDIGO FONTE
# ════════════════════════════════════════════════════════════════════════════
function Get-Code {
    Write-Step "Código-fonte"
    $localCore = Join-Path $PSScriptRoot "core.py"
    if (Test-Path $localCore) {
        Write-Info "Usando código do diretório atual."
        $W.InstallDir = $PSScriptRoot
        return
    }
    if (Test-Path (Join-Path $W.InstallDir ".git")) {
        Write-Info "Atualizando repositório..."
        Set-Location $W.InstallDir
        git fetch origin $Branch --quiet
        git reset --hard "origin/$Branch" --quiet
        Write-OK "Repositório atualizado."
        return
    }
    New-Item -ItemType Directory -Path $W.InstallDir -Force | Out-Null
    Write-Info "Clonando $Repo..."
    git clone --depth 1 --branch $Branch $Repo $W.InstallDir --quiet
    Write-OK "Repositório clonado."
}

# ════════════════════════════════════════════════════════════════════════════
# SCRIPTS .BAT + ATALHO
# ════════════════════════════════════════════════════════════════════════════
function New-RunScripts {
    Write-Step "Scripts de Execução"
    $d = $W.InstallDir
    $vp = Join-Path $d ".venv\Scripts\python.exe"

    # run.bat
    @"
@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python core.py %*
"@ | Set-Content (Join-Path $d "run.bat") -Encoding UTF8

    foreach ($nd in @("seven","spark")) {
        $nm = (Get-Culture).TextInfo.ToTitleCase($nd)
        $mo = if ($nd -eq "seven") {"master"} else {"worker"}
        @"
@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python -c "import config; config.NODE_TYPE='$nd'; config.ASSISTANT_NAME='$nm'; config.NODE_MODE='$mo'; import core; core.main()"
"@ | Set-Content (Join-Path $d "run_$nd.bat") -Encoding UTF8
        Write-OK "run_$nd.bat criado."
    }

    # Atalho Desktop
    try {
        $ws = New-Object -ComObject WScript.Shell
        $sc = $ws.CreateShortcut("$env:USERPROFILE\Desktop\k7-core.lnk")
        $sc.TargetPath       = Join-Path $d "run.bat"
        $sc.WorkingDirectory = $d
        $sc.Description      = "k7-core v$($W.Version).0 — $($W.NodeName)"
        $sc.Save()
        Write-OK "Atalho criado no Desktop."
    } catch { Write-Warn "Não foi possível criar atalho no Desktop." }

    # Chave SSH
    if (-not $NoSSH) {
        $sshKey = "$env:USERPROFILE\.ssh\id_rsa"
        if (-not (Test-Path $sshKey)) {
            New-Item -ItemType Directory -Path "$env:USERPROFILE\.ssh" -Force | Out-Null
            if (Get-Command ssh-keygen -ErrorAction SilentlyContinue) {
                ssh-keygen -t rsa -b 4096 -f $sshKey -N '""' -C "k7@$env:COMPUTERNAME" 2>$null
                Write-OK "Chave SSH gerada: $sshKey"
            }
        }
    }
}

# ════════════════════════════════════════════════════════════════════════════
# RESUMO
# ════════════════════════════════════════════════════════════════════════════
function Show-Summary {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║           k7-core instalado com sucesso!                 ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Versão:     v$($W.Version).0"      -ForegroundColor White
    Write-Host "  Nó:         $($W.NodeName) ($($W.Node) · $($W.Mode))" -ForegroundColor White
    Write-Host "  Diretório:  $($W.InstallDir)"       -ForegroundColor White
    Write-Host "  Dashboard:  http://localhost:2026/dashboard" -ForegroundColor White
    Write-Host "  Login:      $($W.DashUser) / [senha configurada]" -ForegroundColor White
    Write-Host ""
    Write-Host "  Próximos passos:" -ForegroundColor White
    Write-Host "  1. Revise config.py — IPs e MACs da sua rede" -ForegroundColor Gray
    Write-Host "  2. Inicie: .\run.bat  ou  .\run_$($W.Node.ToLower()).bat" -ForegroundColor Gray
    if ($W.Version -eq "3") {
        Write-Host "  3. Instale Ollama: winget install Ollama.Ollama" -ForegroundColor Gray
        Write-Host "     Depois: ollama pull llama3 && ollama serve" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  Docs: https://ksevendev.github.io/Assistente/" -ForegroundColor DarkGray
    Write-Host ""
}

# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
Invoke-Wizard
Install-SystemDeps
Get-Code
Setup-Venv
Install-PythonDeps
New-ConfigPy
New-RunScripts
Show-Summary
