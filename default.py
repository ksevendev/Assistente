# =============================================================================
# k7-core | commands/default.py  — v3 (Distributed Nodes)
#
# Módulo de comandos padrão.
# Inclui: status, VSCode, música, WoL, verificar, avisar parceiro.
# =============================================================================

from __future__ import annotations

import logging
from typing import Callable

import config
import engine

logger = logging.getLogger("k7.cmd.default")

DESCRIPTION = "Comandos padrão v3: status, VSCode, música SSH, WoL, avisar nó parceiro"


# ---------------------------------------------------------------------------
# 1. Status do Sistema
# ---------------------------------------------------------------------------

def cmd_status(text: str, speak: Callable) -> None:
    """Status de CPU, RAM e disco do nó atual."""
    speak("Coletando informações do sistema.")
    info = engine.get_system_info()

    if config.IS_ANDROID:
        bat  = info.get("battery", "N/A")
        mem  = info.get("mem_free", "N/A")
        host = info.get("hostname", "N/A")
        speak(
            f"Nó Mobile, host {host}. "
            f"Bateria: {bat}. "
            f"Memória disponível: {mem} kilobytes."
        )
        return

    try:
        cpu      = float(info.get("cpu_percent", 0))
        mem_u    = int(info.get("mem_used",  0))
        mem_t    = int(info.get("mem_total", 1))
        mem_pct  = round(mem_u / mem_t * 100) if mem_t else 0
    except (ValueError, ZeroDivisionError):
        cpu = mem_pct = 0

    node_label = config.NODE_TYPE.capitalize()
    speak(
        f"Nó {node_label}, host {info.get('hostname', 'N/A')}. "
        f"Uptime: {info.get('uptime', 'N/A')}. "
        f"CPU: {cpu:.1f} por cento. "
        f"Memória: {mem_pct} por cento, {mem_u} de {mem_t} megabytes. "
        f"Disco: {info.get('disk_used','?')} de {info.get('disk_total','?')} "
        f"usados, {info.get('disk_percent','?')} ocupado."
    )


# ---------------------------------------------------------------------------
# 2. Abrir VSCode remoto
# ---------------------------------------------------------------------------

def cmd_abrir_vscode(text: str, speak: Callable) -> None:
    """Abre VS Code no PC remoto (Spark) via SSH."""
    if config.IS_ANDROID:
        speak("Não posso abrir aplicativos no Android.")
        return

    lower = text.lower()
    # Detecta se deve usar o nó Spark ou outro alvo
    alias = _detect_node_alias(lower) or "spark"
    speak(f"Abrindo VS Code no nó {alias}.")

    # Tenta via API do nó primeiro
    result = engine.send_node_command(
        alias, "run", {"shell": "DISPLAY=:0 code --no-sandbox &"}
    )

    if result.success:
        speak("VS Code iniciado com sucesso.")
    else:
        # Fallback: SSH direto
        r = engine.run_ssh("DISPLAY=:0 code --no-sandbox &", alias=alias)
        if r.success:
            speak("VS Code iniciado via SSH.")
        else:
            speak(f"Não consegui abrir o VS Code em {alias}.")


# ---------------------------------------------------------------------------
# 3. Controle de Música via SSH (playerctl)
# ---------------------------------------------------------------------------

def cmd_musica(text: str, speak: Callable) -> None:
    """Controla playerctl no PC remoto via SSH ou API."""
    lower = text.lower()
    alias = _detect_node_alias(lower) or "spark"

    actions = [
        (["pausar", "pause", "parar"], "playerctl pause", "Música pausada."),
        (["continuar", "play", "tocar", "reproduzir"], "playerctl play", "Reproduzindo."),
        (["próxima", "proxima", "skip"], "playerctl next", "Próxima faixa."),
        (["anterior", "voltar"], "playerctl previous", "Faixa anterior."),
        (["o que está tocando", "qual música"], "playerctl metadata title", None),
    ]

    for keywords, cmd, response in actions:
        if any(k in lower for k in keywords):
            result = engine.run_ssh(cmd, alias=alias)
            if response is None:
                out = result.stdout if result.success else "N/A"
                speak(f"Tocando: {out}." if out and out != "N/A" else "Nada tocando no momento.")
            else:
                speak(response if result.success else f"Erro ao controlar player em {alias}.")
            return

    speak("Abrindo reprodutor no nó remoto.")
    engine.run_ssh("DISPLAY=:0 rhythmbox &", alias=alias)


