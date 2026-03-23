# =============================================================================
# k7-core | uninstall.ps1 — Desinstalador Windows
# Repositório: https://github.com/ksevendev/Assistente
#
# Uso:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\uninstall.ps1 [opções]
#
# Opções:
#   -Full         Remove TUDO incluindo o diretório
#   -KeepData     Preserva banco SQLite e histórico
#   -KeepConfig   Preserva config.py
#   -ServiceOnly  Remove apenas o serviço Windows
#   -DryRun       Simulação sem remover nada
#   -Yes          Sem confirmações
#   -Dir CAMINHO  Diretório de instalação
# =============================================================================

[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$KeepData,
    [switch]$KeepConfig,
    [switch]$ServiceOnly,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$Dir = $PSScriptRoot
)

$ErrorActionPreference = "Continue"

function Write-Step($m)  { Write-Host "`n  ━━━ $m" -ForegroundColor Cyan }
function Write-Info($m)  { Write-Host "  •  $m"    -ForegroundColor Cyan }
function Write-OK($m)    { Write-Host "  ✓  $m"    -ForegroundColor Green }
function Write-Warn($m)  { Write-Host "  ⚠  $m"    -ForegroundColor Yellow }
function Write-Err($m)   { Write-Host "  ✗  $m"    -ForegroundColor Red }
function Write-Dry($m)   { Write-Host "  [DRY] Removeria: $m" -ForegroundColor DarkGray }

function Remove-Item2($type, $target, $desc="") {
    if ($DryRun) { Write-Dry "$type`: $target $desc"; return }
    switch ($type) {
        "file" {
            if (Test-Path $target -PathType Leaf) {
                Remove-Item $target -Force -ErrorAction SilentlyContinue
                Write-OK "Removido: $(Split-Path $target -Leaf) $desc"
            }
        }
        "dir"  {
            if (Test-Path $target -PathType Container) {
                Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue
                Write-OK "Removida pasta: $(Split-Path $target -Leaf) $desc"
            }
        }
    }
}

# ── Banner ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ██╗  ██╗███████╗  ██████╗ ██████╗ ██████╗ ███████╗" -ForegroundColor Red
Write-Host "  Desinstalador — github.com/ksevendev/Assistente"      -ForegroundColor DarkGray
Write-Host ""

# Detecta versão instalada
$configPath = Join-Path $Dir "config.py"
$K7Ver = "?"
if (Test-Path $configPath) {
    $content = Get-Content $configPath -Raw -ErrorAction SilentlyContinue
    if ($content -match 'K7_VERSION.*?[''"](\d\.\d)[''"]') { $K7Ver = $Matches[1] }
    elseif ($content) { $K7Ver = "2.0" }
}

if (-not (Test-Path $configPath)) {
    Write-Err "Instalação k7-core não encontrada em: $Dir"
    Write-Info "Use -Dir CAMINHO para especificar o diretório correto."
    exit 1
}
Write-Info "k7-core v$K7Ver encontrado em: $Dir"

# ── Confirmação ────────────────────────────────────────────────────────────
if (-not $ServiceOnly) {
    Write-Host ""
    Write-Host "  O que será removido:" -ForegroundColor Yellow
    Write-Host "  • Ambiente virtual Python (.venv\)" -ForegroundColor Gray
    Write-Host "  • Scripts run*.bat e temporários"   -ForegroundColor Gray
    Write-Host "  • Logs e cache Python"               -ForegroundColor Gray
    if ($K7Ver -like "3*") { Write-Host "  • Base ChromaDB (data\chroma\)" -ForegroundColor Gray }
    if (-not $KeepData)   { Write-Host "  • Banco de dados e histórico (data\)" -ForegroundColor Red }
    if (-not $KeepConfig) { Write-Host "  • Configuração (config.py)" -ForegroundColor Red }
    if ($Full)            { Write-Host "  • DIRETÓRIO COMPLETO: $Dir" -ForegroundColor Red }
    Write-Host ""
    if ($DryRun) { Write-Host "  MODO DRY-RUN: nada será removido." -ForegroundColor Yellow }
    if (-not $Yes -and -not $DryRun) {
        $reply = Read-Host "  Confirmar desinstalação? [s/N]"
        if ($reply -ne "s" -and $reply -ne "S") {
            Write-Info "Desinstalação cancelada."
            exit 0
        }
    }
}

# ── Para processos ─────────────────────────────────────────────────────────
Write-Step "Parando processos"
$procs = Get-WmiObject Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*core.py*" }
foreach ($p in $procs) {
    if ($DryRun) { Write-Dry "Mataria PID $($p.ProcessId)" }
    else {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-OK "Processo $($p.ProcessId) encerrado."
    }
}

