# =============================================================================
# k7-core v2.0 | install.ps1
# Instalador para Windows 10/11 — PowerShell 5.1+
#
# Uso (como Administrador):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install.ps1 [opções]
#
# Ou via comando único (PowerShell como Admin):
#   irm https://raw.githubusercontent.com/SEU_USER/k7-core/main/install.ps1 | iex
#
# Opções:
#   -Node    seven|spark|mobile   Tipo de nó (padrão: seven)
#   -Dir     CAMINHO              Diretório de instalação (padrão: %USERPROFILE%\k7-core)
#   -Branch  NOME                 Branch git (padrão: main)
#   -NoVoice                      Pula PyAudio (servidor headless)
#   -NoSSH                        Não gera chave SSH
#   -Silent                       Sem confirmações interativas
#   -Dev                          Instala dependências de desenvolvimento
# =============================================================================

[CmdletBinding()]
param(
    [string]$Node    = "seven",
    [string]$Dir     = "$env:USERPROFILE\k7-core",
    [string]$Branch  = "main",
    [string]$Repo    = "https://github.com/SEU_USER/k7-core.git",
    [switch]$NoVoice,
    [switch]$NoSSH,
    [switch]$Silent,
    [switch]$Dev
)

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

# ─── Cores e helpers ──────────────────────────────────────────────────────────
function Write-Banner {
    $color = "Cyan"
    Write-Host ""
    Write-Host "  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗" -ForegroundColor $color
    Write-Host "  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝" -ForegroundColor $color
    Write-Host "  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗  " -ForegroundColor $color
    Write-Host "  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝  " -ForegroundColor $color
    Write-Host "  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗" -ForegroundColor $color
    Write-Host "  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝" -ForegroundColor $color
    Write-Host ""
    Write-Host "  k7-core v2.0" -ForegroundColor White -NoNewline
    Write-Host " — Assistente Virtual Distribuído" -ForegroundColor DarkGray
    Write-Host "  Instalador Windows" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step   { Write-Host "`n  ━━━ $args" -ForegroundColor Cyan }
function Write-Info   { Write-Host "  [INFO]  $args" -ForegroundColor Cyan }
function Write-OK     { Write-Host "  [ OK ]  $args" -ForegroundColor Green }
function Write-Warn   { Write-Host "  [WARN]  $args" -ForegroundColor Yellow }
function Write-Err    { Write-Host "  [ERRO]  $args" -ForegroundColor Red }

function Confirm-Action {
    param([string]$Message)
    if ($Silent) { return $true }
    $reply = Read-Host "`n  $Message [s/N]"
    return ($reply -eq "s" -or $reply -eq "S")
}

# ─── Verificações de prerequisito ─────────────────────────────────────────────
function Test-Prerequisites {
    Write-Step "Verificando pré-requisitos"

    # Versão do Windows
    $osVer = [System.Environment]::OSVersion.Version
    Write-Info "Windows $($osVer.Major).$($osVer.Minor) (Build $($osVer.Build))"
    if ($osVer.Major -lt 10) {
        Write-Err "Windows 10 ou superior é necessário."
        exit 1
    }

    # PowerShell
    Write-Info "PowerShell $($PSVersionTable.PSVersion)"
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Err "PowerShell 5.1+ é necessário."
        exit 1
    }

    # Privilégio de administrador
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
    if (-not $isAdmin) {
        Write-Warn "Não está sendo executado como Administrador."
        Write-Warn "Alguns recursos podem falhar (serviço Windows, pacotes de sistema)."
    } else {
        Write-OK "Executando como Administrador."
    }

    # Python 3.10+
    $pyCmd = $null
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python (\d+)\.(\d+)") {
                if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) {
                    $pyCmd = $cmd
                    Write-OK "Python $($Matches[1]).$($Matches[2]) ($cmd)"
                    break
                }
            }
        } catch {}
    }

    if (-not $pyCmd) {
        Write-Err "Python 3.10+ não encontrado."
        Write-Info "Baixe em: https://www.python.org/downloads/"
        Write-Info "Marque 'Add Python to PATH' durante a instalação."
        if (Confirm-Action "Abrir página de download do Python?") {
            Start-Process "https://www.python.org/downloads/"
        }
        exit 1
    }

    $script:PYTHON_CMD = $pyCmd

    # git
    try {
        $gitVer = git --version 2>&1
        Write-OK "git $($gitVer -replace 'git version ','')"
    } catch {
        Write-Warn "git não encontrado — tentando instalar via winget..."
        Install-Git
    }

    # Espaço em disco
    $drive = Split-Path -Qualifier $Dir
    $disk  = Get-PSDrive ($drive.TrimEnd(':')) -ErrorAction SilentlyContinue
    if ($disk -and $disk.Free -lt 500MB) {
        Write-Warn "Pouco espaço em disco: $([math]::Round($disk.Free / 1MB)) MB livres."
    }
}

