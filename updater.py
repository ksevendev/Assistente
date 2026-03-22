# =============================================================================
# k7-core | updater.py  — Auto-Update via GitHub (repositório privado)
#
# DESIGN DE SEGURANÇA — credencial distribuída:
#
#   config.GH_CREDENTIAL  →  blob Base64 de "usuario:token:owner/repo"
#                             armazenado de forma opaca — sem decode no config.
#
#   As três funções de extração são PROPOSITALMENTE independentes entre si
#   e distribuídas em regiões diferentes deste arquivo, sem função auxiliar
#   central compartilhada. Cada uma executa sua própria decodificação Base64
#   e seleciona somente o seu campo. Um leitor casual não encontra as três
#   peças no mesmo lugar.
#
#       _gh_identity()   → linha ~60  — decodifica e retorna campo [0] (user)
#       _gh_secret()     → linha ~130 — decodifica e retorna campo [1] (token)
#       _gh_target()     → linha ~340 — decodifica e retorna campo [2] (repo)
#
#   O token nunca é impresso em logs — _redact() mascara antes de qualquer
#   chamada a logger.*. git fetch recebe a URL autenticada mas os logs
#   exibem apenas "<credencial-omitida>".
#
# FLUXO:
#   1. Compara SHA do HEAD local com o último commit do branch via API GitHub.
#   2. Se diferente: git fetch <url-autenticada> + git reset --hard FETCH_HEAD.
#   3. Persiste resultado em data/update_history.json (máx 50 entradas).
#   4. Opcionalmente reinicia via os.execv() após aplicar.
#
# USO:
#   python updater.py --gen-cred    →  gera o Base64 para config.GH_CREDENTIAL
#   python updater.py --check       →  verifica sem aplicar
#   python updater.py --apply       →  verifica e aplica
#   python updater.py --status      →  histórico e commit atual
#   python updater.py --apply --force  →  ignora file-lock (update paralelo)
# =============================================================================

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger("k7.updater")

# =============================================================================
# ── REGIÃO A ─────────────────────────────────────────────────────────────────
# Identificação do operador (campo 0 do blob)
# =============================================================================

def _gh_identity() -> str:
    """
    Retorna o nome de usuário GitHub contido em config.GH_CREDENTIAL.

    Processo: decodifica Base64 → divide em no máximo 3 partes por ':' →
    retorna a primeira parte (índice 0).

    Não conhece os outros campos. Não chama nenhuma outra função de extração.
    """
    try:
        _raw_a = base64.b64decode(config.GH_CREDENTIAL.encode()).decode().strip()
    except Exception as _err_a:
        raise ValueError(
            f"GH_CREDENTIAL não é um Base64 válido: {_err_a}"
        ) from _err_a

    _parts_a = _raw_a.split(":", 2)
    if len(_parts_a) < 1 or not _parts_a[0]:
        raise ValueError("Campo 'usuario' ausente em GH_CREDENTIAL.")

    return _parts_a[0]


# =============================================================================
# ── REGIÃO B ─────────────────────────────────────────────────────────────────
# Autenticação (campo 1 do blob) + mascaramento de segredo
# =============================================================================

def _redact(value: str) -> str:
    """
    Mascara um segredo para exibição segura em logs.
    Exemplo: "ghp_AbCd1234XyZ" → "ghp_Ab****Z"
    """
    if len(value) <= 10:
        return "****"
    return value[:6] + "****" + value[-1:]


def _gh_secret() -> str:
    """
    Retorna o Personal Access Token GitHub contido em config.GH_CREDENTIAL.

    Processo: decodifica Base64 → divide em no máximo 3 partes por ':' →
    retorna a segunda parte (índice 1).

    Não conhece os outros campos. Não chama nenhuma outra função de extração.
    O valor retornado nunca deve ser passado a logger.* diretamente —
    use sempre _redact() antes de qualquer exibição.
    """
    try:
        _raw_b = base64.b64decode(config.GH_CREDENTIAL.encode()).decode().strip()
    except Exception as _err_b:
        raise ValueError(
            f"GH_CREDENTIAL não é um Base64 válido: {_err_b}"
        ) from _err_b

    _parts_b = _raw_b.split(":", 2)
    if len(_parts_b) < 2 or not _parts_b[1]:
        raise ValueError("Campo 'token' ausente em GH_CREDENTIAL.")

    return _parts_b[1]


# =============================================================================
# ── REGIÃO C ─────────────────────────────────────────────────────────────────
# Estrutura de resultado e histórico
# =============================================================================