# ---------------------------------------------------------------------------
# 4. Acordar PC via Wake-on-LAN
# ---------------------------------------------------------------------------

def cmd_acordar_pc(text: str, speak: Callable) -> None:
    """Envia Magic Packet WoL para ligar PC remoto."""
    lower = text.lower()
    alias = _detect_alias_or_node(lower)

    if not alias:
        pcs = ", ".join(config.REMOTE_PCS.keys())
        speak(f"Qual PC quer ligar? Disponíveis: {pcs}.")
        return

    entry = config.REMOTE_PCS.get(alias)
    if not entry:
        speak(f"PC {alias} não encontrado nas configurações.")
        return

    ip, mac = entry
    if not mac:
        speak(f"{alias} não possui endereço MAC configurado.")
        return

    speak(f"Enviando sinal Wake-on-LAN para {alias}.")
    ok = engine.wake_pc(alias=alias)
    if ok:
        speak(f"Sinal enviado para {alias}. Aguardando resposta...")
        import time; time.sleep(8)
        online = engine.is_host_reachable(ip, port=22)
        speak(f"{alias} está {'online' if online else 'ainda inicializando'}.")
    else:
        speak(f"Falha ao enviar sinal para {alias}.")


# ---------------------------------------------------------------------------
# 5. Verificar conectividade de nó
# ---------------------------------------------------------------------------

def cmd_verificar(text: str, speak: Callable) -> None:
    """Verifica se um nó ou PC está online."""
    lower = text.lower()
    alias = _detect_alias_or_node(lower)

    if alias:
        # Tenta no mapa de nós completo
        node_info = config.NETWORK_NODES.get(alias)
        ip = node_info["ip"] if node_info else (config.REMOTE_PCS.get(alias) or (None,))[0]
        if not ip:
            speak(f"IP de {alias} não configurado.")
            return
        speak(f"Verificando {alias}...")
        port = node_info.get("port", config.SSH_PORT) if node_info else config.SSH_PORT
        online = engine.is_host_reachable(ip, port=port)
        speak(f"{alias} está {'online' if online else 'offline'}.")
    else:
        # Verifica todos os nós da rede
        speak("Verificando todos os nós da rede.")
        results = []
        for node_type, info in config.NETWORK_NODES.items():
            if node_type == config.NODE_TYPE:
                continue
            ip   = info["ip"]
            port = info.get("port", 7007)
            ok   = engine.is_host_reachable(ip, port=port)
            results.append(f"{info['name']}: {'online' if ok else 'offline'}")
        speak("Resultado: " + ", ".join(results) + "." if results else "Nenhum nó configurado.")


# ---------------------------------------------------------------------------
# 6. ★  Avisar Parceiro — envia mensagem para outro nó falar
# ---------------------------------------------------------------------------

