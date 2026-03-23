#!/usr/bin/env bash
# =============================================================================
# k7-core v2.0 | uninstall.sh
# Desinstalador — remove o k7-core e seus componentes do sistema.
#
# Uso:
#   chmod +x uninstall.sh && ./uninstall.sh [opções]
#
# Opções:
#   --full          Remove TUDO incluindo dados, logs e chave SSH
#   --keep-data     Mantém data/ (banco SQLite e histórico de updates)
#   --keep-config   Mantém config.py com suas configurações
#   --keep-ssh      Não remove a chave SSH (~/.ssh/id_rsa)
#   --service-only  Remove apenas o serviço systemd
#   --dry-run       Mostra o que seria removido sem remover nada
#   --yes           Não pede confirmação (modo silencioso)
# =============================================================================

set -euo pipefail

# ─── Cores ───────────────────────────────────────────────────────────────────
R='\033[0;31m'; G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;96m'
B='\033[0;34m'; BOLD='\033[1m'; DIM='\033[2m'; RST='\033[0m'

log_info()  { printf "${C}[INFO]${RST}  %s\n" "$*"; }
log_ok()    { printf "${G}[ OK ]${RST}  %s\n" "$*"; }
log_warn()  { printf "${Y}[WARN]${RST}  %s\n" "$*"; }
log_error() { printf "${R}[ERRO]${RST}  %s\n" "$*" >&2; }
log_step()  { printf "\n${BOLD}${C}━━━ %s ${RST}\n" "$*"; }
log_dry()   { printf "${DIM}[DRY]${RST}  ${DIM}%s${RST}\n" "$*"; }

# ─── Defaults ─────────────────────────────────────────────────────────────────
FULL_REMOVE=false
KEEP_DATA=false
KEEP_CONFIG=false
KEEP_SSH=true        # por padrão, NÃO remove a chave SSH
SERVICE_ONLY=false
DRY_RUN=false
AUTO_YES=false
IS_TERMUX=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${SCRIPT_DIR}"

# ─── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)         FULL_REMOVE=true; KEEP_SSH=false; shift ;;
    --keep-data)    KEEP_DATA=true;    shift ;;
    --keep-config)  KEEP_CONFIG=true;  shift ;;
    --keep-ssh)     KEEP_SSH=true;     shift ;;
    --service-only) SERVICE_ONLY=true; shift ;;
    --dry-run)      DRY_RUN=true;      shift ;;
    --yes|-y)       AUTO_YES=true;     shift ;;
    --dir)          INSTALL_DIR="$2";  shift 2 ;;
    --help|-h)
      printf "k7-core v2.0 | Desinstalador\n\n"
      printf "Opções:\n"
      printf "  --full          Remove TUDO (inclui chave SSH)\n"
      printf "  --keep-data     Mantém data/ (banco e histórico)\n"
      printf "  --keep-config   Mantém config.py\n"
      printf "  --keep-ssh      Mantém ~/.ssh/id_rsa (padrão)\n"
      printf "  --service-only  Remove apenas serviço systemd\n"
      printf "  --dry-run       Mostra o que seria removido\n"
      printf "  --yes           Sem confirmação interativa\n"
      printf "  --dir CAMINHO   Diretório de instalação (padrão: dir do script)\n"
      exit 0 ;;
    *) log_error "Argumento desconhecido: $1"; exit 1 ;;
  esac
done

# ─── Detecção de ambiente ─────────────────────────────────────────────────────
if [[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]]; then
  IS_TERMUX=true
fi

# ─── Banner ───────────────────────────────────────────────────────────────────
printf "\n${BOLD}${R}"
cat << 'EOF'
  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗
  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝
  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗
  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝
EOF
printf "${RST}"
printf "  ${BOLD}k7-core v2.0${RST} ${DIM}— Desinstalador${RST}\n\n"

