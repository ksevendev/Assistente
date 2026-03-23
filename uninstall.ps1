# =============================================================================
# k7-core v2.0 | uninstall.ps1
# Desinstalador para Windows 10/11
#
# Uso (PowerShell como Admin):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\uninstall.ps1 [opções]
#
# Opções:
#   -Full         Remove TUDO incluindo chave SSH
#   -KeepData     Mantém data/ (banco SQLite e histórico)
#   -KeepConfig   Mantém config.py
#   -KeepSSH      Não remove a chave SSH (padrão)
#   -ServiceOnly  Remove apenas o serviço Windows (NSSM)
#   -DryRun       Mostra o que seria removido sem remover nada
#   -Yes          Sem confirmações interativas
#   -Dir CAMINHO  Diretório de instalação (padrão: dir do script)
# =============================================================================

[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$KeepData,
    [switch]$KeepConfig,
    [switch]$KeepSSH  = $true,
    [switch]$ServiceOnly,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$Dir = $PSScriptRoot
)

$ErrorActionPreference = "Continue"

# ─── Helpers ──────────────────────────────────────────────────────────────────
function Write-Step   { Write-Host "`n  ━━━ $args" -ForegroundColor Cyan }
function Write-Info   { Write-Host "  [INFO]  $args" -ForegroundColor Cyan }
function Write-OK     { Write-Host "  [ OK ]  $args" -ForegroundColor Green }
function Write-Warn   { Write-Host "  [WARN]  $args" -ForegroundColor Yellow }
function Write-Err    { Write-Host "  [ERRO]  $args" -ForegroundColor Red }
function Write-Dry    { Write-Host "  [DRY]   $args" -ForegroundColor DarkGray }

function Do-Remove {
    param([string]$Type, [string]$Target, [string]$Desc = "")
    if ($DryRun) { Write-Dry "REMOVERIA $Type`: $Target $Desc"; return }
    switch ($Type) {
        "file" {
            if (Test-Path $Target -PathType Leaf) {
                Remove-Item $Target -Force -ErrorAction SilentlyContinue
                Write-OK "Removido: $(Split-Path $Target -Leaf) $Desc"
            }
        }
        "dir" {
            if (Test-Path $Target -PathType Container) {
                Remove-Item $Target -Recurse -Force -ErrorAction SilentlyContinue
                Write-OK "Removida pasta: $(Split-Path $Target -Leaf) $Desc"
            }
        }
    }
}

function Confirm-Action {
    param([string]$Message)
    if ($Yes) { return $true }
    $r = Read-Host "`n  $Message [s/N]"
    return ($r -eq "s" -or $r -eq "S")
}

# ─── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗" -ForegroundColor Red
Write-Host "  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝" -ForegroundColor Red
Write-Host "  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗  " -ForegroundColor Red
Write-Host "  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝  " -ForegroundColor Red
Write-Host "  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗" -ForegroundColor Red
Write-Host "  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝" -ForegroundColor Red
Write-Host ""
Write-Host "  k7-core v2.0" -ForegroundColor White -NoNewline
Write-Host " — Desinstalador Windows" -ForegroundColor DarkGray
Write-Host ""

# ─── Verifica diretório ───────────────────────────────────────────────────────
$configPath = Join-Path $Dir "config.py"
if (-not (Test-Path $configPath)) {
    Write-Err "Instalação do k7-core não encontrada em: $Dir"
    Write-Info "Use -Dir CAMINHO para especificar o diretório correto."
    exit 1
}
Write-Info "Instalação encontrada em: $Dir"

# ─── Confirmação ──────────────────────────────────────────────────────────────
if (-not $ServiceOnly) {
    Write-Host ""
    Write-Host "  O que será removido:" -ForegroundColor Yellow
    Write-Host "  • Ambiente virtual Python (.venv\)" -ForegroundColor Gray
    Write-Host "  • Scripts de execução (run*.bat)" -ForegroundColor Gray
    Write-Host "  • Arquivos temporários (tmp\)" -ForegroundColor Gray
    Write-Host "  • Logs (logs\)" -ForegroundColor Gray
    if (-not $KeepData)   { Write-Host "  • Banco de dados e histórico (data\)" -ForegroundColor Red }
    if (-not $KeepConfig) { Write-Host "  • Configuração (config.py)" -ForegroundColor Red }
    if ($Full -and -not $KeepSSH) { Write-Host "  • Chave SSH (~\.ssh\id_rsa)" -ForegroundColor Red }
    if ($Full) { Write-Host "  • DIRETÓRIO COMPLETO: $Dir" -ForegroundColor Red }
    Write-Host "  • Serviço Windows k7core (se instalado)" -ForegroundColor Gray

    if (-not (Confirm-Action "Confirmar desinstalação?")) {
        Write-Info "Desinstalação cancelada."
        exit 0
    }
}

# ─── Para processos ───────────────────────────────────────────────────────────
Write-Step "Parando processos k7-core"

$procs = Get-Process | Where-Object { $_.MainWindowTitle -like "*k7*" -or $_.ProcessName -eq "python" } -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    try {
        $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
        if ($cmdLine -like "*core.py*") {
            if ($DryRun) { Write-Dry "MATARIA processo PID $($p.Id): $cmdLine" }
            else {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                Write-OK "Processo encerrado: PID $($p.Id)"
            }
        }
    } catch {}
}

# ─── Remove serviço Windows (NSSM) ───────────────────────────────────────────
Write-Step "Removendo serviço Windows"

$svcName = "k7core"
$svc     = Get-Service -Name $svcName -ErrorAction SilentlyContinue

