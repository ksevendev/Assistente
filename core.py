# =============================================================================
# k7-core | core.py  — v2.0 (Dynamic Discovery)
#
# MUDANÇAS v2.0:
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │  NodeRegistry  → registro em memória dos nós descobertos via mDNS   │
#   │  ZeroconfManager → anuncia este nó e descobre peers automaticamente  │
#   │  _build_worker_app()  → Flask headless (apenas /cmd, /health)        │
#   │  _build_master_app()  → Flask completo (dashboard, auth, /api/*)     │
#   │  Porta 2026           → API_PORT atualizada                          │
#   │  SECRET_KEY validação → toda chamada inter-nó exige API_SECRET       │
#   └─────────────────────────────────────────────────────────────────────┘
#
# FLUXO DE INICIALIZAÇÃO:
#   1. Assistant.__init__()  → instancia CommandLoader + NodeRegistry
#   2. Assistant.run()
#       a. ZeroconfManager.start()  → anuncia serviço mDNS + inicia browser
#       b. Aguarda DISCOVERY_BOOT_WAIT  → dá tempo para peers responderem
#       c. _run_flask_server() em thread daemon
#          - se Master: _build_master_app()  (dashboard + auth + /api/*)
#          - se Worker: _build_worker_app()  (headless, sem templates)
#       d. Loop de voz ou modo Android/texto
# =============================================================================

from __future__ import annotations

import importlib.util
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from datetime import timedelta

import config

# ---------------------------------------------------------------------------
# Imports condicionais — módulos pesados desabilitados no Android
# ---------------------------------------------------------------------------

_STT_AVAILABLE = False
if not config.IS_ANDROID:
    try:
        import speech_recognition as sr
        _STT_AVAILABLE = True
    except ImportError:
        pass

try:
    from flask import (Flask, request, jsonify, render_template,
                       redirect, url_for, session, flash)
    from flask_login import (LoginManager, UserMixin,
                              login_user, logout_user,
                              login_required, current_user)
    from werkzeug.security import generate_password_hash, check_password_hash
    _FLASK_OK = True
except ImportError as _e:
    _FLASK_OK = False

try:
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# Zeroconf — biblioteca de mDNS
try:
    from zeroconf import (ServiceBrowser, ServiceInfo, Zeroconf,
                          ServiceStateChange)
    _ZEROCONF_OK = True
except ImportError:
    _ZEROCONF_OK = False

# ---------------------------------------------------------------------------
# Logging com paleta por nó
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD  = "\033[1m"

class _NodeFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG":    "\033[90m",
        "INFO":     config.get_palette()["ansi_primary"],
        "WARNING":  "\033[93m",
        "ERROR":    "\033[91m",
        "CRITICAL": "\033[41m",
    }
    def format(self, record):
        lc = self.LEVEL_COLORS.get(record.levelname, "")
        return f"{lc}{super().format(record)}{_RESET}"

def _setup_logging():
    root = logging.getLogger("k7")
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt  = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
    nfmt = _NodeFormatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                           datefmt="%H:%M:%S")
    if config.LOG_TO_CONSOLE:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(nfmt)
        root.addHandler(ch)
    if config.LOG_TO_FILE:
        fh = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

_setup_logging()
logger = logging.getLogger("k7.core")


# =============================================================================
# ★  NodeRegistry — registro dinâmico de nós (mDNS + estáticos)
# =============================================================================

class NodeRegistry:
    """
    Fonte de verdade em runtime para os nós conhecidos.

    Combina:
      1. Nós estáticos de config.NETWORK_NODES (com IP preenchido → seeds)
      2. Nós descobertos via Zeroconf (adicionados/removidos dinamicamente)

    Thread-safe via lock.

    Estrutura de cada entry:
        {
            "node_type":  str,       # "seven" | "spark" | "mobile" | "unknown-<host>"
            "name":       str,
            "ip":         str,
            "port":       int,
            "mac":        str,
            "type":       str,       # "desktop" | "mobile"
            "specs":      str,
            "icon":       str,
            "source":     str,       # "static" | "mdns"
            "discovered": float,     # timestamp da descoberta/update
        }
    """

    def __init__(self):
        self._lock:  threading.Lock  = threading.Lock()
        self._nodes: dict[str, dict] = {}
        self._load_static()

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        """Retorna lista de todos os nós conhecidos (thread-safe)."""
        with self._lock:
            return list(self._nodes.values())

    def get(self, node_type: str) -> Optional[dict]:
        """Retorna um nó pelo tipo, ou None."""
        with self._lock:
            return self._nodes.get(node_type)

    def resolve_ip(self, node_type: str) -> Optional[str]:
        """
        Resolve o IP de um nó.
        Prioridade: registry em memória (mDNS) > config.NETWORK_NODES (estático).
        Retorna None se não encontrado.
        """
        entry = self.get(node_type)
        if entry and entry.get("ip"):
            return entry["ip"]
        # Fallback: config estático
        static = config.NETWORK_NODES.get(node_type, {})
        return static.get("ip") or None

    def upsert(self, node_type: str, data: dict):
        """Adiciona ou atualiza um nó no registry."""
        with self._lock:
            existing = self._nodes.get(node_type, {})
            merged   = {**existing, **data, "node_type": node_type}
            merged["discovered"] = time.time()
            self._nodes[node_type] = merged
            logger.info(f"[REGISTRY] Nó registrado: {node_type!r} @ {data.get('ip','?')}:{data.get('port','?')} [{data.get('source','?')}]")

    def remove(self, node_type: str):
        """Remove um nó do registry (ex: ficou offline)."""
        with self._lock:
            if node_type in self._nodes:
                del self._nodes[node_type]
                logger.info(f"[REGISTRY] Nó removido: {node_type!r}")

    def get_with_palette(self) -> list[dict]:
        """
        Retorna todos os nós fundidos com sua paleta de cores.
        Consumido pelo /api/nodes e pelo dashboard para renderizar cards.
        """
        result = []
        for entry in self.get_all():
            nt      = entry.get("node_type", "default")
            palette = config.get_palette(nt)
            merged  = dict(entry)
            for k, v in palette.items():
                if k.startswith("hex_") or k == "label":
                    merged[f"color_{k}"] = v
            result.append(merged)
        return result

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _load_static(self):
        """Carrega nós com IP preenchido em config.NETWORK_NODES como seeds."""
        for node_type, info in config.NETWORK_NODES.items():
            if info.get("ip"):
                self.upsert(node_type, {**info, "source": "static"})
            else:
                # Sem IP: cria entrada incompleta aguardando mDNS
                self.upsert(node_type, {
                    **info,
                    "ip":     "",
                    "source": "pending",
                })