# ─── Verificação de diretório ─────────────────────────────────────────────────
if [[ ! -f "${INSTALL_DIR}/config.py" ]]; then
  log_error "Instalação do k7-core não encontrada em: ${INSTALL_DIR}"
  log_info  "Use --dir CAMINHO para especificar o diretório correto."
  exit 1
fi

log_info "Instalação encontrada em: ${INSTALL_DIR}"

# ─── Função de remoção (suporta dry-run) ─────────────────────────────────────
do_remove() {
  local type="$1"  # file | dir | cmd
  local target="$2"
  local desc="${3:-}"

  if $DRY_RUN; then
    log_dry "REMOVERIA ${type}: ${target} ${desc:+(${desc})}"
    return
  fi

  case "$type" in
    file)
      if [[ -f "$target" ]]; then
        rm -f "$target"
        log_ok "Removido: $(basename "${target}") ${desc:+(${desc})}"
      fi
      ;;
    dir)
      if [[ -d "$target" ]]; then
        rm -rf "$target"
        log_ok "Removida pasta: $(basename "${target}") ${desc:+(${desc})}"
      fi
      ;;
    cmd)
      eval "$target" && log_ok "${desc:-Comando executado.}" || log_warn "Falha: ${target}"
      ;;
  esac
}

# ─── Confirma com o usuário ───────────────────────────────────────────────────
confirm_uninstall() {
  printf "\n${BOLD}${Y}⚠  O que será removido:${RST}\n\n"
  printf "  • Ambiente virtual Python ${INSTALL_DIR}/.venv\n"
  printf "  • Scripts de execução (run*.sh)\n"
  printf "  • Arquivos temporários (tmp/)\n"
  if ! $KEEP_DATA; then
    printf "  • ${R}Banco de dados e histórico (data/)${RST}\n"
  fi
  if ! $KEEP_CONFIG; then
    printf "  • ${R}Configurações (config.py)${RST}\n"
  fi
  if ! $KEEP_SSH && ! $IS_TERMUX; then
    printf "  • ${R}Chave SSH (~/.ssh/id_rsa)${RST}\n"
  fi
  printf "  • Serviço systemd (se instalado)\n"
  printf "  • Pacotes de sistema instalados pelo k7-core\n"

  if $FULL_REMOVE; then
    printf "\n  ${R}${BOLD}MODO COMPLETO: o diretório ${INSTALL_DIR} será removido por inteiro.${RST}\n"
  fi

  printf "\n"

  if $AUTO_YES; then return; fi

  if $DRY_RUN; then
    log_info "Modo DRY-RUN: apenas simulação, nada será removido."
    return
  fi

  printf "${BOLD}Confirmar desinstalação? [s/N]${RST} "
  read -r reply
  if [[ "${reply,,}" != "s" ]]; then
    log_info "Desinstalação cancelada."
    exit 0
  fi
}

# ─── Para processos em execução ───────────────────────────────────────────────
stop_processes() {
  log_step "Parando processos k7-core"

  # Para serviço systemd
  if command -v systemctl &>/dev/null && ! $IS_TERMUX; then
    if systemctl --user is-active k7core &>/dev/null 2>&1; then
      if $DRY_RUN; then
        log_dry "PARARIA serviço: k7core.service"
      else
        systemctl --user stop k7core 2>/dev/null && log_ok "Serviço k7core parado." || true
      fi
    fi
  fi

  # Mata processos core.py em execução
  local pids
  pids="$(pgrep -f "python.*core\.py" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    if $DRY_RUN; then
      log_dry "MATARIA PIDs: ${pids}"
    else
      echo "$pids" | xargs kill -SIGTERM 2>/dev/null || true
      sleep 1
      echo "$pids" | xargs kill -SIGKILL 2>/dev/null || true
      log_ok "Processos k7-core encerrados (PIDs: ${pids})."
    fi
  else
    log_info "Nenhum processo k7-core em execução."
  fi
}

