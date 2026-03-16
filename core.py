# =============================================================================
# k7-core | core.py  — v4 (Dashboard + Auth)
#
# Novidades em relação à v3:
#   - SQLite + werkzeug.security para autenticação do Mestre
#   - Flask-Login gerenciando sessões (@login_required)
#   - Rota GET  /dashboard  → painel de controle HTML
#   - Rota GET  /api/nodes  → JSON com status de todos os nós (polling)
#   - Rota POST /api/wake   → dispara WoL via engine.wake_pc()
#   - Rota POST /api/shutdown → envia shutdown para nó via API
#   - Rota POST /cmd        → executa comando (protegida por login OU secret)
#   - Todas as rotas web protegidas por @login_required
# =============================================================================

from __future__ import annotations

import importlib.util
import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Callable, Optional

import config

# ---------------------------------------------------------------------------
# Imports condicionais
# ---------------------------------------------------------------------------

_STT_AVAILABLE = False
_MIC_AVAILABLE = False

if not config.IS_ANDROID:
    try:
        import speech_recognition as sr
        _STT_AVAILABLE = True
        _MIC_AVAILABLE = True
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
except ImportError as _fe:
    _FLASK_OK = False
    print(f"[WARN] Flask/Flask-Login não disponível: {_fe}")

try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ---------------------------------------------------------------------------
# Logging
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
        lc  = self.LEVEL_COLORS.get(record.levelname, "")
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
# ★  AUTENTICAÇÃO — SQLite + werkzeug + Flask-Login
# =============================================================================

def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _db_init():
    """Cria tabelas e usuário padrão se o banco ainda não existir."""
    with _db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT    UNIQUE NOT NULL,
                password TEXT    NOT NULL,
                role     TEXT    NOT NULL DEFAULT 'master',
                created  TEXT    NOT NULL DEFAULT (datetime('now'))
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
        # Cria usuário padrão se não existir nenhum
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            pw_hash = generate_password_hash(config.DEFAULT_PASSWORD)
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (config.DEFAULT_USER, pw_hash)
            )
            conn.commit()
            logger.info(f"[AUTH] Usuário padrão criado: '{config.DEFAULT_USER}'")

def _audit(username: str, action: str, detail: str = "", ip: str = ""):
    """Registra ação no audit_log."""
    try:
        with _db_connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (username, action, detail, ip) VALUES (?,?,?,?)",
                (username, action, detail, ip)
            )
    except Exception as exc:
        logger.error(f"[AUTH] audit_log falhou: {exc}")