@dataclass
class UpdateResult:
    """Resultado completo de uma tentativa de atualização."""

    timestamp:     str  = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    success:       bool = False
    had_update:    bool = False
    old_commit:    str  = ""
    new_commit:    str  = ""
    branch:        str  = ""
    repo:          str  = ""
    message:       str  = ""
    error:         str  = ""
    files_changed: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.success

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# ── REGIÃO D ─────────────────────────────────────────────────────────────────
# Destino do repositório (campo 2 do blob)
# Separado das Regiões A e B para que o repositório não esteja adjacente
# ao token no código-fonte.
# =============================================================================

def _gh_target() -> str:
    """
    Retorna o caminho "owner/repositorio" contido em config.GH_CREDENTIAL.

    Processo: decodifica Base64 → divide em no máximo 3 partes por ':' →
    retorna a terceira parte (índice 2), que pode conter '/' no valor.

    Não conhece os outros campos. Não chama nenhuma outra função de extração.
    """
    try:
        _raw_d = base64.b64decode(config.GH_CREDENTIAL.encode()).decode().strip()
    except Exception as _err_d:
        raise ValueError(
            f"GH_CREDENTIAL não é um Base64 válido: {_err_d}"
        ) from _err_d

    _parts_d = _raw_d.split(":", 2)
    if len(_parts_d) < 3 or not _parts_d[2]:
        raise ValueError(
            "Campo 'owner/repositorio' ausente em GH_CREDENTIAL. "
            "Formato esperado antes de codificar: 'usuario:token:owner/repo'."
        )

    return _parts_d[2]


# =============================================================================
# ── REGIÃO E ─────────────────────────────────────────────────────────────────
# UpdateManager — orquestrador principal
# =============================================================================

