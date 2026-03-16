#!/bin/bash

################################################################################
# K7-Core v4.1 - Update Script
# Compatível com: Debian, Ubuntu, Termux
# Uso: bash update.sh <node_id>
################################################################################

set -e  # Exit on error

NODE_ID=${1:-seven}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$BASE_DIR/logs/update_${NODE_ID}_$(date +%s).log"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

################################################################################
# FUNÇÕES
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Detectar plataforma
detect_platform() {
    if [[ -d "/data/data/com.termux" ]] || [[ "$TERM" == "xterm-256color" ]]; then
        echo "termux"
    else
        echo "linux"
    fi
}

# Parar o serviço systemd
stop_service() {
    log_info "Parando serviço k7-core-${NODE_ID}..."
    
    if systemctl is-active --quiet "k7-core-${NODE_ID}"; then
        sudo systemctl stop "k7-core-${NODE_ID}" || log_warning "Falha ao parar serviço"
    else
        log_warning "Serviço não está em execução"
    fi
}

# Git Pull
git_pull() {
    log_info "Atualizando repositório Git..."
    
    cd "$BASE_DIR"
    
    # Verificar se é um repositório Git
    if [[ -d ".git" ]]; then
        git fetch origin || log_error "Falha ao fazer fetch do Git"
        git pull origin main || git pull origin master || log_error "Falha ao fazer pull do Git"
        log_success "Git pull concluído"
    else
        log_warning "Não é um repositório Git válido"
    fi
}

# Instalar dependências
install_dependencies() {
    log_info "Instalando dependências Python..."
    
    PLATFORM=$(detect_platform)
    
    if [[ ! -f "$BASE_DIR/requirements.txt" ]]; then
        log_warning "requirements.txt não encontrado"
        return 1
    fi
    
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        log_error "Python não está instalado"
        return 1
    fi
    
    # Instalar com pip
    if [[ "$PLATFORM" == "termux" ]]; then
        # Termux pode ter restrições de permissão
        $PYTHON_CMD -m pip install --upgrade pip --break-system-packages || true
        $PYTHON_CMD -m pip install -r "$BASE_DIR/requirements.txt" --break-system-packages || log_error "Falha ao instalar dependências"
    else
        # Linux desktop/server
        if [[ $EUID -eq 0 ]]; then
            # Rodando como root
            $PYTHON_CMD -m pip install --upgrade pip
            $PYTHON_CMD -m pip install -r "$BASE_DIR/requirements.txt"
        else
            # Usuário normal - usar venv se disponível
            if [[ -d "$BASE_DIR/venv" ]]; then
                source "$BASE_DIR/venv/bin/activate"
                pip install --upgrade pip
                pip install -r "$BASE_DIR/requirements.txt"
            else
                $PYTHON_CMD -m pip install --user --upgrade pip
                $PYTHON_CMD -m pip install --user -r "$BASE_DIR/requirements.txt"
            fi
        fi
    fi
    
    log_success "Dependências instaladas"
}

# Validar integridade do código
validate_code() {
    log_info "Validando integridade do código..."
    
    PYTHON_CMD=$(command -v python3 || command -v python)
    
    # Verificar sintaxe Python
    if ! $PYTHON_CMD -m py_compile "$BASE_DIR/core.py" 2>/dev/null; then
        log_error "Erro de sintaxe em core.py"
        return 1
    fi
    
    log_success "Validação concluída"
}

# Iniciar o serviço
start_service() {
    log_info "Iniciando serviço k7-core-${NODE_ID}..."
    
    sleep 2  # Aguardar para garantir que o processo anterior terminou
    
    sudo systemctl start "k7-core-${NODE_ID}" || log_error "Falha ao iniciar serviço"
    
    # Verificar se iniciou com sucesso
    sleep 2
    if systemctl is-active --quiet "k7-core-${NODE_ID}"; then
        log_success "Serviço iniciado com sucesso"
        return 0
    else
        log_error "Serviço falhou ao iniciar"
        systemctl status "k7-core-${NODE_ID}" | tee -a "$LOG_FILE"
        return 1
    fi
}

# Backup antes de atualizar
backup() {
    log_info "Criando backup..."
    
    BACKUP_DIR="$BASE_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/k7-core_${NODE_ID}_${TIMESTAMP}.tar.gz"
    
    # Fazer backup do código Python e configurações
    tar -czf "$BACKUP_FILE" \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='logs' \
        --exclude='venv' \
        -C "$BASE_DIR" \
        . || log_warning "Falha ao criar backup"
    
    log_success "Backup criado: $BACKUP_FILE"
}

################################################################################
# FLUXO PRINCIPAL
################################################################################

main() {
    log_info "=========================================="
    log_info "K7-Core v4.1 - Update Script"
    log_info "Node: $NODE_ID"
    log_info "Timestamp: $(date)"
    log_info "=========================================="
    
    # Verificar permissões se necessário
    PLATFORM=$(detect_platform)
    if [[ "$PLATFORM" != "termux" ]]; then
        if [[ $EUID -ne 0 ]] && ! sudo -n systemctl status k7-core-${NODE_ID} &>/dev/null; then
            log_warning "Requer permissões de sudo para systemctl"
        fi
    fi
    
    # Executar etapas
    backup || log_warning "Backup falhou, continuando mesmo assim"
    
    stop_service || log_warning "Falha ao parar serviço"
    
    git_pull || log_error "Git pull falhou"
    
    install_dependencies || log_error "Instalação de dependências falhou"
    
    validate_code || { log_error "Validação falhou"; exit 1; }
    
    start_service || { log_error "Serviço não iniciou"; exit 1; }
    
    log_info "=========================================="
    log_success "Atualização concluída com sucesso!"
    log_info "=========================================="
    
    exit 0
}

# Executar
main "$@"
