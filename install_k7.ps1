# Configurações do Nó
$NODE_NAME = "loh"
$INSTALL_PATH = "C:\KRede"

Write-Host "--- Instalando K7 Instance: $NODE_NAME ---" -ForegroundColor Cyan

# 1. Criar diretórios
if (!(Test-Path $INSTALL_PATH)) {
    New-Item -ItemType Directory -Path $INSTALL_PATH
    Write-Host "[OK] Pasta C:\KRede criada."
}

Set-Location $INSTALL_PATH

# 2. Criar Ambiente Virtual (VENV)
Write-Host "[...] Criando ambiente virtual Python..."
python -m venv venv
if ($LASTEXITCODE -ne 0) { 
    Write-Host "[ERRO] Python não encontrado no PATH!" -ForegroundColor Red
    exit 
}

# 3. Instalar Dependências
Write-Host "[...] Instalando Flask e dependências..."
.\venv\Scripts\pip install flask flask-login werkzeug python-dotenv requests

# 4. Criar Script de Inicialização (Launch.bat)
$BATCH_CONTENT = @"
@echo off
cd /d $INSTALL_PATH
echo Iniciando K7 Instance: $NODE_NAME
.\venv\Scripts\python.exe core.py
pause
"@
$BATCH_CONTENT | Out-File -FilePath "run_k7.bat" -Encoding ascii

Write-Host "--- INSTALAÇÃO CONCLUÍDA ---" -ForegroundColor Green
Write-Host "1. Copie seu core.py e config.py para $INSTALL_PATH"
Write-Host "2. Edite o config.py: NODE_TYPE = '$NODE_NAME'"
Write-Host "3. Execute o arquivo 'run_k7.bat' para testar."