# ─── Instala git via winget ────────────────────────────────────────────────────
function Install-Git {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Instalando git via winget..."
        winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
        # Recarrega PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        Write-OK "git instalado."
    } else {
        Write-Err "winget não disponível. Instale git manualmente: https://git-scm.com/download/win"
        if (Confirm-Action "Abrir página de download do git?") {
            Start-Process "https://git-scm.com/download/win"
        }
        exit 1
    }
}

# ─── Instala espeak-ng via winget ─────────────────────────────────────────────
function Install-Espeak {
    if ($NoVoice) { return }
    Write-Info "Verificando espeak-ng..."
    if (Get-Command espeak-ng -ErrorAction SilentlyContinue) {
        Write-OK "espeak-ng já instalado."
        return
    }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Instalando espeak-ng via winget..."
        winget install --id eSpeak.eSpeak-ng -e --silent --accept-package-agreements --accept-source-agreements 2>$null
        Write-OK "espeak-ng instalado."
    } else {
        Write-Warn "espeak-ng não instalado. Baixe em: https://github.com/espeak-ng/espeak-ng/releases"
        Write-Warn "TTS funcionará apenas com gTTS (requer internet)."
    }
}

# ─── Obtém o código ───────────────────────────────────────────────────────────
function Get-Code {
    Write-Step "Obtendo código-fonte"

    # Se está sendo executado de dentro do projeto
    $localCore = Join-Path $PSScriptRoot "core.py"
    if (Test-Path $localCore) {
        Write-Info "Código encontrado no diretório atual: $PSScriptRoot"
        $script:INSTALL_DIR = $PSScriptRoot
        return
    }

    if (Test-Path (Join-Path $Dir ".git")) {
        Write-Info "Repositório existente em $Dir — atualizando..."
        Set-Location $Dir
        git fetch origin $Branch --quiet
        git reset --hard "origin/$Branch" --quiet
        Write-OK "Código atualizado (branch: $Branch)"
        return
    }

    if (Test-Path $Dir) {
        Write-Warn "Diretório $Dir já existe mas não é um repositório git."
        if (-not (Confirm-Action "Continuar mesmo assim?")) { exit 1 }
    } else {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }

    Write-Info "Clonando $Repo em $Dir..."
    git clone --depth 1 --branch $Branch $Repo $Dir --quiet
    Write-OK "Repositório clonado."
    $script:INSTALL_DIR = $Dir
}

# ─── Ambiente virtual Python ──────────────────────────────────────────────────
function Setup-Venv {
    Write-Step "Configurando ambiente virtual Python"

    $venvDir = Join-Path $script:INSTALL_DIR ".venv"
    $venvPip = Join-Path $venvDir "Scripts\pip.exe"
    $venvPy  = Join-Path $venvDir "Scripts\python.exe"

    if (-not (Test-Path $venvDir)) {
        Write-Info "Criando .venv em $venvDir..."
        & $script:PYTHON_CMD -m venv $venvDir
        Write-OK ".venv criado."
    } else {
        Write-Info "Ambiente virtual existente em $venvDir."
    }

    Write-Info "Atualizando pip..."
    & $venvPip install --upgrade pip setuptools wheel --quiet
    Write-OK "pip atualizado."

    $script:PIP_CMD    = $venvPip
    $script:PYTHON_CMD = $venvPy
}