# ─── Remove serviço systemd ───────────────────────────────────────────────────
remove_systemd_service() {
  log_step "Removendo serviço systemd"

  if $IS_TERMUX || ! command -v systemctl &>/dev/null; then
    log_info "systemd não disponível — pulando."
    return
  fi

  local svc_file="${HOME}/.config/systemd/user/k7core.service"

  if systemctl --user is-enabled k7core &>/dev/null 2>&1; then
    do_remove cmd "systemctl --user disable k7core 2>/dev/null" "serviço desabilitado"
  fi

  do_remove file "${svc_file}" "arquivo de serviço"

  if ! $DRY_RUN; then
    systemctl --user daemon-reload 2>/dev/null || true
    log_ok "systemd recarregado."
  fi
}

# ─── Remove ambiente Python ───────────────────────────────────────────────────
remove_python_env() {
  log_step "Removendo ambiente virtual Python"

  do_remove dir  "${INSTALL_DIR}/.venv"     "ambiente virtual"
  do_remove dir  "${INSTALL_DIR}/__pycache__" "cache Python"
  do_remove dir  "${INSTALL_DIR}/commands/__pycache__" "cache de comandos"

  # .pyc files
  if ! $DRY_RUN; then
    find "${INSTALL_DIR}" -name "*.pyc" -delete 2>/dev/null || true
    find "${INSTALL_DIR}" -name "*.pyo" -delete 2>/dev/null || true
    log_ok "Arquivos .pyc removidos."
  else
    log_dry "REMOVERIA: todos os *.pyc e *.pyo em ${INSTALL_DIR}"
  fi
}

# ─── Remove scripts de execução ───────────────────────────────────────────────
remove_run_scripts() {
  log_step "Removendo scripts de execução"

  local scripts=(
    "${INSTALL_DIR}/run.sh"
    "${INSTALL_DIR}/run_seven.sh"
    "${INSTALL_DIR}/run_spark.sh"
    "${INSTALL_DIR}/run_mobile.sh"
  )

  for s in "${scripts[@]}"; do
    do_remove file "$s"
  done
}

# ─── Remove dados e logs ─────────────────────────────────────────────────────
remove_data() {
  log_step "Removendo dados e logs"

  do_remove dir "${INSTALL_DIR}/tmp"  "arquivos temporários"
  do_remove dir "${INSTALL_DIR}/logs" "logs"

  if ! $KEEP_DATA; then
    log_warn "Removendo dados persistentes (banco SQLite e histórico)..."
    do_remove file "${INSTALL_DIR}/data/k7auth.db"             "banco de usuários"
    do_remove file "${INSTALL_DIR}/data/update_history.json"    "histórico de updates"
    do_remove file "${INSTALL_DIR}/data/.update.lock"           "file lock"
    # Remove a pasta data se vazia
    if ! $DRY_RUN && [[ -d "${INSTALL_DIR}/data" ]]; then
      rmdir "${INSTALL_DIR}/data" 2>/dev/null \
        && log_ok "Pasta data/ removida." \
        || log_warn "Pasta data/ não estava vazia — mantida."
    fi
  else
    log_info "Dados preservados (--keep-data): ${INSTALL_DIR}/data/"
  fi
}

# ─── Remove configuração ──────────────────────────────────────────────────────
remove_config() {
  log_step "Removendo configuração"

  if $KEEP_CONFIG; then
    log_info "Configuração preservada (--keep-config): ${INSTALL_DIR}/config.py"
    return
  fi

  # Faz backup antes de remover
  if [[ -f "${INSTALL_DIR}/config.py" ]] && ! $DRY_RUN; then
    local backup="${HOME}/k7core_config_backup_$(date +%Y%m%d_%H%M%S).py"
    cp "${INSTALL_DIR}/config.py" "${backup}"
    log_info "Backup do config.py salvo em: ${backup}"
  fi

  do_remove file "${INSTALL_DIR}/config.py" "configuração principal"
}

