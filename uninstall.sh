#!/usr/bin/env bash
# =============================================================================
# k7-core | uninstall.sh — Desinstalador Inteligente
# Repositório: https://github.com/ksevendev/Assistente
#
# Uso:
#   chmod +x uninstall.sh && ./uninstall.sh [opções]
#
# Opções:
#   --full          Remove TUDO incluindo o diretório
#   --keep-data     Mantém data/ (banco SQLite e histórico)
#   --keep-config   Mantém config.py
#   --service-only  Remove apenas o serviço systemd
#   --dry-run       Mostra o que seria removido
#   --yes           Sem confirmações
#   --dir CAMINHO   Diretório de instalação (padrão: diretório do script)
# =============================================================================

set -euo pipefail

R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' C='\033[0;96m'
BOLD='\033[1m' DIM='\033[2m' RST='\033[0m'

info()  { printf "  ${C}•${RST}  %s\n" "$*"; }
ok()    { printf "  ${G}✓${RST}  %s\n" "$*"; }
warn()  { printf "  ${Y}⚠${RST}  %s\n" "$*"; }
err()   { printf "  ${R}✗${RST}  %s\n" "$*" >&2; }
step()  { printf "\n${BOLD}${C}  ━━━  %s${RST}\n\n" "$*"; }
dry()   { printf "  ${DIM}[DRY] Removeria: %s${RST}\n" "$*"; }

# Defaults
FULL=false
KEEP_DATA=false
KEEP_CONFIG=false
SERVICE_ONLY=false
DRY=false
AUTO_YES=false
IS_TERMUX=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
INSTALL_DIR="$SCRIPT_DIR"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)         FULL=true;         shift ;;
    --keep-data)    KEEP_DATA=true;    shift ;;
    --keep-config)  KEEP_CONFIG=true;  shift ;;
    --service-only) SERVICE_ONLY=true; shift ;;
    --dry-run)      DRY=true;          shift ;;
    --yes|-y)       AUTO_YES=true;     shift ;;
    --dir)          INSTALL_DIR="$2";  shift 2 ;;
    --help|-h)
      printf "k7-core Desinstalador\n\nOpções:\n"
      printf "  --full           Remove tudo incluindo o diretório\n"
      printf "  --keep-data      Preserva banco SQLite e histórico\n"
      printf "  --keep-config    Preserva config.py\n"
      printf "  --service-only   Remove apenas o serviço systemd\n"
      printf "  --dry-run        Simulação sem remover nada\n"
      printf "  --yes            Sem confirmações\n"
      printf "  --dir CAMINHO    Diretório de instalação\n"
      exit 0 ;;
    *) warn "Flag desconhecida: $1"; shift ;;
  esac
done

[[ -n "${TERMUX_VERSION:-}" ]] || [[ -d "/data/data/com.termux" ]] && IS_TERMUX=true

# ── Banner ────────────────────────────────────────────────────────────────────
printf "\n${BOLD}${R}"
cat << 'BANNER'
  ██╗  ██╗███████╗      ██████╗ ██████╗ ██████╗ ███████╗
  ██║ ██╔╝╚════██║     ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  █████╔╝     ██╔╝     ██║     ██║   ██║██████╔╝█████╗
  ██╔═██╗    ██╔╝      ██║     ██║   ██║██╔══██╗██╔══╝
  ██║  ██╗   ██║       ╚██████╗╚██████╔╝██║  ██║███████╗
  ╚═╝  ╚═╝   ╚═╝        ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝
BANNER
printf "${RST}"
printf "  ${BOLD}Desinstalador${RST} — ${DIM}https://github.com/ksevendev/Assistente${RST}\n\n"

# Detecta versão instalada
K7_VER="desconhecida"
if [[ -f "${INSTALL_DIR}/config.py" ]]; then
  K7_VER=$(grep -oP "K7_VERSION.*?['\"](\d\.\d)['\"]" "${INSTALL_DIR}/config.py" | grep -oP "\d\.\d" | head -1 || echo "2.0")
fi

if [[ ! -f "${INSTALL_DIR}/config.py" ]]; then
  err "Instalação não encontrada em: ${INSTALL_DIR}"
  info "Use --dir CAMINHO para especificar o diretório correto."
  exit 1
fi

info "Instalação k7-core v${K7_VER} encontrada em: ${INSTALL_DIR}"

# ── Dry-run helper ─────────────────────────────────────────────────────────
rm_item() {
  local type="$1" target="$2" desc="${3:-}"
  if $DRY; then dry "${type}: ${target} ${desc}"; return; fi
  case "$type" in
    file) [[ -f "$target" ]] && rm -f "$target" && ok "Removido: $(basename "$target") ${desc}" ;;
    dir)  [[ -d "$target" ]] && rm -rf "$target" && ok "Removida pasta: $(basename "$target") ${desc}" ;;
  esac
}