# ─── Instala dependências Python ──────────────────────────────────────────────
function Install-PythonDeps {
    Write-Step "Instalando bibliotecas Python"

    $pkgsCore = @(
        "flask>=3.0.0",
        "flask-login>=0.6.3",
        "werkzeug>=3.0.0",
        "requests>=2.31.0",
        "zeroconf>=0.131.0",
        "paramiko>=3.4.0"
    )

    $pkgsVoice = @(
        "SpeechRecognition>=3.10.0",
        "gTTS>=2.5.0",
        "pygame>=2.5.0"
        # PyAudio requer compilação no Windows — tratado separadamente
    )

    $pkgsDev = @(
        "pytest>=7.0.0",
        "black>=24.0.0",
        "mypy>=1.0.0"
    )

    $allPkgs = $pkgsCore
    if (-not $NoVoice) { $allPkgs += $pkgsVoice }
    if ($Dev)          { $allPkgs += $pkgsDev }

    $total = $allPkgs.Count
    $count = 0

    foreach ($pkg in $allPkgs) {
        $count++
        Write-Host "  [$("{0,2}" -f $count)/$total] $("{0,-40}" -f $pkg)" -NoNewline
        try {
            & $script:PIP_CMD install $pkg --quiet 2>$null
            Write-Host " OK" -ForegroundColor Green
        } catch {
            Write-Host " FALHOU (continuando)" -ForegroundColor Yellow
        }
    }

    # PyAudio no Windows — usa wheel pré-compilada
    if (-not $NoVoice) {
        Write-Info "Tentando instalar PyAudio (Windows wheel)..."
        $pyAudioOk = $false
        try {
            & $script:PIP_CMD install PyAudio --quiet 2>$null
            $pyAudioOk = $true
            Write-OK "PyAudio instalado."
        } catch {}

        if (-not $pyAudioOk) {
            Write-Warn "PyAudio falhou. Tentando pipwin..."
            try {
                & $script:PIP_CMD install pipwin --quiet 2>$null
                & $script:PYTHON_CMD -m pipwin install pyaudio 2>$null
                Write-OK "PyAudio instalado via pipwin."
            } catch {
                Write-Warn "PyAudio não instalado — reconhecimento de voz desabilitado."
                Write-Warn "Baixe manualmente: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio"
            }
        }
    }

    Write-OK "Bibliotecas Python instaladas."
}

# ─── Verifica a instalação ────────────────────────────────────────────────────
function Test-Installation {
    Write-Step "Verificando instalação"

    $modules = @("flask", "flask_login", "werkzeug", "requests", "zeroconf", "paramiko")
    if (-not $NoVoice) { $modules += @("speech_recognition", "gtts", "pygame") }

    $allOk = $true
    foreach ($mod in $modules) {
        $result = & $script:PYTHON_CMD -c "import $mod; print(getattr($mod, '__version__', 'ok'))" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  $([char]0x2713) $("{0,-30}" -f $mod) $result" -ForegroundColor Green
        } else {
            Write-Host "  $([char]0x2717) $("{0,-30}" -f $mod) FALHOU" -ForegroundColor Red
            $allOk = $false
        }
    }

    if ($allOk) { Write-OK "Todas as verificações passaram." }
    else { Write-Warn "Algumas verificações falharam — instalação pode estar incompleta." }
}

# ─── Configura o nó ───────────────────────────────────────────────────────────
function Set-NodeConfig {
    Write-Step "Configurando nó"

    $cfgPath = Join-Path $script:INSTALL_DIR "config.py"
    if (-not (Test-Path $cfgPath)) {
        Write-Warn "config.py não encontrado — edite manualmente após a instalação."
        return
    }

    if ($Node -ne "seven") {
        $content = Get-Content $cfgPath -Raw
        $nameMap = @{ "seven" = "Seven"; "spark" = "Spark"; "mobile" = "Mobile" }
        $newName = $nameMap[$Node]

        $content = $content -replace 'NODE_TYPE:\s*str\s*=\s*"[^"]+"',     "NODE_TYPE: str = `"$Node`""
        $content = $content -replace 'ASSISTANT_NAME:\s*str\s*=\s*"[^"]+"', "ASSISTANT_NAME: str = `"$newName`""

        Set-Content $cfgPath $content -Encoding UTF8
        Write-OK "NODE_TYPE configurado como: $Node"
    } else {
        Write-OK "NODE_TYPE: seven (padrão)"
    }
}

