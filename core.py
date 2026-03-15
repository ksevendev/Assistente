# =============================================================================
# k7-core | core.py  — v3 (Distributed Nodes)
#
# Responsabilidades:
#   1. Detectar ambiente (Linux desktop / Android Termux)
#   2. Configurar logging centralizado com paleta de cor por nó
#   3. Iniciar servidor Flask (porta 7007) em thread separada
#   4. Gerenciar TTS/STT adaptado ao ambiente
#   5. Carregar módulos de comando dinamicamente (CommandLoader + hot-reload)
#   6. Executar loop de voz principal
# =============================================================================

from __future__ import annotations

import importlib.util
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import config

# ---------------------------------------------------------------------------
# Logging colorido por nó
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD  = "\033[1m"
_PALETTE = config.get_palette()
_PC = _PALETTE["primary"]    # cor primária do nó
_SC = _PALETTE["secondary"]  # cor secundária


class _NodeFormatter(logging.Formatter):
    """Formatter que aplica a paleta do nó ao output no console."""
    LEVEL_COLORS = {
        "DEBUG":    "\033[90m",
        "INFO":     _PC,
        "WARNING":  "\033[93m",
        "ERROR":    "\033[91m",
        "CRITICAL": "\033[41m",
    }

    def format(self, record: logging.LogRecord) -> str:
        lc  = self.LEVEL_COLORS.get(record.levelname, "")
        msg = super().format(record)
        return f"{lc}{msg}{_RESET}"