class User(UserMixin if _FLASK_OK else object):
    """Modelo de usuário para Flask-Login."""
    def __init__(self, id_: int, username: str, role: str):
        self.id       = id_
        self.username = username
        self.role     = role

    @staticmethod
    def get(user_id: int) -> Optional["User"]:
        try:
            with _db_connect() as conn:
                row = conn.execute(
                    "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            return User(row["id"], row["username"], row["role"]) if row else None
        except Exception:
            return None

    @staticmethod
    def get_by_username(username: str) -> Optional["User"]:
        try:
            with _db_connect() as conn:
                row = conn.execute(
                    "SELECT id, username, role, password FROM users WHERE username = ?",
                    (username,)
                ).fetchone()
            return row
        except Exception:
            return None


# =============================================================================
# ★  TTS — síntese de voz
# =============================================================================

def _speak_espeak(text: str):
    import subprocess
    for bin_ in ("espeak-ng", "espeak"):
        try:
            subprocess.run([bin_, "-v", config.ESPEAK_VOICE,
                            "-s", str(config.ESPEAK_SPEED),
                            "-a", str(config.ESPEAK_VOLUME), text],
                           check=True, capture_output=True, timeout=30)
            return
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.error(f"[TTS] {exc}")
            return

def _speak_termux(text: str):
    import subprocess
    try:
        subprocess.run(["termux-tts-speak", text], timeout=30, check=False)
    except Exception as exc:
        logger.error(f"[TTS] Termux: {exc}")

def _speak_gtts(text: str):
    try:
        from gtts import gTTS
        import pygame
        lang = config.ASSISTANT_LANG.split("-")[0]
        tts  = gTTS(text=text, lang=lang, slow=False)
        tmp  = os.path.join(config.TEMP_DIR, "_tts.mp3")
        tts.save(tmp)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.quit()
    except Exception as exc:
        logger.error(f"[TTS] gTTS: {exc}")
        _speak_espeak(text)

def speak(text: str):
    palette = config.get_palette()
    p = palette["ansi_primary"]
    print(f"\n  {p}{_BOLD}🔊  {config.ASSISTANT_NAME}:{_RESET} {text}\n", flush=True)
    logger.info(f"[TTS] {text!r}")
    engine = config.VOICE_ENGINE.lower()
    try:
        if engine == "termux" or config.IS_ANDROID:
            _speak_termux(text)
        elif engine == "gtts":
            _speak_gtts(text)
        else:
            _speak_espeak(text)
    except Exception as exc:
        logger.error(f"[TTS] Falha: {exc}")


# =============================================================================
# ★  STT — reconhecimento de voz
# =============================================================================

def listen(recognizer, mic) -> Optional[str]:
    if not _STT_AVAILABLE:
        return None
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        try:
            audio = recognizer.listen(source,
                                      timeout=config.MIC_TIMEOUT,
                                      phrase_time_limit=config.MIC_PHRASE_TIME_LIMIT)
        except sr.WaitTimeoutError:
            return None
    try:
        text = recognizer.recognize_google(audio, language=config.ASSISTANT_LANG)
        logger.info(f"[STT] {text!r}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        logger.error(f"[STT] {exc}")
        return None


# =============================================================================
# ★  CommandLoader
# =============================================================================

class CommandLoader:
    def __init__(self, commands_dir: str):
        self._dir      = Path(commands_dir)
        self._registry: dict[str, Callable] = {}
        self._load_all()

    @property
    def registry(self) -> dict:
        return dict(self._registry)

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
                    speak_fn("Erro interno ao executar o comando.")
                return True
        return False

    def _load_all(self):
        if not self._dir.is_dir():
            logger.error(f"[LOADER] Diretório não encontrado: {self._dir}")
            return
        total = 0
        for path in sorted(self._dir.glob("*.py")):
            if not path.name.startswith("_"):
                _, t = self._load_module(path)
                total += t
        logger.info(f"[LOADER] {total} gatilho(s) carregado(s).")

    def _load_module(self, path: Path) -> tuple:
        name = f"commands.{path.stem}"
        try:
            spec   = importlib.util.spec_from_file_location(name, str(path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.error(f"[LOADER] '{path.name}': {exc}", exc_info=True)
            return 0, 0
        commands = getattr(module, "COMMANDS", None)
        if not isinstance(commands, dict):
            return 0, 0
        count = sum(1 for fn in commands.values() if callable(fn))
        for trigger, fn in commands.items():
            if callable(fn):
                self._registry[trigger.lower().strip()] = fn
        desc = getattr(module, "DESCRIPTION", path.stem)
        logger.info(f"[LOADER]   ✓ {path.name} ({count} cmd) — {desc}")
        return 1, count


# =============================================================================
# ★  Flask App — API + Dashboard
# =============================================================================

def _build_app(loader: CommandLoader) -> "Flask":
    """
    Constrói e retorna a aplicação Flask completa.

    Rotas públicas:
        GET  /login        → formulário de login
        POST /login        → autentica e redireciona
        GET  /logout       → encerra sessão

    Rotas protegidas (@login_required):
        GET  /             → redireciona para /dashboard
        GET  /dashboard    → painel de controle HTML
        GET  /api/nodes    → JSON com status de todos os nós
        GET  /api/config   → JSON com NETWORK_NODES + NODE_PALETTES
        POST /api/wake     → dispara Wake-on-LAN { "node": "spark" }
        POST /api/shutdown → envia shutdown para nó { "node": "seven" }
        POST /api/speak    → faz nó falar { "node": "spark", "text": "..." }
        POST /api/terminal → executa cmd no nó { "node": "seven", "cmd": "..." }
        POST /cmd          → executa comando (aceita secret OU sessão autenticada)
    """
    import engine as eng

    app = Flask(
        f"k7-{config.NODE_TYPE}",
        template_folder=config.TEMPLATES_DIR,
    )
    app.secret_key = config.FLASK_SECRET_KEY
    app.permanent_session_lifetime = timedelta(seconds=config.SESSION_LIFETIME)

    # Silencia logs de acesso do Werkzeug
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # --- Flask-Login setup ---
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login_page"
    login_manager.login_message = "Acesso restrito. Faça login."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(int(user_id))

    # =========================================================================
    # Rotas de autenticação
    # =========================================================================

    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            row = User.get_by_username(username)
            if row and check_password_hash(row["password"], password):
                user = User(row["id"], row["username"], row["role"])
                login_user(user, remember=True)
                session.permanent = True
                _audit(username, "login", ip=request.remote_addr)
                logger.info(f"[AUTH] Login: '{username}' de {request.remote_addr}")
                return redirect(url_for("dashboard"))
            else:
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
            flash("Nova senha deve ter no mínimo 6 caracteres.", "error")
            return redirect(url_for("dashboard"))
        new_hash = generate_password_hash(new_pw)
        with _db_connect() as conn:
            conn.execute("UPDATE users SET password=? WHERE username=?",
                         (new_hash, current_user.username))
        _audit(current_user.username, "password_changed", ip=request.remote_addr)
        flash("Senha alterada com sucesso.", "success")
        return redirect(url_for("dashboard"))

    # =========================================================================
    # Dashboard
    # =========================================================================

    @app.route("/")
    @login_required
    def index():
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        nodes_with_palette = config.get_nodes_with_palette()
        return render_template(
            "dashboard.html",
            node_type      = config.NODE_TYPE,
            assistant_name = config.ASSISTANT_NAME,
            current_node   = config.NODE_TYPE,
            nodes          = nodes_with_palette,
            palette        = config.get_palette(),
            username       = current_user.username,
        )

    # =========================================================================
    # API — dados para o frontend (polling AJAX)
    # =========================================================================

    @app.route("/api/config")
    @login_required
    def api_config():
        """Retorna a configuração de nós e paletas (fonte única de verdade)."""
        return jsonify({
            "network_nodes":  config.NETWORK_NODES,
            "node_palettes":  {
                k: {pk: pv for pk, pv in pv.items() if pk.startswith("hex_") or pk == "label"}
                for k, pv in config.NODE_PALETTES.items()
            },
            "current_node":   config.NODE_TYPE,
        })

    @app.route("/api/nodes")
    @login_required
    def api_nodes():
        """
        Verifica o status de cada nó da rede em paralelo e retorna JSON.
        Chamado pelo dashboard a cada 10 segundos via fetch().
        """
        import concurrent.futures

        def _check_node(node_type: str, info: dict) -> dict:
            ip   = info["ip"]
            port = info["port"]
            online = eng.is_host_reachable(ip, port=port, timeout=2)
            result = {
                "node_type": node_type,
                "name":      info["name"],
                "online":    online,
                "ip":        ip,
                "type":      info.get("type", "desktop"),
                "specs":     info.get("specs", ""),
                "has_wol":   bool(info.get("mac")),
            }
            # Se online, tenta buscar status detalhado via API do nó
            if online and _REQUESTS_OK:
                try:
                    r = _requests.get(
                        f"http://{ip}:{port}/health",
                        timeout=3
                    )
                    if r.status_code == 200:
                        data = r.json()
                        sys_info = data.get("system", {})
                        result["uptime"]   = sys_info.get("uptime", "N/A")
                        result["cpu"]      = sys_info.get("cpu_percent", "N/A")
                        result["mem_used"] = sys_info.get("mem_used", "")
                        result["mem_total"]= sys_info.get("mem_total", "")
                        result["battery"]  = sys_info.get("battery", "")
                        result["commands"] = data.get("commands", 0)
                except Exception:
                    pass
            return result

        nodes_status = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_check_node, nt, info): nt
                       for nt, info in config.NETWORK_NODES.items()}
            for future in concurrent.futures.as_completed(futures):
                try:
                    r = future.result()
                    nodes_status[r["node_type"]] = r
                except Exception as exc:
                    nt = futures[future]
                    nodes_status[nt] = {"node_type": nt, "online": False, "error": str(exc)}

        return jsonify({"nodes": nodes_status, "timestamp": time.time()})

    # =========================================================================
    # Ações de controle dos nós
    # =========================================================================

    @app.route("/api/wake", methods=["POST"])
    @login_required
    def api_wake():
        """Dispara Wake-on-LAN para o nó especificado."""
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", "")
        node_info = config.NETWORK_NODES.get(node_type)

        if not node_info:
            return jsonify({"ok": False, "error": f"Nó '{node_type}' não encontrado."}), 404

        mac = node_info.get("mac", "")
        if not mac:
            return jsonify({"ok": False, "error": "Este nó não possui MAC configurado para WoL."}), 400

        ok = eng.send_magic_packet(mac)
        _audit(current_user.username, "wake", detail=node_type, ip=request.remote_addr)
        logger.info(f"[DASHBOARD] WoL → {node_type} ({mac}) | ok={ok}")
        return jsonify({"ok": ok, "node": node_type, "mac": mac})

    @app.route("/api/shutdown", methods=["POST"])
    @login_required
    def api_shutdown():
        """Envia comando de shutdown para o nó via API."""
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", "")
        node_info = config.NETWORK_NODES.get(node_type)
        if not node_info:
            return jsonify({"ok": False, "error": "Nó não encontrado."}), 404

        # Envia via API do nó
        if node_type == config.NODE_TYPE:
            # Self-shutdown
            result = eng.run_local("sudo shutdown -h now")
        else:
            result = eng.send_node_command(node_type, "run", {"shell": "sudo shutdown -h now"})

        _audit(current_user.username, "shutdown", detail=node_type, ip=request.remote_addr)
        logger.warning(f"[DASHBOARD] Shutdown → {node_type}")
        return jsonify({"ok": result.success, "node": node_type})

    @app.route("/api/speak", methods=["POST"])
    @login_required
    def api_speak():
        """Faz um nó específico falar via TTS."""
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", config.NODE_TYPE)
        text      = data.get("text", "").strip()
        if not text:
            return jsonify({"ok": False, "error": "Campo 'text' obrigatório."}), 400

        if node_type == config.NODE_TYPE:
            speak(text)
            result_ok = True
        else:
            result = eng.send_node_command(node_type, "speak", {"text": text})
            result_ok = result.success

        _audit(current_user.username, "speak", detail=f"{node_type}: {text[:60]}")
        return jsonify({"ok": result_ok, "node": node_type, "text": text})

    @app.route("/api/terminal", methods=["POST"])
    @login_required
    def api_terminal():
        """
        Executa um comando shell no nó especificado e retorna o output.
        Principal feature do Terminal embutido no dashboard.
        """
        data      = request.get_json(silent=True) or {}
        node_type = data.get("node", config.NODE_TYPE)
        cmd       = data.get("cmd", "").strip()

        if not cmd:
            return jsonify({"ok": False, "error": "Comando vazio."}), 400

        _audit(current_user.username, "terminal", detail=f"{node_type}: {cmd[:80]}",
               ip=request.remote_addr)

        if node_type == config.NODE_TYPE:
            result = eng.run_local(cmd, timeout=15)
        else:
            result = eng.send_node_command(node_type, "run", {"shell": cmd})

        return jsonify({
            "ok":         result.success,
            "node":       node_type,
            "cmd":        cmd,
            "stdout":     result.stdout[:4000],
            "stderr":     result.stderr[:500],
            "returncode": result.returncode,
        })

    @app.route("/api/reload", methods=["POST"])
    @login_required
    def api_reload():
        """Hot-reload dos módulos de comando."""
        loader.reload()
        return jsonify({"ok": True, "commands": len(loader.registry)})

    # =========================================================================
    # /cmd — compatibilidade com v3 (aceita secret OU sessão autenticada)
    # =========================================================================

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status":   "ok",
            "node":     config.NODE_TYPE,
            "name":     config.ASSISTANT_NAME,
            "palette":  config.get_palette()["label"],
            "android":  config.IS_ANDROID,
            "commands": len(loader.registry),
            "system":   eng.get_system_info(),
        })

    @app.route("/cmd", methods=["POST"])
    def receive_cmd():
        """Recebe comandos de outros nós (autenticado por secret ou sessão)."""
        data = request.get_json(silent=True) or {}

        # Aceita secret (chamadas máquina-a-máquina) OU sessão web autenticada
        authed_by_secret  = data.get("secret") == config.API_SECRET
        authed_by_session = _FLASK_OK and current_user.is_authenticated

        if not authed_by_secret and not authed_by_session:
            return jsonify({"error": "Unauthorized"}), 401

        cmd    = data.get("command", "").lower().strip()
        text   = data.get("text", "")
        origin = data.get("origin", "unknown")
        logger.info(f"[API /cmd] ← {origin} | cmd={cmd!r}")

        if cmd == "speak":
            if not text:
                return jsonify({"error": "Campo 'text' obrigatório."}), 400
            speak(text)
            return jsonify({"ok": True})

        if cmd == "vibrate":
            if config.IS_ANDROID:
                eng.termux_vibrate(int(data.get("duration", 500)))
            return jsonify({"ok": config.IS_ANDROID})

        if cmd == "notify":
            title   = data.get("title", config.ASSISTANT_NAME)
            content = text or data.get("content", "")
            if config.IS_ANDROID:
                eng.termux_notify(title, content)
            else:
                print(f"\n  🔔 [{title}] {content}\n")
            return jsonify({"ok": True})

        if cmd == "torch":
            state = data.get("state", "on") == "on"
            if config.IS_ANDROID:
                eng.termux_torch(state)
            return jsonify({"ok": config.IS_ANDROID})

        if cmd == "run":
            shell_cmd = data.get("shell", "")
            if not shell_cmd:
                return jsonify({"error": "Campo 'shell' obrigatório."}), 400
            result = eng.run_local(shell_cmd, timeout=15)
            return jsonify({"ok": result.success, "stdout": result.stdout,
                            "stderr": result.stderr, "returncode": result.returncode})

        if cmd == "status":
            return jsonify({"ok": True, "system": eng.get_system_info()})

        if cmd == "reload":
            loader.reload()
            return jsonify({"ok": True, "commands": len(loader.registry)})

        matched = loader.dispatch(text or cmd, speak)
        if matched:
            return jsonify({"ok": True, "action": "dispatch"})

        return jsonify({"error": f"Comando desconhecido: {cmd!r}"}), 404

    return app