# ─── Cria scripts .bat ────────────────────────────────────────────────────────
function Create-RunScripts {
    Write-Step "Criando scripts de execução"

    $venvPy = Join-Path $script:INSTALL_DIR ".venv\Scripts\python.exe"
    $iDir   = $script:INSTALL_DIR

    # run.bat
    @"
@echo off
:: k7-core v2.0 | run.bat
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
echo k7-core v2.0 iniciando...
python core.py %*
pause
"@ | Set-Content (Join-Path $iDir "run.bat") -Encoding UTF8

    # run_seven.bat
    @"
@echo off
:: k7-core | run_seven.bat — Nó Seven (Master com Dashboard)
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python -c "import config; config.NODE_TYPE='seven'; config.ASSISTANT_NAME='Seven'; import core; core.main()"
pause
"@ | Set-Content (Join-Path $iDir "run_seven.bat") -Encoding UTF8

    # run_spark.bat
    @"
@echo off
:: k7-core | run_spark.bat — Nó Spark (Worker headless)
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python -c "import config; config.NODE_TYPE='spark'; config.ASSISTANT_NAME='Spark'; config.NODE_MODE='worker'; config.ENABLE_DASHBOARD=False; import core; core.main()"
pause
"@ | Set-Content (Join-Path $iDir "run_spark.bat") -Encoding UTF8

    # Atalho no Desktop
    try {
        $WshShell  = New-Object -ComObject WScript.Shell
        $Shortcut  = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\k7-core.lnk")
        $Shortcut.TargetPath       = Join-Path $iDir "run.bat"
        $Shortcut.WorkingDirectory = $iDir
        $Shortcut.Description      = "k7-core v2.0 — Assistente Virtual"
        $Shortcut.Save()
        Write-OK "Atalho criado no Desktop."
    } catch {
        Write-Warn "Não foi possível criar atalho no Desktop."
    }

    # Serviço Windows (NSSM — opcional)
    if (Get-Command nssm -ErrorAction SilentlyContinue) {
        Write-Info "NSSM detectado — criando serviço Windows..."
        $svcName = "k7core"
        nssm install $svcName $venvPy "`"$iDir\core.py`"" 2>$null
        nssm set $svcName AppDirectory $iDir 2>$null
        nssm set $svcName DisplayName "k7-core Assistente Virtual v2.0" 2>$null
        nssm set $svcName Start SERVICE_AUTO_START 2>$null
        Write-OK "Serviço Windows criado: $svcName"
        Write-Info "Para iniciar: nssm start $svcName"
    } else {
        Write-Info "NSSM não encontrado — serviço Windows não criado."
        Write-Info "Instale NSSM para executar como serviço: https://nssm.cc/"
    }

    Write-OK "Scripts criados em: $iDir"
}

# ─── Chave SSH ────────────────────────────────────────────────────────────────
function Setup-SSH {
    if ($NoSSH) { return }

    Write-Step "Configurando chave SSH"

    $sshDir = Join-Path $env:USERPROFILE ".ssh"
    $sshKey = Join-Path $sshDir "id_rsa"

    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
    }

    if (Test-Path $sshKey) {
        Write-Info "Chave SSH já existe: $sshKey"
        return
    }

    if (Get-Command ssh-keygen -ErrorAction SilentlyContinue) {
        Write-Info "Gerando chave RSA 4096 bits..."
        ssh-keygen -t rsa -b 4096 -f $sshKey -N '""' -C "k7-core@$env:COMPUTERNAME" 2>$null
        Write-OK "Chave gerada: $sshKey"
        $pubKey = Get-Content "$sshKey.pub"
        Write-Info "Chave pública:"
        Write-Host "  $pubKey" -ForegroundColor DarkGray
    } else {
        Write-Warn "ssh-keygen não encontrado. Instale OpenSSH ou Git for Windows."
    }
}

# ─── Resumo final ─────────────────────────────────────────────────────────────
function Show-Summary {
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║          k7-core v2.0 instalado com sucesso!          ║" -ForegroundColor Green
    Write-Host "  ╚═══════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Diretório:  $($script:INSTALL_DIR)" -ForegroundColor White
    Write-Host "  Nó:         $Node"                  -ForegroundColor White
    Write-Host "  Dashboard:  http://localhost:2026/dashboard" -ForegroundColor White
    Write-Host ""
    Write-Host "  Próximos passos:" -ForegroundColor White
    Write-Host "  1. Edite " -NoNewline; Write-Host "config.py" -ForegroundColor Cyan -NoNewline; Write-Host " com seus IPs, MACs e segredos"
    Write-Host "  2. Gere a credencial GitHub: " -NoNewline; Write-Host "python updater.py --gen-cred" -ForegroundColor Cyan
    Write-Host "  3. Crie seu usuário: " -NoNewline; Write-Host "python manage_auth.py create-user" -ForegroundColor Cyan
    Write-Host "  4. Inicie: " -NoNewline; Write-Host ".\run.bat" -ForegroundColor Cyan -NoNewline; Write-Host " ou " -NoNewline; Write-Host ".\run_$($Node).bat" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Credenciais padrão: mestre / k7mestre" -ForegroundColor DarkGray
    Write-Host ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────
Write-Banner

Write-Info "Sistema:    Windows $([System.Environment]::OSVersion.Version)"
Write-Info "Nó alvo:    $Node"
Write-Info "Diretório:  $Dir"
Write-Host ""

$script:INSTALL_DIR = $Dir
$script:PYTHON_CMD  = "python"
$script:PIP_CMD     = "pip"

Test-Prerequisites
Install-Espeak
Get-Code
Setup-Venv
Install-PythonDeps
Test-Installation
Setup-SSH
Set-NodeConfig
Create-RunScripts
Show-Summary