# ─── Remove chave SSH ─────────────────────────────────────────────────────────
remove_ssh() {
  log_step "Tratando chave SSH"

  if $KEEP_SSH || $IS_TERMUX; then
    log_info "Chave SSH preservada: ~/.ssh/id_rsa"
    return
  fi

  if [[ -f "${HOME}/.ssh/id_rsa" ]]; then
    printf "${Y}  ⚠  Remover chave SSH ${HOME}/.ssh/id_rsa ?${RST}\n"
    printf "  ${DIM}(Isso pode quebrar outros serviços que usam esta chave)${RST}\n"
    if ! $AUTO_YES; then
      printf "  Confirmar? [s/N] "
      read -r reply
      if [[ "${reply,,}" != "s" ]]; then
        log_info "Chave SSH mantida."
        return
      fi
    fi
    do_remove file "${HOME}/.ssh/id_rsa"     "chave privada"
    do_remove file "${HOME}/.ssh/id_rsa.pub" "chave pública"
  fi
}

# ─── Remove pacotes de sistema ────────────────────────────────────────────────
remove_system_packages() {
  if ! $FULL_REMOVE; then
    log_info "Pacotes de sistema preservados (use --full para remover)."
    return
  fi

  log_step "Removendo pacotes de sistema (modo --full)"
  log_warn "Remoção de pacotes pode afetar outros programas."

  if $IS_TERMUX; then
    log_info "No Termux, não removemos pacotes automaticamente."
    return
  fi

  if command -v apt-get &>/dev/null; then
    local apt_k7_pkgs=(espeak-ng playerctl)
    printf "  Remover pacotes apt instalados pelo k7-core? [s/N] "
    if ! $AUTO_YES; then read -r reply; else reply="n"; fi
    if [[ "${reply,,}" == "s" ]]; then
      do_remove cmd \
        "DEBIAN_FRONTEND=noninteractive sudo apt-get remove -y ${apt_k7_pkgs[*]} --auto-remove -qq 2>/dev/null" \
        "pacotes apt removidos"
    else
      log_info "Pacotes apt preservados."
    fi
  fi
}

# ─── Remove diretório completo (modo --full) ──────────────────────────────────
remove_directory() {
  if ! $FULL_REMOVE; then
    log_info "Diretório ${INSTALL_DIR} preservado."
    log_info "Para remover manualmente: rm -rf ${INSTALL_DIR}"
    return
  fi

  log_step "Removendo diretório de instalação completo"

  # Sai do diretório antes de removê-lo
  cd "${HOME}"

  do_remove dir "${INSTALL_DIR}" "diretório completo de instalação"
}

# ─── Resumo ───────────────────────────────────────────────────────────────────
print_summary() {
  printf "\n"
  if $DRY_RUN; then
    printf "${BOLD}${Y}━━━ Resumo (DRY-RUN — nada foi removido) ━━━${RST}\n\n"
    log_info "Execute sem --dry-run para aplicar a desinstalação."
  else
    printf "${BOLD}${G}"
    cat << 'EOF'
  ╔═══════════════════════════════════════════════════════╗
  ║         k7-core v2.0 desinstalado com sucesso!        ║
  ╚═══════════════════════════════════════════════════════╝
EOF
    printf "${RST}"

    if $KEEP_DATA; then
      printf "\n  ${Y}Dados preservados em:${RST} %s/data/\n" "${INSTALL_DIR}"
    fi
    if $KEEP_CONFIG; then
      printf "  ${Y}Configuração preservada em:${RST} %s/config.py\n" "${INSTALL_DIR}"
    fi
    if [[ -f "${HOME}/.ssh/id_rsa" ]]; then
      printf "  ${Y}Chave SSH mantida em:${RST} ~/.ssh/id_rsa\n"
    fi
  fi
  printf "\n"
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
  if $SERVICE_ONLY; then
    stop_processes
    remove_systemd_service
    log_ok "Remoção do serviço concluída."
    return
  fi

  confirm_uninstall
  stop_processes
  remove_systemd_service
  remove_python_env
  remove_run_scripts
  remove_data
  remove_config
  remove_ssh
  remove_system_packages
  remove_directory
  print_summary
}

main "$@"