class UpdateManager:
    """
    Gerencia verificação e aplicação de atualizações do repositório privado.

    Thread-safe via file-lock (evita updates simultâneos: scheduler +
    acionamento manual pelo dashboard ao mesmo tempo).

    Acessa as credenciais somente através de _gh_identity(), _gh_secret()
    e _gh_target() — nunca lê config.GH_CREDENTIAL diretamente.
    """

    def __init__(self) -> None:
        self._history_path = Path(config.DATA_DIR) / "update_history.json"
        self._lock_path    = Path(config.GH_LOCK_FILE)
        self._timer:   Optional[threading.Timer] = None
        self._running: bool = False

        # Valida as três partes da credencial ao inicializar.
        # Falha rápida — melhor descobrir agora que no meio de um update.
        _gh_identity()   # lança ValueError se campo 0 inválido
        _gh_secret()     # lança ValueError se campo 1 inválido
        _gh_target()     # lança ValueError se campo 2 inválido
        logger.debug(
            f"[UPDATER] Credencial válida — user={_gh_identity()} | "
            f"token={_redact(_gh_secret())} | repo={_gh_target()}"
        )

    # ── API pública ───────────────────────────────────────────────────────────

    def check_and_apply(self, force: bool = False) -> UpdateResult:
        """
        Verifica se há commit novo no repositório remoto e aplica se houver.

        Args:
            force: aguarda até 10 s pelo file-lock antes de desistir.

        Returns:
            UpdateResult descrevendo o que aconteceu.
        """
        if not config.ENABLE_AUTO_UPDATE:
            return UpdateResult(
                message="Auto-update desabilitado (ENABLE_AUTO_UPDATE = False)."
            )

        if not self._acquire_lock(wait=force):
            return UpdateResult(message="Outro update em andamento — lock ativo.")

        result = UpdateResult(branch=config.GH_BRANCH, repo=_gh_target())

        try:
            result = self._run_update(result)
        except Exception as exc:
            result.success = False
            result.error   = str(exc)
            logger.error(f"[UPDATER] Erro inesperado: {exc}", exc_info=True)
        finally:
            self._release_lock()
            self._persist(result)

        return result

    def check_only(self) -> dict:
        """
        Consulta o SHA mais recente do branch remoto SEM modificar o repo local.

        Returns:
            dict com has_update, local_commit, remote_commit, branch, repo.
        """
        try:
            local  = self._local_sha()
            remote = self._remote_sha()
            return {
                "has_update":    local != remote,
                "local_commit":  local,
                "remote_commit": remote,
                "branch":        config.GH_BRANCH,
                "repo":          _gh_target(),
            }
        except Exception as exc:
            return {"has_update": False, "error": str(exc)}

    def status(self) -> dict:
        """Retorna estado atual: commit local, histórico e configuração."""
        history = self._load_history()
        return {
            "current_commit":  self._local_sha(),
            "branch":          config.GH_BRANCH,
            "repo":            _gh_target(),
            "enabled":         config.ENABLE_AUTO_UPDATE,
            "check_interval":  config.GH_CHECK_INTERVAL,
            "last_update":     history[-1] if history else {},
            "history_count":   len(history),
        }

    def start_scheduler(self) -> None:
        """Inicia verificação periódica em thread daemon."""
        if not config.ENABLE_AUTO_UPDATE or config.GH_CHECK_INTERVAL <= 0:
            return
        self._running = True
        self._enqueue()
        logger.info(
            f"[UPDATER] Scheduler iniciado — intervalo={config.GH_CHECK_INTERVAL}s | "
            f"repo={_gh_target()} | branch={config.GH_BRANCH}"
        )

    def stop_scheduler(self) -> None:
        """Para o scheduler."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    # ── Núcleo do update ──────────────────────────────────────────────────────

    def _run_update(self, result: UpdateResult) -> UpdateResult:
        """Executa o ciclo completo: comparar → fetch → reset → (reiniciar)."""

        logger.info(
            f"[UPDATER] Verificando '{_gh_target()}' branch '{config.GH_BRANCH}'..."
        )

        result.old_commit = self._local_sha()

        # Consulta commit remoto via API (sem modificar o repo local)
        try:
            remote = self._remote_sha()
        except Exception as exc:
            result.error   = f"API GitHub inacessível: {exc}"
            result.message = result.error
            return result

        # Sem novidades
        if result.old_commit == remote:
            result.success    = True
            result.had_update = False
            result.new_commit = remote
            result.message    = f"Já na versão mais recente ({remote[:8]})."
            logger.info(f"[UPDATER] {result.message}")
            return result

        # Há update — aplica
        result.had_update = True
        logger.info(
            f"[UPDATER] Update: {result.old_commit[:8]} → {remote[:8]}"
        )

        # Monta URL autenticada — _gh_secret() é chamado aqui e descartado
        # após a montagem da string. Nunca logamos auth_url diretamente.
        _u = _gh_identity()
        _t = _gh_secret()
        _r = _gh_target()
        auth_url = f"https://{_u}:{_t}@github.com/{_r}.git"
        del _u, _t, _r   # descarta as partes da memória o mais rápido possível

        # git fetch
        if self._git(
            f"fetch {auth_url} {config.GH_BRANCH}",
            safe_log=f"fetch <credencial-omitida> {config.GH_BRANCH}",
        ) is None:
            result.error   = "git fetch falhou. Verifique token e repositório."
            result.message = result.error
            return result

        # Arquivos que serão alterados
        diff = self._git("diff --name-only HEAD FETCH_HEAD") or ""
        result.files_changed = [l for l in diff.splitlines() if l.strip()]

        # git reset --hard
        if self._git("reset --hard FETCH_HEAD") is None:
            result.error   = "git reset --hard falhou."
            result.message = result.error
            return result

        result.new_commit = self._local_sha()
        result.success    = True
        n = len(result.files_changed)
        result.message = (
            f"Update aplicado: {result.old_commit[:8]} → {result.new_commit[:8]} "
            f"({n} arquivo{'s' if n != 1 else ''} alterado{'s' if n != 1 else ''})."
        )
        logger.info(f"[UPDATER] {result.message}")

        if config.GH_RESTART_ON_UPDATE:
            logger.info("[UPDATER] Reagendando reinício em 3 s...")
            threading.Timer(3.0, self._restart).start()

        return result

    # ── Git helpers ───────────────────────────────────────────────────────────

    def _git(self, args: str, safe_log: Optional[str] = None) -> Optional[str]:
        """
        Executa `git <args>` no BASE_DIR.
        safe_log substitui args nos logs (oculta URLs com token).
        Retorna stdout ou None em caso de erro.
        """
        display = safe_log or args
        logger.debug(f"[UPDATER] git {display}")

        try:
            proc = subprocess.run(
                f"git {args}",
                shell=True,
                cwd=config.BASE_DIR,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"[UPDATER] git {display} → timeout")
            return None

        if proc.returncode != 0:
            # Sanitiza stderr antes de logar — remove o token se aparecer
            stderr_safe = self._sanitize(proc.stderr.strip())
            logger.error(
                f"[UPDATER] git {display} → RC={proc.returncode} | {stderr_safe}"
            )
            return None

        return proc.stdout

    def _sanitize(self, text: str) -> str:
        """Remove o token de uma string antes de logar."""
        try:
            tok = _gh_secret()
            if tok and tok in text:
                text = text.replace(tok, _redact(tok))
        except Exception:
            pass
        return text

    # ── SHA helpers ───────────────────────────────────────────────────────────

    def _local_sha(self) -> str:
        """SHA do commit HEAD local."""
        out = self._git("rev-parse HEAD")
        return out.strip() if out else "unknown"

    def _remote_sha(self) -> str:
        """
        SHA do último commit no branch remoto via API REST do GitHub.
        Usa o token para autenticar — não altera o repo local.
        """
        repo   = _gh_target()
        branch = config.GH_BRANCH
        tok    = _gh_secret()

        url = f"https://api.github.com/repos/{repo}/commits/{branch}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"token {tok}")
        req.add_header("Accept",        "application/vnd.github.v3+json")
        req.add_header("User-Agent",    "k7-core-updater/2.0")

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode())["sha"]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ValueError(
                    "Token inválido ou expirado (HTTP 401). "
                    "Gere um novo token e atualize GH_CREDENTIAL."
                ) from exc
            if exc.code == 404:
                raise ValueError(
                    f"Repositório '{repo}' não encontrado ou token sem acesso (HTTP 404)."
                ) from exc
            raise ValueError(f"GitHub API respondeu HTTP {exc.code}.") from exc

    # ── Restart ───────────────────────────────────────────────────────────────

    def _restart(self) -> None:
        """Reinicia o processo Python atual com os mesmos argumentos."""
        logger.info("[UPDATER] Reiniciando via os.execv()...")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as exc:
            logger.error(f"[UPDATER] Falha ao reiniciar: {exc}")

    # ── Scheduler ─────────────────────────────────────────────────────────────

    def _enqueue(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(config.GH_CHECK_INTERVAL, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        logger.info("[UPDATER] Verificação periódica...")
        result = self.check_and_apply()
        if result.had_update and result.success:
            logger.info(f"[UPDATER] Aplicado automaticamente: {result.message}")
        self._enqueue()

    # ── Histórico ─────────────────────────────────────────────────────────────

    def _persist(self, result: UpdateResult) -> None:
        history = self._load_history()
        history.append(result.to_dict())
        history = history[-50:]
        try:
            self._history_path.write_text(
                json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.error(f"[UPDATER] Falha ao salvar histórico: {exc}")

    def _load_history(self) -> list:
        if not self._history_path.is_file():
            return []
        try:
            return json.loads(self._history_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ── File lock ─────────────────────────────────────────────────────────────

    def _acquire_lock(self, wait: bool = False, timeout: int = 10) -> bool:
        deadline = time.monotonic() + (timeout if wait else 0)
        while True:
            if not self._lock_path.exists():
                try:
                    self._lock_path.write_text(str(os.getpid()))
                    return True
                except Exception:
                    return False
            # Verifica se o PID que criou o lock ainda está vivo
            try:
                pid = int(self._lock_path.read_text())
                os.kill(pid, 0)       # sinal 0 = só testa existência
                if time.monotonic() >= deadline:
                    return False      # lock válido, sem tempo para esperar
                time.sleep(0.4)
            except (ProcessLookupError, ValueError):
                self._lock_path.unlink(missing_ok=True)   # lock stale — remove

    def _release_lock(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except Exception:
            pass


# =============================================================================
# ── REGIÃO F ─────────────────────────────────────────────────────────────────
# Singleton global + helper de geração de credencial
# =============================================================================

_manager: Optional[UpdateManager] = None


def get_update_manager() -> Optional[UpdateManager]:
    """
    Retorna (criando se necessário) o UpdateManager global.
    Retorna None se ENABLE_AUTO_UPDATE=False ou credencial inválida.
    """
    global _manager
    if not config.ENABLE_AUTO_UPDATE:
        return None
    if _manager is None:
        try:
            _manager = UpdateManager()
        except ValueError as exc:
            logger.error(f"[UPDATER] Não inicializado — {exc}")
            return None
    return _manager


def generate_credential(user: str, token: str, repo: str) -> str:
    """
    Gera o valor Base64 para colar em config.GH_CREDENTIAL.

    Args:
        user:  nome de usuário GitHub        (ex: "john")
        token: Personal Access Token         (ex: "ghp_abc123...")
        repo:  caminho owner/repositorio     (ex: "john/k7-core")

    Returns:
        String Base64 pronta para ser colada como valor de GH_CREDENTIAL.

    Segurança:
        Não logue o retorno desta função. Use _redact(token) se precisar
        mostrar algo ao usuário.
    """
    return base64.b64encode(f"{user}:{token}:{repo}".encode()).decode()


# =============================================================================
# ── REGIÃO G ─────────────────────────────────────────────────────────────────
# Entrypoint CLI
# =============================================================================

def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="updater",
        description="k7-core — gerenciador de auto-update via GitHub privado",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python updater.py --gen-cred          gera Base64 para config.py\n"
            "  python updater.py --check             verifica sem aplicar\n"
            "  python updater.py --apply             verifica e aplica\n"
            "  python updater.py --apply --force     ignora file-lock\n"
            "  python updater.py --status            histórico e commit atual\n"
        ),
    )
    ap.add_argument("--gen-cred", action="store_true", help="Gerador interativo de GH_CREDENTIAL")
    ap.add_argument("--check",    action="store_true", help="Verifica sem aplicar")
    ap.add_argument("--apply",    action="store_true", help="Verifica e aplica update")
    ap.add_argument("--force",    action="store_true", help="Ignora file-lock (use com --apply)")
    ap.add_argument("--status",   action="store_true", help="Exibe status e histórico")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.WARNING,          # CLI: silencia DEBUG/INFO do updater
        format="%(levelname)s: %(message)s",
    )

    # ── Gerador de credencial ────────────────────────────────────────────────
    if args.gen_cred:
        import getpass
        print("\n  k7-core · Gerador de GH_CREDENTIAL")
        print("  " + "─" * 40)
        print("  Não compartilhe o resultado gerado.\n")
        usr = input("  Usuário GitHub           : ").strip()
        tok = getpass.getpass("  Personal Access Token    : ")
        rep = input("  Repositório (owner/repo) : ").strip()
        if not all([usr, tok, rep]):
            print("\n  Erro: todos os campos são obrigatórios."); sys.exit(1)
        blob = generate_credential(usr, tok, rep)
        print(f"\n  Cole em config.py:\n")
        print(f'  GH_CREDENTIAL: str = "{blob}"\n')
        print(f"  Token (mascarado): {_redact(tok)}")
        print(f"  Repositório: {rep}\n")
        return

    # ── Operações que precisam do manager ────────────────────────────────────
    mgr = get_update_manager()
    if mgr is None:
        print(
            "Auto-update desabilitado ou credencial inválida.\n"
            "Verifique ENABLE_AUTO_UPDATE e GH_CREDENTIAL em config.py.\n"
            "Use --gen-cred para gerar uma credencial válida."
        )
        sys.exit(1)

    if args.status:
        st = mgr.status()
        lc = st["current_commit"]
        print(f"\n  Repositório  : {st['repo']}")
        print(f"  Branch       : {st['branch']}")
        print(f"  Commit local : {lc[:12] if lc != 'unknown' else 'desconhecido'}")
        print(f"  Habilitado   : {st['enabled']}")
        print(f"  Intervalo    : {st['check_interval']} s")
        print(f"  Histórico    : {st['history_count']} entrada(s)")
        last = st.get("last_update", {})
        if last:
            mark = "✓" if last.get("success") else "✗"
            print(f"\n  Último update: {last.get('timestamp', '?')}")
            print(f"  Resultado    : {mark} {last.get('message', '')}")
        print()
        return

    if args.check:
        info = mgr.check_only()
        if "error" in info:
            print(f"Erro: {info['error']}"); sys.exit(1)
        if info["has_update"]:
            print(f"  Update disponível!")
            print(f"  Local  : {info['local_commit'][:12]}")
            print(f"  Remoto : {info['remote_commit'][:12]}")
        else:
            print(f"  Sem updates. Commit atual: {info['local_commit'][:12]}")
        return

    if args.apply:
        print("  Verificando e aplicando update...")
        result = mgr.check_and_apply(force=args.force)
        if result.success:
            mark = "✓" if result.had_update else "·"
            print(f"  {mark} {result.message}")
            if result.files_changed:
                shown  = result.files_changed[:6]
                extra  = len(result.files_changed) - len(shown)
                joined = ", ".join(shown) + (f" +{extra} mais" if extra else "")
                print(f"    Arquivos: {joined}")
        else:
            print(f"  ✗ {result.error or result.message}")
            sys.exit(1)
        return

    ap.print_help()


if __name__ == "__main__":
    _cli()