def cmd_avisar(text: str, speak: Callable) -> None:
    """
    Envia uma mensagem de texto para ser falada em outro nó da rede.

    Exemplos de fala:
        "Seven, avisar Spark: o build terminou"
        "Seven, avisar Mobile que tem café"
        "Seven, avisar Seven que a reunião começou"  (envia para si mesmo via API)

    Protocolo:
        Chama engine.send_node_command(target, "speak", {"text": mensagem})
        No Android, também envia notificação push + vibração.
    """
    lower = text.lower()
    target_node = None

    # Detecta o nó alvo na fala
    node_name_map = {
        info["name"].lower(): node_type
        for node_type, info in config.NETWORK_NODES.items()
    }
    # Também aceita o node_type diretamente
    for node_type in config.NETWORK_NODES:
        node_name_map[node_type] = node_type

    for name_key, node_type in node_name_map.items():
        if name_key in lower:
            target_node = node_type
            break

    if not target_node:
        nodes = ", ".join(v["name"] for v in config.NETWORK_NODES.values())
        speak(f"Qual nó devo avisar? Disponíveis: {nodes}.")
        return

    # Extrai a mensagem — tudo após ":" ou palavras-chave de separação
    import re
    msg = ""
    # Tenta extrair após ":" ou "que" ou "sobre"
    patterns = [
        r"[:：]\s*(.+)$",
        r"\bque\b\s+(.+)$",
        r"\bsobre\b\s+(.+)$",
        r"\bdizendo\b\s+(.+)$",
        r"\bmensagem\b\s+(.+)$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            msg = m.group(1).strip()
            break

    if not msg:
        # Fallback: remove nome do nó e palavras de comando e usa o resto
        cleaned = re.sub(
            r"\b(avisar?|notificar?|" + "|".join(node_name_map.keys()) + r")\b",
            "", lower, flags=re.IGNORECASE
        ).strip(" ,.:;")
        msg = cleaned if len(cleaned) > 3 else ""

    if not msg:
        speak(f"Qual mensagem devo enviar para {config.NETWORK_NODES[target_node]['name']}?")
        return

    target_name = config.NETWORK_NODES[target_node]["name"]
    origin_name = config.ASSISTANT_NAME

    # Formata a mensagem com identificação de origem
    full_msg = f"Mensagem de {origin_name}: {msg}"

    speak(f"Avisando {target_name}.")
    logger.info(f"[AVISAR] → {target_node} | {full_msg!r}")

    # Envia comando de fala
    result_speak = engine.send_node_command(
        target_node, "speak", {"text": full_msg}
    )

    # Se for mobile: também vibra + notificação push
    if target_node == "mobile":
        engine.send_node_command(target_node, "vibrate", {"duration": 800})
        engine.send_node_command(
            target_node, "notify",
            {"title": f"📢 {origin_name}", "content": msg}
        )

    if result_speak.success:
        speak(f"Mensagem entregue para {target_name}.")
    else:
        speak(
            f"Não consegui alcançar {target_name}. "
            f"Verifique se o nó está online na porta {config.API_PORT}."
        )


# ---------------------------------------------------------------------------
# 7. Avisar TODOS os nós
# ---------------------------------------------------------------------------

def cmd_avisar_todos(text: str, speak: Callable) -> None:
    """
    Broadcast: envia uma mensagem para TODOS os outros nós da rede.
    Exemplo: "Seven, avisar todos: reunião em 5 minutos"
    """
    import re
    msg = ""
    m = re.search(r"[:：]\s*(.+)$", text)
    if m:
        msg = m.group(1).strip()
    else:
        cleaned = re.sub(r"\b(avisar?\s+todos?|broadcast)\b", "", text, flags=re.IGNORECASE)
        msg = cleaned.strip(" ,.:;")

    if not msg:
        speak("Qual mensagem devo enviar para todos?")
        return

    full_msg = f"Broadcast de {config.ASSISTANT_NAME}: {msg}"
    speak(f"Enviando mensagem para todos os nós: {msg}")

    results = engine.broadcast_node_command("speak", {"text": full_msg})

    successes = sum(1 for r in results.values() if r.success)
    total     = len(results)
    speak(f"Mensagem entregue para {successes} de {total} nó{'s' if total != 1 else ''}.")


# ---------------------------------------------------------------------------
# 8. Controle de Termux (Mobile → lanterna, vibração)
# ---------------------------------------------------------------------------

def cmd_lanterna(text: str, speak: Callable) -> None:
    """Liga ou desliga a lanterna do celular (local ou remoto)."""
    lower = text.lower()
    ligar = any(w in lower for w in ["ligar", "acender", "on", "ativar"])
    state = ligar

    # Determina alvo
    if "mobile" in lower or "celular" in lower:
        result = engine.send_node_command("mobile", "torch", {"state": "on" if state else "off"})
        speak(f"Lanterna do celular {'ligada' if state else 'desligada'}."
              if result.success else "Não consegui controlar a lanterna do celular.")
    elif config.IS_ANDROID:
        engine.termux_torch(state)
        speak(f"Lanterna {'ligada' if state else 'desligada'}.")
    else:
        speak("Lanterna disponível apenas no dispositivo móvel.")


# ---------------------------------------------------------------------------
# 9. Ajuda
# ---------------------------------------------------------------------------

def cmd_ajuda(text: str, speak: Callable) -> None:
    """Lista os comandos disponíveis."""
    node = config.NODE_TYPE
    base = (
        "Comandos disponíveis: "
        "status do sistema, "
        "verificar nó ou PC, "
        "avisar seguido do nome do nó e a mensagem, "
        "avisar todos com a mensagem para broadcast, "
        "recarregar módulos para hot-reload, "
        "encerrar para desligar. "
    )
    extra = ""
    if node in ("seven", "spark"):
        extra = (
            "Também posso: "
            "abrir vscode no PC remoto, "
            "controlar música via SSH, "
            "ligar computadores via Wake-on-LAN, "
            "controlar a lanterna do celular."
        )
    elif node == "mobile":
        extra = "No Android, recebo comandos da rede e posso vibrar, notificar e usar a lanterna."
    speak(base + extra)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _detect_node_alias(text: str) -> str | None:
    """Detecta alias de nó da rede no texto."""
    for node_type, info in config.NETWORK_NODES.items():
        if info["name"].lower() in text.lower() or node_type in text.lower():
            return node_type
    return None


def _detect_alias_or_node(text: str) -> str | None:
    """Detecta alias em REMOTE_PCS ou NETWORK_NODES."""
    lower = text.lower()
    for alias in config.REMOTE_PCS:
        if alias in lower:
            return alias
    return _detect_node_alias(text)


# ---------------------------------------------------------------------------
# ★  Registro de comandos
# ---------------------------------------------------------------------------

COMMANDS: dict = {

    # Status
    "status do sistema":        cmd_status,
    "informações do sistema":   cmd_status,
    "como está o sistema":      cmd_status,
    "status":                   cmd_status,

    # VSCode
    "abrir vscode":             cmd_abrir_vscode,
    "abrir visual studio":      cmd_abrir_vscode,
    "abrir editor":             cmd_abrir_vscode,

    # Música
    "o que está tocando":       cmd_musica,
    "qual música":              cmd_musica,
    "pausar música":            cmd_musica,
    "continuar música":         cmd_musica,
    "próxima música":           cmd_musica,
    "música anterior":          cmd_musica,
    "próxima":                  cmd_musica,
    "anterior":                 cmd_musica,
    "pausar":                   cmd_musica,
    "música":                   cmd_musica,
    "musica":                   cmd_musica,

    # WoL
    "despertar pc":             cmd_acordar_pc,
    "acordar pc":               cmd_acordar_pc,
    "ligar pc":                 cmd_acordar_pc,
    "acordar":                  cmd_acordar_pc,
    "despertar":                cmd_acordar_pc,
    "ligar":                    cmd_acordar_pc,
    "wake":                     cmd_acordar_pc,

    # Verificar
    "verificar todos os nós":   cmd_verificar,
    "verificar rede":           cmd_verificar,
    "verificar":                cmd_verificar,
    "está online":              cmd_verificar,
    "ping":                     cmd_verificar,

    # ★ Avisar parceiro (S2 feature)
    "avisar todos":             cmd_avisar_todos,
    "broadcast":                cmd_avisar_todos,
    "avisar":                   cmd_avisar,
    "notificar":                cmd_avisar,
    "mandar mensagem":          cmd_avisar,

    # Mobile
    "lanterna":                 cmd_lanterna,
    "ligar lanterna":           cmd_lanterna,
    "acender lanterna":         cmd_lanterna,

    # Ajuda
    "o que você faz":           cmd_ajuda,
    "o que sabe fazer":         cmd_ajuda,
    "comandos":                 cmd_ajuda,
    "ajuda":                    cmd_ajuda,
    "help":                     cmd_ajuda,
}