def _setup_logging() -> None:
    root = logging.getLogger("k7")
    root.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    fmt  = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    node_fmt = _NodeFormatter(
        fmt="%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    if config.LOG_TO_CONSOLE:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(node_fmt)
        root.addHandler(ch)

    if config.LOG_TO_FILE:
        fh = logging.handlers.RotatingFileHandler(
            config.LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)


_setup_logging()
logger = logging.getLogger("k7.core")


# ---------------------------------------------------------------------------
# Imports condicionais — módulos pesados desabilitados no Android
# ---------------------------------------------------------------------------

_STT_AVAILABLE = False
_MIC_AVAILABLE = False

if not config.IS_ANDROID:
    try:
        import speech_recognition as sr
        _STT_AVAILABLE = True
        _MIC_AVAILABLE = True
    except ImportError:
        logger.warning("[CORE] SpeechRecognition não instalado — STT desabilitado.")
else:
    logger.info("[CORE] Android detectado — STT por microfone desabilitado.")

# Flask (necessário para o servidor de API)
try:
    from flask import Flask, request, jsonify
    _FLASK_OK = True
except ImportError:
    _FLASK_OK = False
    logger.warning("[CORE] Flask não instalado — servidor de API desabilitado.")


# ---------------------------------------------------------------------------
# ★  Síntese de Voz — TTS (adaptada ao ambiente)
# ---------------------------------------------------------------------------

def _speak_espeak(text: str) -> None:
    import subprocess
    for bin_name in ("espeak-ng", "espeak"):
        try:
            subprocess.run(
                [bin_name, "-v", config.ESPEAK_VOICE,
                 "-s", str(config.ESPEAK_SPEED),
                 "-a", str(config.ESPEAK_VOLUME), text],
                check=True, capture_output=True, timeout=30,
            )
            return
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.error(f"[TTS] espeak erro: {exc}")
            return


def _speak_gtts(text: str) -> None:
    try:
        from gtts import gTTS
        import pygame, os as _os
        lang = config.ASSISTANT_LANG.split("-")[0]
        tts  = gTTS(text=text, lang=lang, slow=False)
        tmp  = _os.path.join(config.TEMP_DIR, "_tts.mp3")
        tts.save(tmp)
        pygame.mixer.init()
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.quit()
    except Exception as exc:
        logger.error(f"[TTS] gTTS erro: {exc}")
        _speak_espeak(text)   # fallback


def _speak_termux(text: str) -> None:
    """Síntese de voz nativa do Android via Termux API."""
    import subprocess
    try:
        subprocess.run(
            ["termux-tts-speak", text],
            timeout=30, check=False,
        )
    except FileNotFoundError:
        logger.error("[TTS] termux-tts-speak não encontrado. Instale o Termux:API app.")
    except Exception as exc:
        logger.error(f"[TTS] Termux TTS erro: {exc}")


def speak(text: str) -> None:
    """
    Faz o nó atual falar.
    Seleciona automaticamente o engine correto para o ambiente.
    """
    name = config.ASSISTANT_NAME
    logger.info(f"[TTS] {name}: {text!r}")
    palette = config.get_palette()
    print(f"\n  {palette['primary']}{_BOLD}🔊  {name}:{_RESET} {text}\n", flush=True)

    engine = config.VOICE_ENGINE.lower()
    try:
        if engine == "termux" or config.IS_ANDROID:
            _speak_termux(text)
        elif engine == "gtts":
            _speak_gtts(text)
        else:
            _speak_espeak(text)
    except Exception as exc:
        logger.error(f"[TTS] Falha crítica no TTS: {exc}")


# ---------------------------------------------------------------------------
# ★  Reconhecimento de Voz — STT
# ---------------------------------------------------------------------------

def listen(recognizer: "sr.Recognizer", mic: "sr.Microphone") -> Optional[str]:
    """
    Ouve o microfone e retorna texto reconhecido.
    Retorna None em silêncio, erro ou se STT estiver desabilitado.
    """
    if not _STT_AVAILABLE:
        return None

    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.4)
        try:
            audio = recognizer.listen(
                source,
                timeout=config.MIC_TIMEOUT,
                phrase_time_limit=config.MIC_PHRASE_TIME_LIMIT,
            )
        except sr.WaitTimeoutError:
            return None

    try:
        text = recognizer.recognize_google(audio, language=config.ASSISTANT_LANG)
        logger.info(f"[STT] Reconhecido: {text!r}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        logger.error(f"[STT] Erro no serviço Google: {exc}")
        return None


# ---------------------------------------------------------------------------
# ★  CommandLoader — carregamento dinâmico de módulos
# ---------------------------------------------------------------------------

class CommandLoader:
    """
    Carrega todos os arquivos .py de commands/ e registra seus COMMANDS.
    Suporta hot-reload via reload().
    """

    def __init__(self, commands_dir: str) -> None:
        self._dir      = Path(commands_dir)
        self._registry: dict[str, Callable] = {}
        self._load_all()

    @property
    def registry(self) -> dict[str, Callable]:
        return dict(self._registry)

    def reload(self) -> None:
        for key in [k for k in sys.modules if k.startswith("commands.")]:
            del sys.modules[key]
        self._registry.clear()
        self._load_all()
        logger.info(f"[LOADER] Hot-reload concluído: {len(self._registry)} gatilho(s).")

    def dispatch(self, text: str, speak_fn: Callable) -> bool:
        lower = text.lower().strip()
        for trigger in sorted(self._registry, key=len, reverse=True):
            if trigger in lower:
                logger.info(f"[DISPATCH] '{trigger}' → {self._registry[trigger].__name__}")
                try:
                    self._registry[trigger](text, speak_fn)
                except Exception as exc:
                    logger.error(f"[DISPATCH] Erro em '{trigger}': {exc}", exc_info=True)
                    speak_fn("Erro interno ao executar esse comando.")
                return True
        return False

    def execute_by_name(self, command_key: str, text: str = "", speak_fn: Callable = speak) -> bool:
        """Executa um comando diretamente pelo nome do gatilho (usado pela API)."""
        fn = self._registry.get(command_key.lower())
        if fn:
            try:
                fn(text, speak_fn)
                return True
            except Exception as exc:
                logger.error(f"[LOADER] execute_by_name '{command_key}': {exc}")
        return False

    def _load_all(self) -> None:
        if not self._dir.is_dir():
            logger.error(f"[LOADER] Diretório não encontrado: {self._dir}")
            return
        total = 0
        for path in sorted(self._dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            _, t = self._load_module(path)
            total += t
        logger.info(f"[LOADER] {total} gatilho(s) registrado(s) de {self._dir.name}/")

    def _load_module(self, path: Path) -> tuple[int, int]:
        name = f"commands.{path.stem}"
        try:
            spec   = importlib.util.spec_from_file_location(name, str(path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.error(f"[LOADER] Falha ao carregar '{path.name}': {exc}", exc_info=True)
            return 0, 0

        commands = getattr(module, "COMMANDS", None)
        if not isinstance(commands, dict):
            logger.warning(f"[LOADER] '{path.name}' sem COMMANDS dict — ignorado.")
            return 0, 0

        count = 0
        for trigger, fn in commands.items():
            if callable(fn):
                self._registry[trigger.lower().strip()] = fn
                count += 1

        desc = getattr(module, "DESCRIPTION", path.stem)
        logger.info(f"[LOADER]   ✓ {path.name} ({count} cmd) — {desc}")
        return 1, count


# ---------------------------------------------------------------------------
# ★  API Server Flask — /cmd  (porta 7007)
# ---------------------------------------------------------------------------

def _build_flask_app(loader: CommandLoader) -> "Flask":
    """
    Constrói a aplicação Flask que serve como endpoint de comandos entre nós.

    Rotas:
        GET  /health  → status do nó
        POST /cmd     → recebe e executa comando JSON
    """
    app = Flask(f"k7-{config.NODE_TYPE}")
    # Silencia o log de acesso do Werkzeug para não poluir o console
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/health", methods=["GET"])
    def health():
        """Rota de health check — retorna identidade e estado do nó."""
        import engine
        info = engine.get_system_info()
        return jsonify({
            "status":     "ok",
            "node":       config.NODE_TYPE,
            "name":       config.ASSISTANT_NAME,
            "palette":    config.get_palette()["label"],
            "android":    config.IS_ANDROID,
            "commands":   len(loader.registry),
            "system":     info,
        })

    @app.route("/cmd", methods=["POST"])
    def receive_cmd():
        """
        Recebe um comando de outro nó e o executa localmente.

        Body JSON esperado:
            {
                "command": "speak" | "vibrate" | "notify" | "run" | "reload" | <gatilho>,
                "text":    "...",          # para speak / notify
                "title":   "...",          # para notify
                "shell":   "...",          # para run
                "origin":  "seven",        # nó de origem
                "secret":  "<API_SECRET>"
            }
        """
        import engine as eng

        data = request.get_json(silent=True) or {}

        # Autenticação simples por token compartilhado
        if data.get("secret") != config.API_SECRET:
            logger.warning(f"[API] Requisição rejeitada — secret inválido. Origem: {data.get('origin')}")
            return jsonify({"error": "Unauthorized"}), 401

        cmd    = data.get("command", "").lower().strip()
        text   = data.get("text", "")
        origin = data.get("origin", "unknown")

        logger.info(f"[API] ← {origin} | cmd={cmd!r} | text={text[:60]!r}")

        # --- Comandos nativos de sistema ---

        if cmd == "speak":
            if not text:
                return jsonify({"error": "Campo 'text' obrigatório para speak."}), 400
            speak(text)
            return jsonify({"ok": True, "action": "speak", "text": text})

        if cmd == "vibrate":
            duration = int(data.get("duration", 500))
            if config.IS_ANDROID:
                eng.termux_vibrate(duration)
                return jsonify({"ok": True, "action": "vibrate", "duration": duration})
            return jsonify({"ok": False, "reason": "Vibrate disponível apenas no Android."})

        if cmd == "notify":
            title   = data.get("title", config.ASSISTANT_NAME)
            content = text or data.get("content", "")
            if config.IS_ANDROID:
                eng.termux_notify(title, content)
                return jsonify({"ok": True, "action": "notify"})
            # No desktop, imprime no console como fallback
            print(f"\n  🔔  [{title}] {content}\n")
            return jsonify({"ok": True, "action": "notify", "fallback": "console"})

        if cmd == "torch":
            state = data.get("state", "on") == "on"
            if config.IS_ANDROID:
                eng.termux_torch(state)
                return jsonify({"ok": True, "action": "torch", "state": state})
            return jsonify({"ok": False, "reason": "Lanterna disponível apenas no Android."})

        if cmd == "run":
            shell_cmd = data.get("shell", "")
            if not shell_cmd:
                return jsonify({"error": "Campo 'shell' obrigatório para run."}), 400
            result = eng.run_local(shell_cmd, timeout=15)
            return jsonify({
                "ok":         result.success,
                "stdout":     result.stdout,
                "stderr":     result.stderr,
                "returncode": result.returncode,
            })

        if cmd == "status":
            return jsonify({"ok": True, "system": eng.get_system_info()})

        if cmd == "reload":
            loader.reload()
            return jsonify({"ok": True, "commands": len(loader.registry)})

        # --- Tenta despachar como gatilho de módulo ---
        matched = loader.dispatch(text or cmd, speak)
        if matched:
            return jsonify({"ok": True, "action": "dispatch", "trigger": cmd})

        return jsonify({"error": f"Comando desconhecido: {cmd!r}"}), 404

    return app


def _run_api_server(loader: CommandLoader) -> None:
    """Inicia o servidor Flask em thread daemon."""
    if not _FLASK_OK:
        logger.error("[API] Flask não disponível — servidor não iniciado.")
        return

    app = _build_flask_app(loader)
    logger.info(f"[API] Servidor iniciando em {config.API_HOST}:{config.API_PORT}")
    try:
        app.run(
            host=config.API_HOST,
            port=config.API_PORT,
            debug=False,
            use_reloader=False,   # evita conflito com o hot-reload dos módulos
            threaded=True,
        )
    except OSError as exc:
        logger.error(f"[API] Falha ao iniciar servidor: {exc}")


# ---------------------------------------------------------------------------
# ★  Assistente — classe principal
# ---------------------------------------------------------------------------

class Assistant:
    """
    Gerencia o ciclo de vida do assistente para este nó.

    Fluxo de inicialização:
        1. Detecta ambiente (Android / Desktop)
        2. Inicia CommandLoader
        3. Sobe thread do servidor Flask (porta 7007)
        4. Inicia loop de voz (ou modo texto no Android)
    """

    _EXIT_WORDS    = {"encerrar", "desligar", "tchau", "adeus", "sair", "fechar"}
    _RELOAD_TRIGGER = "recarregar módulos"

    def __init__(self) -> None:
        self.name   = config.ASSISTANT_NAME
        self.node   = config.NODE_TYPE
        self.loader = CommandLoader(config.COMMANDS_DIR)
        self._running = False

        # STT — só em desktop
        self._rec = None
        self._mic = None
        if _STT_AVAILABLE and not config.IS_ANDROID:
            self._rec = sr.Recognizer()
            self._rec.energy_threshold    = config.MIC_ENERGY_THRESHOLD
            self._rec.pause_threshold     = config.MIC_PAUSE_THRESHOLD
            self._rec.dynamic_energy_threshold = True
            self._mic = sr.Microphone()

        logger.info(
            f"[CORE] Nó '{self.node}' | Assistente '{self.name}' | "
            f"Android={config.IS_ANDROID} | STT={_STT_AVAILABLE}"
        )

    # -----------------------------------------------------------------------
    # API Server thread
    # -----------------------------------------------------------------------

    def _start_api_server(self) -> None:
        """Inicia o servidor de API em thread daemon."""
        t = threading.Thread(
            target=_run_api_server,
            args=(self.loader,),
            name="k7-api-server",
            daemon=True,
        )
        t.start()
        logger.info(f"[CORE] Thread API iniciada → http://{config.API_HOST}:{config.API_PORT}")

    # -----------------------------------------------------------------------
    # Loop principal
    # -----------------------------------------------------------------------

    def run(self) -> None:
        """Ponto de entrada principal. Inicia API e loop de escuta."""
        self._start_api_server()
        time.sleep(0.5)   # aguarda Flask subir

        if config.IS_ANDROID:
            self._run_android_mode()
        elif _STT_AVAILABLE:
            self._run_voice_loop()
        else:
            logger.warning("[CORE] STT indisponível — entrando em modo texto (stdin).")
            self._run_text_loop()

    def _run_voice_loop(self) -> None:
        """Loop de escuta por microfone (modo desktop)."""
        self._running = True
        self._greet()
        palette = config.get_palette()
        p = palette["primary"]

        bar = "─" * 54
        print(f"\n  {p}{bar}{_RESET}")
        print(f"  {p}{_BOLD}  {self.name} [{self.node.upper()}] — ouvindo...{_RESET}")
        print(f"  {p}{bar}{_RESET}\n")

        while self._running:
            try:
                raw = listen(self._rec, self._mic)
                if raw is None:
                    continue
                print(f"  👤 {raw}", flush=True)
                self._process(raw)
            except KeyboardInterrupt:
                speak("Até logo!")
                self._running = False
            except Exception as exc:
                logger.critical(f"[CORE] Erro no loop: {exc}", exc_info=True)
                time.sleep(1)

    def _run_text_loop(self) -> None:
        """Loop de entrada por teclado (fallback sem microfone)."""
        self._running = True
        self._greet()
        print(f"\n  [{self.node.upper()}] Modo texto — digite comandos (Ctrl+C para sair)\n")

        while self._running:
            try:
                raw = input(f"  > ").strip()
                if raw:
                    self._process(raw)
            except (KeyboardInterrupt, EOFError):
                speak("Até logo!")
                self._running = False

    def _run_android_mode(self) -> None:
        """
        Modo Android: sem microfone, apenas servidor de API ativo.
        O celular recebe comandos dos outros nós via HTTP.
        """
        self._running = True
        speak(f"{self.name} online no Android. Aguardando comandos da rede.")
        palette = config.get_palette()
        p = palette["primary"]
        print(f"\n  {p}[MOBILE] {self.name} em modo servidor — porta {config.API_PORT}{_RESET}")
        print(f"  {p}Ctrl+C para encerrar.{_RESET}\n")

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._running = False
            logger.info("[CORE] Android mode encerrado.")

    # -----------------------------------------------------------------------
    # Processamento de fala / texto
    # -----------------------------------------------------------------------

    def _process(self, raw: str) -> None:
        """Pipeline: verificar nome → extrair comando → executar."""
        if not self._is_addressed(raw):
            logger.debug(f"[CORE] Ignorado (não endereçado): {raw!r}")
            return

        command = self._strip_name(raw)

        if not command:
            speak(f"Sim, estou aqui. Como posso ajudar?")
            return

        if self._handle_internal(command):
            return

        matched = self.loader.dispatch(command, speak)
        if not matched:
            speak(
                f"Não reconheci '{command}'. "
                f"Diga '{self.name}, ajuda' para ver os comandos."
            )

    def _greet(self) -> None:
        node_label = {"seven": "Notebook", "spark": "PC Desktop", "mobile": "Android"}.get(
            self.node, self.node
        )
        speak(
            f"Olá! Sou {self.name}, assistente do {node_label}. "
            f"Servidor de rede ativo na porta {config.API_PORT}. "
            f"Diga {self.name} seguido de um comando."
        )

    def _is_addressed(self, text: str) -> bool:
        return text.lower().lstrip().startswith(self.name.lower())

    def _strip_name(self, text: str) -> str:
        s = text.strip()
        if s.lower().startswith(self.name.lower()):
            s = s[len(self.name):]
        return s.lstrip(" ,.:;").strip()

    def _handle_internal(self, command: str) -> bool:
        lower = command.lower().strip()

        if self._RELOAD_TRIGGER in lower:
            speak("Recarregando módulos de comando.")
            self.loader.reload()
            n = len(self.loader.registry)
            speak(f"Pronto. {n} comando{'s' if n != 1 else ''} ativo{'s' if n != 1 else ''}.")
            return True

        for word in self._EXIT_WORDS:
            if word in lower:
                speak(f"Encerrando {self.name}. Até logo!")
                self._running = False
                return True

        return False


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    assistant = Assistant()
    assistant.run()


if __name__ == "__main__":
    main()