# Registry global — único por processo
_registry = NodeRegistry()

def get_registry() -> NodeRegistry:
    """Retorna o NodeRegistry global."""
    return _registry


# =============================================================================
# ★  ZeroconfManager — anúncio e descoberta via mDNS
# =============================================================================

class ZeroconfManager:
    """
    Gerencia o ciclo de vida do Zeroconf:
      - Registra este nó na rede como serviço _k7core._tcp.local.
      - Escuta anúncios de outros nós e os adiciona ao NodeRegistry.
      - Ao encerrar, cancela o registro e para o browser.

    Protocolo de propriedades mDNS (TXT record):
        node_type  → "seven" | "spark" | "mobile"
        name       → nome amigável ("Seven", "Spark", ...)
        port       → porta HTTP (b"2026")
        mac        → MAC para WoL (opcional)
        node_mode  → "master" | "worker"
        api_secret → SHA-256 do API_SECRET para identificação sem revelar o segredo
    """

    def __init__(self, registry: NodeRegistry):
        self._zc:       Optional[Zeroconf]      = None
        self._browser:  Optional[ServiceBrowser] = None
        self._info:     Optional[ServiceInfo]    = None
        self._registry = registry
        self._running  = False
        # Fingerprint do secret para descoberta segura (não revela o segredo)
        import hashlib
        self._secret_fp = hashlib.sha256(
            config.API_SECRET.encode()
        ).hexdigest()[:16]

    def start(self) -> bool:
        """
        Inicia o Zeroconf: registra este nó e inicia o ServiceBrowser.
        Retorna True se OK, False se zeroconf não disponível.
        """
        if not _ZEROCONF_OK:
            logger.warning("[MDNS] zeroconf não instalado — descoberta automática desabilitada.")
            logger.warning("[MDNS] Instale com: pip install zeroconf")
            return False

        try:
            self._zc = Zeroconf()
            self._register_self()
            self._start_browser()
            self._running = True
            logger.info(f"[MDNS] Serviço registrado: {self._service_name()}")
            return True
        except Exception as exc:
            logger.error(f"[MDNS] Falha ao iniciar Zeroconf: {exc}", exc_info=True)
            return False

    def stop(self):
        """Encerra o Zeroconf gracefully."""
        if not self._running:
            return
        try:
            if self._info and self._zc:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
            logger.info("[MDNS] Zeroconf encerrado.")
        except Exception as exc:
            logger.error(f"[MDNS] Erro ao encerrar: {exc}")
        finally:
            self._running = False

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _service_name(self) -> str:
        """Nome único deste nó no formato mDNS: 'k7-seven._k7core._tcp.local.'"""
        base = config.DISCOVERY_NODE_NAME or f"k7-{config.NODE_TYPE}"
        return f"{base}.{config.DISCOVERY_SERVICE_TYPE}"

    def _get_local_ip(self) -> str:
        """Detecta o IP local que alcança a rede (sem enviar pacotes)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def _register_self(self):
        """Cria e registra o ServiceInfo deste nó."""
        local_ip = self._get_local_ip()
        props    = {
            "node_type":  config.NODE_TYPE,
            "name":       config.ASSISTANT_NAME,
            "port":       str(config.API_PORT),
            "mac":        config.NETWORK_NODES.get(config.NODE_TYPE, {}).get("mac", ""),
            "node_mode":  config.NODE_MODE,
            "secret_fp":  self._secret_fp,   # fingerprint para verificação
            "specs":      config.NETWORK_NODES.get(config.NODE_TYPE, {}).get("specs", ""),
        }
        self._info = ServiceInfo(
            type_     = config.DISCOVERY_SERVICE_TYPE,
            name      = self._service_name(),
            addresses = [socket.inet_aton(local_ip)],
            port      = config.API_PORT,
            properties= {k: v.encode() for k, v in props.items()},
            server    = f"{socket.gethostname()}.local.",
        )
        self._zc.register_service(self._info)
        logger.info(f"[MDNS] Anunciando como {local_ip}:{config.API_PORT} ({config.NODE_TYPE})")

    def _start_browser(self):
        """Inicia o ServiceBrowser que escuta outros nós k7-core."""
        self._browser = ServiceBrowser(
            self._zc,
            config.DISCOVERY_SERVICE_TYPE,
            handlers=[self._on_service_state_change],
        )

    def _on_service_state_change(
        self,
        zeroconf:     Zeroconf,
        service_type: str,
        name:         str,
        state_change: "ServiceStateChange",
    ):
        """
        Callback chamado pelo ServiceBrowser quando um nó aparece, atualiza ou some.
        Executa em thread separada do Zeroconf — precisa ser thread-safe.
        """
        if state_change == ServiceStateChange.Added or state_change == ServiceStateChange.Updated:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                self._on_node_discovered(name, info)
        elif state_change == ServiceStateChange.Removed:
            self._on_node_removed(name)

    def _on_node_discovered(self, name: str, info: ServiceInfo):
        """Processa um nó descoberto e o adiciona ao NodeRegistry."""
        try:
            # Decode das propriedades TXT
            props = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in info.properties.items()
            }

            # Valida fingerprint do secret — ignora nós de outras redes/projetos
            their_fp = props.get("secret_fp", "")
            if their_fp and their_fp != self._secret_fp:
                logger.warning(f"[MDNS] Nó ignorado (secret diferente): {name}")
                return

            node_type = props.get("node_type", "")
            # Gera um key legível mesmo para nós sem node_type
            if not node_type:
                node_type = f"unknown-{name.split('.')[0]}"

            # Ignora a si mesmo
            if node_type == config.NODE_TYPE:
                return

            ip = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""

            self._registry.upsert(node_type, {
                "name":      props.get("name", node_type.capitalize()),
                "ip":        ip,
                "port":      int(props.get("port", config.API_PORT)),
                "mac":       props.get("mac", ""),
                "type":      "mobile" if node_type == "mobile" else "desktop",
                "specs":     props.get("specs", ""),
                "node_mode": props.get("node_mode", "worker"),
                "icon":      _icon_for_node(node_type),
                "source":    "mdns",
            })

        except Exception as exc:
            logger.error(f"[MDNS] Erro ao processar descoberta '{name}': {exc}")

    def _on_node_removed(self, name: str):
        """Remove da memória um nó que saiu da rede."""
        # Extrai node_type do nome do serviço: "k7-seven._k7core._tcp.local." → "seven"
        try:
            base = name.split(".")[0]   # "k7-seven"
            if base.startswith("k7-"):
                node_type = base[3:]    # "seven"
                self._registry.remove(node_type)
        except Exception as exc:
            logger.error(f"[MDNS] Erro ao remover '{name}': {exc}")


def _icon_for_node(node_type: str) -> str:
    """Retorna ícone Material para um tipo de nó."""
    icons = {
        "seven":  "laptop",
        "spark":  "desktop_windows",
        "mobile": "smartphone",
    }
    return icons.get(node_type, "computer")


# =============================================================================
# ★  Autenticação — SQLite + werkzeug + Flask-Login
# =============================================================================

import sqlite3

def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _db_init():
    """Cria tabelas e usuário padrão se o banco não existir. Apenas no Master."""
    if config.is_worker():
        return
    with _db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role     TEXT NOT NULL DEFAULT 'master',
                created  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT NOT NULL,
                action    TEXT NOT NULL,
                detail    TEXT,
                ip        TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?,?)",
                (config.DEFAULT_USER, generate_password_hash(config.DEFAULT_PASSWORD))
            )
            conn.commit()
            logger.info(f"[AUTH] Usuário padrão criado: '{config.DEFAULT_USER}'")

def _audit(username: str, action: str, detail: str = "", ip: str = ""):
    if config.is_worker():
        return
    try:
        with _db_connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (username, action, detail, ip) VALUES (?,?,?,?)",
                (username, action, detail, ip)
            )
    except Exception as exc:
        logger.error(f"[AUTH] audit_log: {exc}")


class User(UserMixin if _FLASK_OK else object):
    def __init__(self, id_: int, username: str, role: str):
        self.id = id_; self.username = username; self.role = role

    @staticmethod
    def get(user_id: int) -> Optional["User"]:
        try:
            with _db_connect() as conn:
                row = conn.execute(
                    "SELECT id, username, role FROM users WHERE id=?", (user_id,)
                ).fetchone()
            return User(row["id"], row["username"], row["role"]) if row else None
        except Exception:
            return None

    @staticmethod
    def get_by_username(username: str):
        try:
            with _db_connect() as conn:
                return conn.execute(
                    "SELECT id, username, role, password FROM users WHERE username=?",
                    (username,)
                ).fetchone()
        except Exception:
            return None


# =============================================================================
# ★  TTS — síntese de voz
# =============================================================================

def _speak_espeak(text: str):
    import subprocess
    for bin_ in ("espeak-ng", "espeak"):
        try:
            subprocess.run(
                [bin_, "-v", config.ESPEAK_VOICE,
                 "-s", str(config.ESPEAK_SPEED),
                 "-a", str(config.ESPEAK_VOLUME), text],
                check=True, capture_output=True, timeout=30)
            return
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.error(f"[TTS] espeak: {exc}"); return

def _speak_termux(text: str):
    import subprocess
    try:
        subprocess.run(["termux-tts-speak", text], timeout=30, check=False)
    except Exception as exc:
        logger.error(f"[TTS] Termux: {exc}")

def _speak_gtts(text: str):
    try:
        from gtts import gTTS; import pygame
        lang = config.ASSISTANT_LANG.split("-")[0]
        tts  = gTTS(text=text, lang=lang, slow=False)
        tmp  = os.path.join(config.TEMP_DIR, "_tts.mp3")
        tts.save(tmp)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp); pygame.mixer.music.play()
        while pygame.mixer.music.get_busy(): time.sleep(0.05)
        pygame.mixer.quit()
    except Exception as exc:
        logger.error(f"[TTS] gTTS: {exc}"); _speak_espeak(text)

def speak(text: str):
    p = config.get_palette()["ansi_primary"]
    print(f"\n  {p}{_BOLD}🔊  {config.ASSISTANT_NAME}:{_RESET} {text}\n", flush=True)
    logger.info(f"[TTS] {text!r}")
    engine = config.VOICE_ENGINE.lower()
    try:
        if engine == "termux" or config.IS_ANDROID:  _speak_termux(text)
        elif engine == "gtts":                        _speak_gtts(text)
        else:                                         _speak_espeak(text)
    except Exception as exc:
        logger.error(f"[TTS] {exc}")


# =============================================================================
# ★  STT
# =============================================================================

def listen(recognizer, mic) -> Optional[str]:
    if not _STT_AVAILABLE: return None
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        try:
            audio = recognizer.listen(
                source,
                timeout=config.MIC_TIMEOUT,
                phrase_time_limit=config.MIC_PHRASE_TIME_LIMIT)
        except sr.WaitTimeoutError:
            return None
    try:
        text = recognizer.recognize_google(audio, language=config.ASSISTANT_LANG)
        logger.info(f"[STT] {text!r}"); return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        logger.error(f"[STT] {exc}"); return None


# =============================================================================
# ★  CommandLoader
# =============================================================================

class CommandLoader:
    def __init__(self, commands_dir: str):
        self._dir      = Path(commands_dir)
        self._registry: dict[str, Callable] = {}
        self._load_all()

    @property
    def registry(self) -> dict: return dict(self._registry)

    def reload(self):
        for key in [k for k in sys.modules if k.startswith("commands.")]:
            del sys.modules[key]
        self._registry.clear()
        self._load_all()
        logger.info(f"[LOADER] Reload: {len(self._registry)} gatilho(s).")

    def dispatch(self, text: str, speak_fn: Callable) -> bool:
        lower = text.lower().strip()
        for trigger in sorted(self._registry, key=len, reverse=True):
            if trigger in lower:
                logger.info(f"[DISPATCH] '{trigger}'")
                try:
                    self._registry[trigger](text, speak_fn)
                except Exception as exc:
                    logger.error(f"[DISPATCH] {exc}", exc_info=True)
                    speak_fn("Erro interno.")
                return True
        return False

    def _load_all(self):
        if not self._dir.is_dir():
            logger.error(f"[LOADER] {self._dir} não encontrado."); return
        total = 0
        for path in sorted(self._dir.glob("*.py")):
            if not path.name.startswith("_"):
                _, t = self._load_module(path); total += t
        logger.info(f"[LOADER] {total} gatilho(s).")

    def _load_module(self, path: Path) -> tuple:
        name = f"commands.{path.stem}"
        try:
            spec   = importlib.util.spec_from_file_location(name, str(path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.error(f"[LOADER] '{path.name}': {exc}", exc_info=True); return 0, 0
        commands = getattr(module, "COMMANDS", None)
        if not isinstance(commands, dict): return 0, 0
        count = 0
        for trigger, fn in commands.items():
            if callable(fn):
                self._registry[trigger.lower().strip()] = fn; count += 1
        desc = getattr(module, "DESCRIPTION", path.stem)
        logger.info(f"[LOADER]   ✓ {path.name} ({count} cmd) — {desc}")
        return 1, count


# =============================================================================
# ★  _cmd_handler — lógica compartilhada Master e Worker para /cmd
# =============================================================================

def _handle_cmd_request(data: dict, loader: CommandLoader, registry: NodeRegistry) -> tuple:
    """
    Processa o body de um POST /cmd.
    Retorna (response_dict, http_status_code).

    Segurança:
        - Valida config.API_SECRET obrigatoriamente para todas as chamadas
          máquina-a-máquina (Worker não tem sessão Flask).
        - Operações privilegiadas (run, shutdown) exigem ADMIN_SECRET.
    """
    import engine as eng

    cmd    = data.get("command", "").lower().strip()
    text   = data.get("text",    "")
    origin = data.get("origin",  "unknown")

    logger.info(f"[/cmd] ← {origin} | cmd={cmd!r}")

    if cmd == "speak":
        if not text: return {"error": "Campo 'text' obrigatório."}, 400
        speak(text)
        return {"ok": True, "action": "speak"}, 200

    if cmd == "vibrate":
        if config.IS_ANDROID:
            eng.termux_vibrate(int(data.get("duration", 500)))
        return {"ok": config.IS_ANDROID, "action": "vibrate"}, 200

    if cmd == "notify":
        title = data.get("title", config.ASSISTANT_NAME)
        content = text or data.get("content", "")
        if config.IS_ANDROID:
            eng.termux_notify(title, content)
        else:
            print(f"\n  🔔 [{title}] {content}\n")
        return {"ok": True, "action": "notify"}, 200

    if cmd == "torch":
        state = data.get("state", "on") == "on"
        if config.IS_ANDROID:
            eng.termux_torch(state)
        return {"ok": config.IS_ANDROID, "action": "torch"}, 200

    if cmd == "run":
        # Operação privilegiada — exige ADMIN_SECRET
        if data.get("admin_secret") != config.ADMIN_SECRET:
            logger.warning(f"[/cmd] run rejeitado — admin_secret inválido. Origem: {origin}")
            return {"error": "Admin secret inválido para operação 'run'."}, 403
        shell_cmd = data.get("shell", "")
        if not shell_cmd: return {"error": "Campo 'shell' obrigatório."}, 400
        result = eng.run_local(shell_cmd, timeout=15)
        return {"ok": result.success, "stdout": result.stdout,
                "stderr": result.stderr, "returncode": result.returncode}, 200

    if cmd == "status":
        return {"ok": True, "system": eng.get_system_info()}, 200

    if cmd == "reload":
        loader.reload()
        return {"ok": True, "commands": len(loader.registry)}, 200

    # Tenta despachar como gatilho de módulo
    if loader.dispatch(text or cmd, speak):
        return {"ok": True, "action": "dispatch"}, 200

    return {"error": f"Comando desconhecido: {cmd!r}"}, 404


# =============================================================================
# ★  _build_worker_app — Flask headless (Worker mode)
#    Rotas: GET /health, POST /cmd
#    SEM templates, SEM auth DB, SEM /dashboard
# =============================================================================

def _build_worker_app(loader: CommandLoader, registry: NodeRegistry) -> "Flask":
    """
    Constrói Flask mínimo para modo Worker.
    Não carrega templates, Flask-Login nem Auth DB.
    """
    app = Flask(f"k7-worker-{config.NODE_TYPE}")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/health", methods=["GET"])
    def health():
        import engine as eng
        return jsonify({
            "status":   "ok",
            "node":     config.NODE_TYPE,
            "name":     config.ASSISTANT_NAME,
            "mode":     "worker",
            "port":     config.API_PORT,
            "android":  config.IS_ANDROID,
            "commands": len(loader.registry),
            "system":   eng.get_system_info(),
        })

    @app.route("/cmd", methods=["POST"])
    def worker_cmd():
        data = request.get_json(silent=True) or {}
        # Worker sempre exige API_SECRET — sem sessão web
        if data.get("secret") != config.API_SECRET:
            logger.warning(f"[WORKER /cmd] Secret inválido de {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        resp, code = _handle_cmd_request(data, loader, registry)
        return jsonify(resp), code

    return app


# =============================================================================
# ★  _build_master_app — Flask completo (Master mode)
#    Rotas: tudo acima + /login, /dashboard, /api/nodes, /api/wake, /api/terminal, ...
# =============================================================================

def _build_master_app(loader: CommandLoader, registry: NodeRegistry) -> "Flask":
    """
    Constrói Flask completo para modo Master.
    Inclui dashboard, auth, todas as rotas /api/*.
    """
    import engine as eng
    import concurrent.futures

    app = Flask(
        f"k7-master-{config.NODE_TYPE}",
        template_folder=config.TEMPLATES_DIR,
    )
    app.secret_key = config.FLASK_SECRET_KEY
    app.permanent_session_lifetime = timedelta(seconds=config.SESSION_LIFETIME)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view        = "login_page"
    login_manager.login_message     = "Acesso restrito."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id): return User.get(int(user_id))

    # ── Auth routes ──────────────────────────────────────────────────────────

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            row = User.get_by_username(username)
            if row and check_password_hash(row["password"], password):
                u = User(row["id"], row["username"], row["role"])
                login_user(u, remember=True)
                session.permanent = True
                _audit(username, "login", ip=request.remote_addr)
                logger.info(f"[AUTH] Login: '{username}' de {request.remote_addr}")
                return redirect(url_for("dashboard"))
            _audit(username or "?", "login_failed", ip=request.remote_addr)
            flash("Credenciais inválidas.", "error")
        return render_template("login.html",
                               node_type=config.NODE_TYPE,
                               palette=config.get_palette())

    @app.route("/logout")
    @login_required
    def logout_page():
        _audit(current_user.username, "logout", ip=request.remote_addr)
        logout_user()
        return redirect(url_for("login_page"))

    @app.route("/change-password", methods=["POST"])
    @login_required
    def change_password():
        current_pw = request.form.get("current_password", "")
        new_pw     = request.form.get("new_password", "")
        row = User.get_by_username(current_user.username)
        if not row or not check_password_hash(row["password"], current_pw):
            flash("Senha atual incorreta.", "error")
            return redirect(url_for("dashboard"))
        if len(new_pw) < 6:
            flash("Mínimo 6 caracteres.", "error")
            return redirect(url_for("dashboard"))
        with _db_connect() as conn:
            conn.execute("UPDATE users SET password=? WHERE username=?",
                         (generate_password_hash(new_pw), current_user.username))
        _audit(current_user.username, "password_changed")
        flash("Senha alterada.", "success")
        return redirect(url_for("dashboard"))

    # ── Dashboard ────────────────────────────────────────────────────────────

    @app.route("/")
    @login_required
    def index(): return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        # Passa lista inicial de nós ao template (estáticos + já descobertos)
        nodes_data = registry.get_with_palette()
        return render_template(
            "dashboard.html",
            node_type      = config.NODE_TYPE,
            assistant_name = config.ASSISTANT_NAME,
            current_node   = config.NODE_TYPE,
            nodes          = nodes_data,
            palette        = config.get_palette(),
            username       = current_user.username,
        )

    # ── /api/config — fonte única de verdade para o frontend ────────────────

    @app.route("/api/config")
    @login_required
    def api_config():
        return jsonify({
            "network_nodes": {
                nt: {k: v for k, v in info.items()}
                for nt, info in config.NETWORK_NODES.items()
            },
            "node_palettes": {
                k: {pk: pv for pk, pv in pv.items()
                    if pk.startswith("hex_") or pk == "label"}
                for k, pv in config.NODE_PALETTES.items()
            },
            "current_node":  config.NODE_TYPE,
            "api_port":      config.API_PORT,
            "mdns_available":_ZEROCONF_OK,
        })

    # ── /api/nodes — status de todos os nós (polling do dashboard) ──────────

    @app.route("/api/nodes")
    @login_required
    def api_nodes():
        """
        Retorna status atualizado de cada nó no registry.
        O registry já contém nós estáticos + mDNS.
        O health check é feito em paralelo.
        """
        def _check(entry: dict) -> dict:
            node_type = entry["node_type"]
            ip        = entry.get("ip", "")
            port      = entry.get("port", config.API_PORT)

            if not ip:
                return {**entry, "online": False, "reachable": False}

            online = eng.is_host_reachable(ip, port=port, timeout=2)
            result = {**entry, "online": online}

            if online and _REQUESTS_OK:
                try:
                    r = _req.get(f"http://{ip}:{port}/health", timeout=3)
                    if r.status_code == 200:
                        data     = r.json()
                        sys_info = data.get("system", {})
                        result.update({
                            "uptime":    sys_info.get("uptime",    "N/A"),
                            "cpu":       sys_info.get("cpu_percent","N/A"),
                            "mem_used":  sys_info.get("mem_used",  ""),
                            "mem_total": sys_info.get("mem_total", ""),
                            "battery":   sys_info.get("battery",   ""),
                            "commands":  data.get("commands", 0),
                            "node_mode": data.get("mode", "worker"),
                        })
                except Exception:
                    pass

            return result

        all_nodes = registry.get_with_palette()
        nodes_status = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_check, e): e["node_type"] for e in all_nodes}
            for future in concurrent.futures.as_completed(futures):
                nt = futures[future]
                try:
                    r = future.result()
                    nodes_status[nt] = r
                except Exception as exc:
                    nodes_status[nt] = {"node_type": nt, "online": False, "error": str(exc)}

        return jsonify({"nodes": nodes_status, "timestamp": time.time(),
                        "mdns_active": _ZEROCONF_OK})

    # ── /api/wake ────────────────────────────────────────────────────────────

    @app.route("/api/wake", methods=["POST"])
    @login_required
    def api_wake():
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", "")
        entry     = registry.get(node_type)
        mac = ""
        if entry:
            mac = entry.get("mac", "")
        if not mac:
            static = config.NETWORK_NODES.get(node_type, {})
            mac    = static.get("mac", "")
        if not mac:
            return jsonify({"ok": False, "error": "MAC não disponível para WoL."}), 400
        ok = eng.send_magic_packet(mac)
        _audit(current_user.username, "wake", detail=node_type, ip=request.remote_addr)
        return jsonify({"ok": ok, "node": node_type, "mac": mac})

    # ── /api/shutdown ────────────────────────────────────────────────────────

    @app.route("/api/shutdown", methods=["POST"])
    @login_required
    def api_shutdown():
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", "")
        if node_type == config.NODE_TYPE:
            result = eng.run_local("sudo shutdown -h now")
        else:
            entry = registry.get(node_type)
            if not entry or not entry.get("ip"):
                return jsonify({"ok": False, "error": f"IP de {node_type} desconhecido."}), 404
            result = _send_to_node(node_type, entry, "run",
                                   {"shell": "sudo shutdown -h now",
                                    "admin_secret": config.ADMIN_SECRET})
        _audit(current_user.username, "shutdown", detail=node_type, ip=request.remote_addr)
        return jsonify({"ok": result.success if hasattr(result, 'success') else True,
                        "node": node_type})

    # ── /api/speak ───────────────────────────────────────────────────────────

    @app.route("/api/speak", methods=["POST"])
    @login_required
    def api_speak():
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", config.NODE_TYPE)
        text      = data.get("text", "").strip()
        if not text:
            return jsonify({"ok": False, "error": "Campo 'text' obrigatório."}), 400
        if node_type == config.NODE_TYPE:
            speak(text); ok = True
        else:
            entry = registry.get(node_type)
            if not entry or not entry.get("ip"):
                return jsonify({"ok": False, "error": f"IP de {node_type} desconhecido."}), 404
            result = _send_to_node(node_type, entry, "speak", {"text": text})
            ok = result.success
        _audit(current_user.username, "speak", detail=f"{node_type}: {text[:50]}")
        return jsonify({"ok": ok, "node": node_type})

    # ── /api/terminal ────────────────────────────────────────────────────────

    @app.route("/api/terminal", methods=["POST"])
    @login_required
    def api_terminal():
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", config.NODE_TYPE)
        cmd       = data.get("cmd", "").strip()
        if not cmd:
            return jsonify({"ok": False, "error": "Comando vazio."}), 400
        _audit(current_user.username, "terminal",
               detail=f"{node_type}: {cmd[:80]}", ip=request.remote_addr)
        if node_type == config.NODE_TYPE:
            result = eng.run_local(cmd, timeout=15)
        else:
            entry = registry.get(node_type)
            if not entry or not entry.get("ip"):
                return jsonify({"ok": False, "error": f"IP de {node_type} desconhecido."}), 404
            result = _send_to_node(node_type, entry, "run",
                                   {"shell": cmd, "admin_secret": config.ADMIN_SECRET})
        return jsonify({
            "ok":         result.success,
            "node":       node_type,
            "cmd":        cmd,
            "stdout":     result.stdout[:4000],
            "stderr":     result.stderr[:500],
            "returncode": result.returncode,
        })

    # ── /api/reload ──────────────────────────────────────────────────────────

    @app.route("/api/reload", methods=["POST"])
    @login_required
    def api_reload():
        loader.reload()
        return jsonify({"ok": True, "commands": len(loader.registry)})

    # ── /health (público — usado pelo browser mDNS de outros Masters) ────────

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status":   "ok",
            "node":     config.NODE_TYPE,
            "name":     config.ASSISTANT_NAME,
            "mode":     "master",
            "port":     config.API_PORT,
            "android":  config.IS_ANDROID,
            "commands": len(loader.registry),
            "system":   eng.get_system_info(),
        })

    # ── /cmd (aceita secret OU sessão autenticada) ───────────────────────────

    @app.route("/cmd", methods=["POST"])
    def master_cmd():
        data = request.get_json(silent=True) or {}
        authed_secret  = data.get("secret") == config.API_SECRET
        authed_session = _FLASK_OK and current_user.is_authenticated
        if not authed_secret and not authed_session:
            logger.warning(f"[MASTER /cmd] Acesso negado de {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        resp, code = _handle_cmd_request(data, loader, registry)
        return jsonify(resp), code

    return app


def _send_to_node(node_type: str, entry: dict, command: str,
                  extra: Optional[dict] = None) -> "CommandResult":
    """
    Envia comando para um nó usando IP e porta do NodeRegistry.
    Usa sempre o ADMIN_SECRET no body quando necessário.
    """
    if not _REQUESTS_OK:
        from engine import CommandResult
        return CommandResult(success=False, returncode=-1,
                             error_msg="requests não instalado.")
    import engine as eng

    ip   = entry["ip"]
    port = entry.get("port", config.API_PORT)
    url  = f"http://{ip}:{port}/cmd"
    body = {
        "command": command,
        "origin":  config.NODE_TYPE,
        "secret":  config.API_SECRET,
        **(extra or {}),
    }
    try:
        r = _req.post(url, json=body, timeout=8)
        r.raise_for_status()
        return eng.CommandResult(
            stdout=json.dumps(r.json(), ensure_ascii=False),
            returncode=0, success=True)
    except Exception as exc:
        return eng.CommandResult(success=False, returncode=-1, error_msg=str(exc))


# =============================================================================
# ★  Flask server thread
# =============================================================================

def _run_flask_server(loader: CommandLoader, registry: NodeRegistry):
    if not _FLASK_OK:
        logger.error("[FLASK] Não disponível — instale flask flask-login.")
        return

    if config.is_master():
        _db_init()
        app = _build_master_app(loader, registry)
        mode_label = "MASTER  (dashboard + auth)"
    else:
        app = _build_worker_app(loader, registry)
        mode_label = "WORKER  (headless)"

    logger.info(f"[FLASK] Iniciando em {config.API_HOST}:{config.API_PORT} [{mode_label}]")
    if config.is_master():
        logger.info(f"[FLASK] Dashboard → http://localhost:{config.API_PORT}/dashboard")

    app.run(host=config.API_HOST, port=config.API_PORT,
            debug=False, use_reloader=False, threaded=True)


# =============================================================================
# ★  Assistant — loop principal
# =============================================================================

class Assistant:
    _EXIT_WORDS     = {"encerrar", "desligar", "tchau", "adeus", "sair", "fechar"}
    _RELOAD_TRIGGER = "recarregar módulos"

    def __init__(self):
        self.name     = config.ASSISTANT_NAME
        self.node     = config.NODE_TYPE
        self.loader   = CommandLoader(config.COMMANDS_DIR)
        self.registry = _registry      # NodeRegistry global
        self._mdns    = ZeroconfManager(self.registry)
        self._running = False
        self._rec = self._mic = None
        if _STT_AVAILABLE and not config.IS_ANDROID:
            self._rec = sr.Recognizer()
            self._rec.energy_threshold         = config.MIC_ENERGY_THRESHOLD
            self._rec.pause_threshold          = config.MIC_PAUSE_THRESHOLD
            self._rec.dynamic_energy_threshold = True
            self._mic = sr.Microphone()

        mode = "MASTER" if config.is_master() else "WORKER"
        logger.info(
            f"[CORE] Nó='{self.node}' | Nome='{self.name}' | "
            f"Mode={mode} | Port={config.API_PORT} | Android={config.IS_ANDROID}"
        )

    def run(self):
        # 1. Registra serviço mDNS e inicia browser de descoberta
        mdns_ok = self._mdns.start()
        if mdns_ok:
            logger.info(f"[CORE] Aguardando descoberta mDNS ({config.DISCOVERY_BOOT_WAIT}s)...")
            time.sleep(config.DISCOVERY_BOOT_WAIT)

        # 2. Inicia Flask em thread daemon
        t = threading.Thread(
            target=_run_flask_server,
            args=(self.loader, self.registry),
            name="k7-flask",
            daemon=True,
        )
        t.start()
        time.sleep(0.8)   # deixa Flask subir

        # 3. Loop de interação
        try:
            if config.IS_ANDROID:
                self._android_mode()
            elif _STT_AVAILABLE:
                self._voice_loop()
            else:
                self._text_loop()
        finally:
            self._mdns.stop()

    def _voice_loop(self):
        self._running = True
        self._greet()
        p   = config.get_palette()["ansi_primary"]
        bar = "─" * 56
        print(f"\n  {p}{bar}{_RESET}")
        print(f"  {p}{_BOLD}  {self.name} [{self.node.upper()} / {'MASTER' if config.is_master() else 'WORKER'}]{_RESET}")
        print(f"  {p}  Porta {config.API_PORT}  |  mDNS: {'✓' if _ZEROCONF_OK else '✗'}{_RESET}")
        if config.is_master():
            print(f"  {p}  Dashboard → http://localhost:{config.API_PORT}/dashboard{_RESET}")
        print(f"  {p}{bar}{_RESET}\n")

        while self._running:
            try:
                raw = listen(self._rec, self._mic)
                if raw:
                    print(f"  👤 {raw}", flush=True)
                    self._process(raw)
            except KeyboardInterrupt:
                speak("Até logo!"); self._running = False
            except Exception as exc:
                logger.critical(f"[CORE] {exc}", exc_info=True); time.sleep(1)

    def _text_loop(self):
        self._running = True
        self._greet()
        print(f"\n  [{self.node.upper()}] Modo texto (Ctrl+C para sair)\n")
        while self._running:
            try:
                raw = input("  > ").strip()
                if raw: self._process(raw)
            except (KeyboardInterrupt, EOFError):
                speak("Até logo!"); self._running = False

    def _android_mode(self):
        self._running = True
        speak(f"{self.name} Worker online. Porta {config.API_PORT}.")
        print(f"\n  [MOBILE/WORKER] Aguardando comandos na porta {config.API_PORT}\n")
        try:
            while self._running: time.sleep(1)
        except KeyboardInterrupt:
            self._running = False

    def _process(self, raw: str):
        if not raw.lower().strip().startswith(self.name.lower()): return
        cmd = raw.strip()[len(self.name):].lstrip(" ,.:;").strip()
        if not cmd:
            speak("Sim, estou aqui."); return
        if self._handle_internal(cmd): return
        if not self.loader.dispatch(cmd, speak):
            speak(f"Não reconheci '{cmd}'. Diga '{self.name}, ajuda'.")

    def _greet(self):
        mode = "Master" if config.is_master() else "Worker"
        speak(f"Olá! Sou {self.name}, nó {mode} na porta {config.API_PORT}.")

    def _handle_internal(self, command: str) -> bool:
        lower = command.lower()
        if self._RELOAD_TRIGGER in lower:
            speak("Recarregando módulos.")
            self.loader.reload()
            speak(f"{len(self.loader.registry)} comandos ativos.")
            return True
        for word in self._EXIT_WORDS:
            if word in lower:
                speak("Até logo!"); self._running = False; return True
        return False


# =============================================================================
# Ponto de entrada
# =============================================================================

def main():
    assistant = Assistant()
    assistant.run()

if __name__ == "__main__":
    main()