if ($svc) {
    if ($DryRun) {
        Write-Dry "PARARIA e removeria serviço: $svcName"
    } else {
        if ($svc.Status -eq "Running") {
            Stop-Service $svcName -Force -ErrorAction SilentlyContinue
            Write-OK "Serviço parado: $svcName"
        }
        if (Get-Command nssm -ErrorAction SilentlyContinue) {
            nssm remove $svcName confirm 2>$null
            Write-OK "Serviço NSSM removido: $svcName"
        } else {
            sc.exe delete $svcName 2>$null | Out-Null
            Write-OK "Serviço removido: $svcName"
        }
    }
} else {
    Write-Info "Serviço $svcName não encontrado — nada a remover."
}

if ($ServiceOnly) {
    Write-OK "Remoção do serviço concluída."
    exit 0
}

# ─── Remove ambiente Python ───────────────────────────────────────────────────
Write-Step "Removendo ambiente virtual Python"

Do-Remove "dir"  (Join-Path $Dir ".venv")    "(ambiente virtual)"
Do-Remove "dir"  (Join-Path $Dir "__pycache__") "(cache)"

if (-not $DryRun) {
    Get-ChildItem $Dir -Recurse -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem $Dir -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-OK "Arquivos .pyc e __pycache__ removidos."
} else {
    Write-Dry "REMOVERIA: todos os *.pyc e __pycache__ em $Dir"
}

# ─── Remove scripts de execução ───────────────────────────────────────────────
Write-Step "Removendo scripts de execução"

$scripts = @("run.bat", "run_seven.bat", "run_spark.bat", "run_mobile.bat",
             "run.sh", "run_seven.sh", "run_spark.sh")
foreach ($s in $scripts) {
    Do-Remove "file" (Join-Path $Dir $s)
}

# Atalho no Desktop
$shortcut = Join-Path $env:USERPROFILE "Desktop\k7-core.lnk"
Do-Remove "file" $shortcut "(atalho do Desktop)"

# ─── Remove dados e logs ──────────────────────────────────────────────────────
Write-Step "Removendo dados e logs"

Do-Remove "dir" (Join-Path $Dir "tmp")  "(arquivos temporários)"
Do-Remove "dir" (Join-Path $Dir "logs") "(logs)"

if (-not $KeepData) {
    Write-Warn "Removendo dados persistentes..."
    Do-Remove "file" (Join-Path $Dir "data\k7auth.db")           "(banco de usuários)"
    Do-Remove "file" (Join-Path $Dir "data\update_history.json")  "(histórico de updates)"
    Do-Remove "file" (Join-Path $Dir "data\.update.lock")         "(file lock)"
    # Remove pasta data se vazia
    $dataDir = Join-Path $Dir "data"
    if (-not $DryRun -and (Test-Path $dataDir)) {
        $items = Get-ChildItem $dataDir -ErrorAction SilentlyContinue
        if ($items.Count -eq 0) {
            Remove-Item $dataDir -Force -ErrorAction SilentlyContinue
            Write-OK "Pasta data\ removida."
        } else {
            Write-Warn "Pasta data\ não estava vazia — mantida."
        }
    }
} else {
    Write-Info "Dados preservados (-KeepData): $Dir\data\"
}

# ─── Remove configuração ──────────────────────────────────────────────────────
Write-Step "Removendo configuração"

if ($KeepConfig) {
    Write-Info "Configuração preservada (-KeepConfig): $Dir\config.py"
} else {
    # Backup antes de remover
    if ((Test-Path $configPath) -and -not $DryRun) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backup = Join-Path $env:USERPROFILE "k7core_config_backup_$timestamp.py"
        Copy-Item $configPath $backup
        Write-Info "Backup salvo em: $backup"
    }
    Do-Remove "file" $configPath "(configuração principal)"
}

# ─── Remove chave SSH ─────────────────────────────────────────────────────────
Write-Step "Tratando chave SSH"

if ($Full -and -not $KeepSSH) {
    $sshKey = Join-Path $env:USERPROFILE ".ssh\id_rsa"
    if (Test-Path $sshKey) {
        Write-Warn "Remover chave SSH pode quebrar outros serviços!"
        if (Confirm-Action "Remover $sshKey ?") {
            Do-Remove "file" $sshKey             "(chave privada)"
            Do-Remove "file" "$sshKey.pub"       "(chave pública)"
        } else {
            Write-Info "Chave SSH mantida."
        }
    }
} else {
    Write-Info "Chave SSH preservada: $env:USERPROFILE\.ssh\id_rsa"
}

# ─── Remove diretório completo (modo --full) ──────────────────────────────────
if ($Full) {
    Write-Step "Removendo diretório de instalação completo"

    if (Confirm-Action "CONFIRMA remoção de $Dir ?") {
        Set-Location $env:USERPROFILE
        Do-Remove "dir" $Dir "(diretório completo)"
    }
} else {
    Write-Info "Diretório $Dir preservado."
    Write-Info "Para remover manualmente: Remove-Item -Recurse -Force `"$Dir`""
}

# ─── Resumo ───────────────────────────────────────────────────────────────────
Write-Host ""
if ($DryRun) {
    Write-Host "  ━━━ Resumo (DRY-RUN — nada foi removido) ━━━" -ForegroundColor Yellow
    Write-Info "Execute sem -DryRun para aplicar a desinstalação."
} else {
    Write-Host "  ╔═══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║      k7-core v2.0 desinstalado com sucesso!           ║" -ForegroundColor Green
    Write-Host "  ╚═══════════════════════════════════════════════════════╝" -ForegroundColor Green
    if ($KeepData)   { Write-Info "Dados preservados em: $Dir\data\" }
    if ($KeepConfig) { Write-Info "Configuração em: $Dir\config.py" }
}
Write-Host ""