def _run_api_server(loader: CommandLoader):
    if not _FLASK_OK:
        logger.error("[API] Flask não disponível.")
        return
    _db_init()
    app = _build_app(loader)
    logger.info(f"[API] Iniciando em {config.API_HOST}:{config.API_PORT}")
    logger.info(f"[API] Dashboard → http://localhost:{config.API_PORT}/dashboard")
    app.run(host=config.API_HOST, port=config.API_PORT,
            debug=False, use_reloader=False, threaded=True)


# =============================================================================
# ★  Assistente — loop de voz principal
# =============================================================================

class Assistant:
    _EXIT_WORDS     = {"encerrar", "desligar", "tchau", "adeus", "sair", "fechar"}
    _RELOAD_TRIGGER = "recarregar módulos"

    def __init__(self):
        self.name   = config.ASSISTANT_NAME
        self.node   = config.NODE_TYPE
        self.loader = CommandLoader(config.COMMANDS_DIR)
        self._running = False
        self._rec = self._mic = None
        if _STT_AVAILABLE and not config.IS_ANDROID:
            self._rec = sr.Recognizer()
            self._rec.energy_threshold         = config.MIC_ENERGY_THRESHOLD
            self._rec.pause_threshold          = config.MIC_PAUSE_THRESHOLD
            self._rec.dynamic_energy_threshold = True
            self._mic = sr.Microphone()
        logger.info(f"[CORE] Nó='{self.node}' | Nome='{self.name}' | Android={config.IS_ANDROID}")

    def run(self):
        # Inicia servidor Flask em thread daemon
        t = threading.Thread(target=_run_api_server, args=(self.loader,),
                             name="k7-api", daemon=True)
        t.start()
        time.sleep(0.8)  # aguarda Flask iniciar

        if config.IS_ANDROID:
            self._android_mode()
        elif _STT_AVAILABLE:
            self._voice_loop()
        else:
            self._text_loop()

    def _voice_loop(self):
        self._running = True
        self._greet()
        palette = config.get_palette()
        p = palette["ansi_primary"]
        bar = "─" * 54
        print(f"\n  {p}{bar}{_RESET}")
        print(f"  {p}{_BOLD}  {self.name} [{self.node.upper()}] — ouvindo{_RESET}")
        print(f"  {p}  Dashboard → http://localhost:{config.API_PORT}/dashboard{_RESET}")
        print(f"  {p}{bar}{_RESET}\n")
        while self._running:
            try:
                raw = listen(self._rec, self._mic)
                if raw:
                    print(f"  👤 {raw}", flush=True)
                    self._process(raw)
            except KeyboardInterrupt:
                speak("Até logo!")
                self._running = False
            except Exception as exc:
                logger.critical(f"[CORE] {exc}", exc_info=True)
                time.sleep(1)

    def _text_loop(self):
        self._running = True
        self._greet()
        print(f"\n  [{self.node.upper()}] Modo texto. Ctrl+C para sair.\n")
        while self._running:
            try:
                raw = input("  > ").strip()
                if raw:
                    self._process(raw)
            except (KeyboardInterrupt, EOFError):
                speak("Até logo!")
                self._running = False

    def _android_mode(self):
        self._running = True
        speak(f"{self.name} online no Android. Acesse o dashboard pelo navegador.")
        print(f"\n  [MOBILE] Servidor ativo na porta {config.API_PORT}")
        print(f"  Acesse: http://localhost:{config.API_PORT}/dashboard\n")
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._running = False

    def _process(self, raw: str):
        if not raw.lower().strip().startswith(self.name.lower()):
            return
        command = raw.strip()
        if command.lower().startswith(self.name.lower()):
            command = command[len(self.name):].lstrip(" ,.:;").strip()
        if not command:
            speak(f"Sim, estou aqui.")
            return
        if self._handle_internal(command):
            return
        if not self.loader.dispatch(command, speak):
            speak(f"Não reconheci '{command}'. Diga '{self.name}, ajuda'.")

    def _greet(self):
        speak(f"Olá! Sou {self.name}. Dashboard disponível na porta {config.API_PORT}.")

    def _handle_internal(self, command: str) -> bool:
        lower = command.lower()
        if self._RELOAD_TRIGGER in lower:
            speak("Recarregando módulos.")
            self.loader.reload()
            speak(f"{len(self.loader.registry)} comandos ativos.")
            return True
        for word in self._EXIT_WORDS:
            if word in lower:
                speak("Até logo!")
                self._running = False
                return True
        return False


def main():
    assistant = Assistant()
    assistant.run()

if __name__ == "__main__":
    main()