# ── Confirmação ────────────────────────────────────────────────────────────
if ! $SERVICE_ONLY; then
  printf "\n  ${BOLD}${Y}O que será removido:${RST}\n\n"
  printf "  • Ambiente virtual Python (.venv/)\n"
  printf "  • Scripts run*.sh e arquivos temporários\n"
  printf "  • Logs e cache Python (__pycache__/)\n"
  [[ "$K7_VER" == "3"* ]] && printf "  • Base ChromaDB (data/chroma/) — memória da IA\n"
  $KEEP_DATA   || printf "  • ${R}Banco de dados e histórico (data/)${RST}\n"
  $KEEP_CONFIG || printf "  • ${R}Configurações (config.py)${RST}\n"
  $FULL        && printf "  • ${R}DIRETÓRIO COMPLETO: ${INSTALL_DIR}${RST}\n"
  printf "\n"
  $DRY && info "MODO DRY-RUN: nada será removido."

  if ! $AUTO_YES && ! $DRY; then
    printf "  Confirmar desinstalação? [s/N] "
    read -r _reply
    [[ "${_reply,,}" != "s" ]] && { info "Desinstalação cancelada."; exit 0; }
  fi
fi

# ── Para processos ─────────────────────────────────────────────────────────
step "Parando processos"
_pids=$(pgrep -f "python.*core\.py" 2>/dev/null || true)
if [[ -n "$_pids" ]]; then
  if $DRY; then dry "Mataria PIDs: $_pids"
  else
    echo "$_pids" | xargs kill -SIGTERM 2>/dev/null || true
    sleep 1; echo "$_pids" | xargs kill -SIGKILL 2>/dev/null || true
    ok "Processos encerrados."
  fi
else
  info "Nenhum processo k7-core em execução."
fi

# ── Serviço systemd ────────────────────────────────────────────────────────
step "Serviço systemd"
if command -v systemctl &>/dev/null && ! $IS_TERMUX; then
  _svc="${HOME}/.config/systemd/user/k7core.service"
  if systemctl --user is-active k7core &>/dev/null 2>&1; then
    $DRY && dry "Pararia e removeria k7core.service" || {
      systemctl --user stop k7core    2>/dev/null || true
      systemctl --user disable k7core 2>/dev/null || true
      ok "Serviço k7core parado e desabilitado."
    }
  fi
  rm_item file "$_svc" "(serviço systemd)"
  $DRY || systemctl --user daemon-reload 2>/dev/null || true
else
  info "systemd não disponível — pulando."
fi

$SERVICE_ONLY && { ok "Remoção do serviço concluída."; exit 0; }

# ── Ambiente Python ────────────────────────────────────────────────────────
step "Ambiente Python"
rm_item dir  "${INSTALL_DIR}/.venv" "(ambiente virtual)"
rm_item dir  "${INSTALL_DIR}/__pycache__"
if ! $DRY; then
  find "${INSTALL_DIR}" -name "*.pyc" -delete 2>/dev/null || true
  find "${INSTALL_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
  ok "Cache Python removido."
fi

# ── Scripts de execução ────────────────────────────────────────────────────
step "Scripts"
for _s in run.sh run_seven.sh run_spark.sh run_mobile.sh; do
  rm_item file "${INSTALL_DIR}/${_s}"
done

# ── v3 — ChromaDB ─────────────────────────────────────────────────────────
if [[ "$K7_VER" == "3"* ]]; then
  step "Base de Conhecimento (v3.0)"
  rm_item dir "${INSTALL_DIR}/data/chroma" "(vetores ChromaDB)"
  rm_item file "${INSTALL_DIR}/data/episodic.db" "(memória episódica)"
fi

# ── Dados e logs ───────────────────────────────────────────────────────────
step "Dados e Logs"
rm_item dir "${INSTALL_DIR}/tmp"  "(temporários)"
rm_item dir "${INSTALL_DIR}/logs" "(logs)"

if ! $KEEP_DATA; then
  warn "Removendo dados persistentes..."
  rm_item file "${INSTALL_DIR}/data/k7auth.db"           "(banco de usuários)"
  rm_item file "${INSTALL_DIR}/data/update_history.json"  "(histórico updates)"
  rm_item file "${INSTALL_DIR}/data/.update.lock"         "(file lock)"
  if ! $DRY && [[ -d "${INSTALL_DIR}/data" ]]; then
    rmdir "${INSTALL_DIR}/data" 2>/dev/null \
      && ok "Pasta data/ removida." \
      || warn "Pasta data/ contém arquivos extras — mantida."
  fi
else
  info "Dados preservados (--keep-data)."
fi

# ── Configuração ───────────────────────────────────────────────────────────
step "Configuração"
if $KEEP_CONFIG; then
  info "config.py preservado (--keep-config)."
else
  if [[ -f "${INSTALL_DIR}/config.py" ]] && ! $DRY; then
    local _bk="${HOME}/k7core_config_backup_$(date +%Y%m%d_%H%M%S).py"
    cp "${INSTALL_DIR}/config.py" "$_bk" && info "Backup salvo em: $_bk"
  fi
  rm_item file "${INSTALL_DIR}/config.py" "(configuração principal)"
fi

# ── Remoção total ─────────────────────────────────────────────────────────
if $FULL; then
  step "Remoção total"
  cd "${HOME}"
  rm_item dir "${INSTALL_DIR}" "(diretório completo)"
else
  info "Diretório ${INSTALL_DIR} preservado."
fi

# ── Resumo ─────────────────────────────────────────────────────────────────
printf "\n"
if $DRY; then
  printf "  ${Y}DRY-RUN: nada foi removido.${RST}\n\n"
else
  printf "  ${BOLD}${G}k7-core v${K7_VER} desinstalado com sucesso.${RST}\n\n"
  $KEEP_DATA   && info "Dados preservados em: ${INSTALL_DIR}/data/"
  $KEEP_CONFIG && info "Config preservado em: ${INSTALL_DIR}/config.py"
fi