# ── Serviço Windows ────────────────────────────────────────────────────────
Write-Step "Serviço Windows"
$svc = Get-Service -Name "k7core" -ErrorAction SilentlyContinue
if ($svc) {
    if ($DryRun) { Write-Dry "Pararia e removeria serviço k7core" }
    else {
        if ($svc.Status -eq "Running") { Stop-Service "k7core" -Force -ErrorAction SilentlyContinue }
        if (Get-Command nssm -ErrorAction SilentlyContinue) {
            nssm remove k7core confirm 2>$null
        } else {
            sc.exe delete k7core 2>$null | Out-Null
        }
        Write-OK "Serviço k7core removido."
    }
} else { Write-Info "Serviço k7core não encontrado." }

if ($ServiceOnly) { Write-OK "Remoção do serviço concluída."; exit 0 }

# ── Ambiente Python ────────────────────────────────────────────────────────
Write-Step "Ambiente Python"
Remove-Item2 "dir" (Join-Path $Dir ".venv") "(ambiente virtual)"
if (-not $DryRun) {
    Get-ChildItem $Dir -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem $Dir -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-OK "Cache Python removido."
}

# ── Scripts ─────────────────────────────────────────────────────────────────
Write-Step "Scripts"
foreach ($s in @("run.bat","run_seven.bat","run_spark.bat","run_mobile.bat","run.sh","run_seven.sh","run_spark.sh")) {
    Remove-Item2 "file" (Join-Path $Dir $s)
}
Remove-Item2 "file" "$env:USERPROFILE\Desktop\k7-core.lnk" "(atalho Desktop)"

# ── v3 — ChromaDB ─────────────────────────────────────────────────────────
if ($K7Ver -like "3*") {
    Write-Step "Base de Conhecimento v3.0"
    Remove-Item2 "dir"  (Join-Path $Dir "data\chroma")      "(vetores ChromaDB)"
    Remove-Item2 "file" (Join-Path $Dir "data\episodic.db")  "(memória episódica)"
}

# ── Dados ──────────────────────────────────────────────────────────────────
Write-Step "Dados e Logs"
Remove-Item2 "dir" (Join-Path $Dir "tmp")  "(temporários)"
Remove-Item2 "dir" (Join-Path $Dir "logs") "(logs)"

if (-not $KeepData) {
    Write-Warn "Removendo dados persistentes..."
    Remove-Item2 "file" (Join-Path $Dir "data\k7auth.db")
    Remove-Item2 "file" (Join-Path $Dir "data\update_history.json")
    Remove-Item2 "file" (Join-Path $Dir "data\.update.lock")
    $dataDir = Join-Path $Dir "data"
    if (-not $DryRun -and (Test-Path $dataDir)) {
        $items = Get-ChildItem $dataDir -ErrorAction SilentlyContinue
        if ($items.Count -eq 0) {
            Remove-Item $dataDir -Force -ErrorAction SilentlyContinue
            Write-OK "Pasta data\ removida."
        }
    }
} else { Write-Info "Dados preservados (-KeepData)." }

# ── Config ─────────────────────────────────────────────────────────────────
Write-Step "Configuração"
if ($KeepConfig) {
    Write-Info "config.py preservado (-KeepConfig)."
} else {
    if ((Test-Path $configPath) -and -not $DryRun) {
        $ts = Get-Date -Format "yyyyMMdd_HHmmss"
        $bk = "$env:USERPROFILE\k7core_config_backup_$ts.py"
        Copy-Item $configPath $bk -ErrorAction SilentlyContinue
        Write-Info "Backup: $bk"
    }
    Remove-Item2 "file" $configPath "(configuração principal)"
}

# ── Remoção total ─────────────────────────────────────────────────────────
if ($Full) {
    Write-Step "Remoção do diretório completo"
    Set-Location $env:USERPROFILE
    Remove-Item2 "dir" $Dir "(diretório completo)"
} else {
    Write-Info "Diretório $Dir preservado."
}

# ── Resumo ──────────────────────────────────────────────────────────────────
Write-Host ""
if ($DryRun) {
    Write-Host "  DRY-RUN: nada foi removido." -ForegroundColor Yellow
} else {
    Write-Host "  ✓  k7-core v$K7Ver desinstalado com sucesso." -ForegroundColor Green
    if ($KeepData)   { Write-Info "Dados preservados em: $Dir\data\" }
    if ($KeepConfig) { Write-Info "Config preservado em: $Dir\config.py" }
}
Write-Host ""
