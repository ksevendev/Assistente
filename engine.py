# =============================================================================
# k7-core | engine.py  — v2.0 (Dynamic Discovery)
# Motor de execução: local, SSH, WoL, API inter-nós e Termux.
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import config

logger = logging.getLogger("k7.engine")

# Import condicional de paramiko (não disponível no Termux sem compilação)
try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    _PARAMIKO_OK = False
    logger.warning("[ENGINE] paramiko não disponível — SSH desabilitado.")

# Import condicional de requests
try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False
    logger.warning("[ENGINE] requests não disponível — chamadas HTTP desabilitadas.")


# ---------------------------------------------------------------------------
# Resultado padronizado
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    """Resultado padronizado de qualquer execução de comando."""
    stdout:     str  = ""
    stderr:     str  = ""
    returncode: int  = 0
    success:    bool = True
    error_msg:  str  = ""

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        return self.stdout if self.success else f"[ERRO] {self.error_msg}"


# ---------------------------------------------------------------------------
# Execução LOCAL
# ---------------------------------------------------------------------------

def run_local(command: str, timeout: int = 30, shell: bool = True) -> CommandResult:
    """Executa um comando no sistema local via subprocess."""
    logger.debug(f"[LOCAL] {command!r}")
    try:
        proc = subprocess.run(
            command, shell=shell, capture_output=True, text=True, timeout=timeout
        )
        ok = proc.returncode == 0
        return CommandResult(
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            returncode=proc.returncode,
            success=ok,
            error_msg=proc.stderr.strip() if not ok else "",
        )
    except subprocess.TimeoutExpired:
        msg = f"Timeout após {timeout}s"
        logger.error(f"[LOCAL] {msg}")
        return CommandResult(success=False, returncode=-1, error_msg=msg)
    except Exception as exc:
        logger.error(f"[LOCAL] {exc}", exc_info=True)
        return CommandResult(success=False, returncode=-1, error_msg=str(exc))


def run_local_background(command: str) -> Optional[subprocess.Popen]:
    """Inicia um processo em background (não bloqueia)."""
    logger.debug(f"[LOCAL BG] {command!r}")
    try:
        return subprocess.Popen(
            command, shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        logger.error(f"[LOCAL BG] {exc}")
        return None


# ---------------------------------------------------------------------------
# Execução REMOTA via SSH
# ---------------------------------------------------------------------------

def run_ssh(
    command: str,
    host: Optional[str] = None,
    alias: Optional[str] = None,
    timeout: int = 30,
) -> CommandResult:
    """
    Executa um comando em host remoto via SSH com chave RSA.
    No Android (Termux), desabilitado automaticamente.
    """
    if not _PARAMIKO_OK:
        return CommandResult(success=False, returncode=-1,
                             error_msg="paramiko não disponível neste ambiente.")

    if config.IS_ANDROID:
        return CommandResult(success=False, returncode=-1,
                             error_msg="SSH de saída desabilitado no Android.")

    # Resolve host
    if host is None:
        if alias:
            entry = config.REMOTE_PCS.get(alias)
            if not entry:
                msg = f"Alias '{alias}' não encontrado."
                return CommandResult(success=False, returncode=-1, error_msg=msg)
            host = entry[0]
        else:
            host = config.PC_IP

    key_path = os.path.expanduser(config.SSH_KEY)
    if not os.path.isfile(key_path):
        return CommandResult(success=False, returncode=-1,
                             error_msg=f"Chave SSH não encontrada: {key_path}")

    logger.debug(f"[SSH] {config.SSH_USER}@{host} → {command!r}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host, port=config.SSH_PORT,
            username=config.SSH_USER, key_filename=key_path,
            timeout=config.SSH_TIMEOUT, look_for_keys=False, allow_agent=False,
        )
        _, out_ch, err_ch = client.exec_command(command, timeout=timeout)
        out = out_ch.read().decode("utf-8", errors="replace").strip()
        err = err_ch.read().decode("utf-8", errors="replace").strip()
        rc  = out_ch.channel.recv_exit_status()
        ok  = rc == 0
        logger.debug(f"[SSH] RC={rc} | OUT={out[:100]}")
        return CommandResult(stdout=out, stderr=err, returncode=rc,
                             success=ok, error_msg=err if not ok else "")
    except Exception as exc:
        msg = str(exc)
        logger.error(f"[SSH] {msg}")
        return CommandResult(success=False, returncode=-1, error_msg=msg)
    finally:
        client.close()


def is_host_reachable(host: str, port: int = None, timeout: int = 2) -> bool:
    """Verifica conectividade TCP com um host."""
    port = port or config.SSH_PORT
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


# ---------------------------------------------------------------------------
# Wake-on-LAN
# ---------------------------------------------------------------------------

def send_magic_packet(mac: str, broadcast: str = None, port: int = None) -> bool:
    """Envia um Magic Packet WoL (102 bytes: 0xFF×6 + MAC×16)."""
    broadcast = broadcast or config.WOL_BROADCAST
    port      = port      or config.WOL_PORT

    mac_clean = mac.upper().replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12 or not all(c in "0123456789ABCDEF" for c in mac_clean):
        logger.error(f"[WOL] MAC inválido: {mac!r}")
        return False
    try:
        mac_bytes = bytes.fromhex(mac_clean)
        magic     = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(magic, (broadcast, port))
        logger.info(f"[WOL] Magic Packet enviado → {mac}")
        return True
    except OSError as exc:
        logger.error(f"[WOL] {exc}")
        return False


def wake_pc(alias: str = None, mac: str = None) -> bool:
    """Acorda PC via WoL pelo alias ou MAC direto."""
    if mac is None:
        if alias:
            entry = config.REMOTE_PCS.get(alias)
            if not entry:
                logger.error(f"[WOL] Alias '{alias}' não encontrado.")
                return False
            mac = entry[1]
        else:
            mac = config.PC_MAC
    return send_magic_packet(mac)


# ---------------------------------------------------------------------------
# ★  COMUNICAÇÃO INTER-NÓS — API HTTP (porta 2026)
# ---------------------------------------------------------------------------

def _resolve_node_address(target_node: str) -> tuple[str, int]:
    """
    Resolve (ip, port) de um nó usando a seguinte prioridade:
        1. NodeRegistry em memória (dados do mDNS — mais recentes)
        2. config.NETWORK_NODES (estático / seed)

    Retorna ("", 0) se o nó não for encontrado em nenhuma fonte.
    """
    # Tenta o NodeRegistry dinâmico primeiro (importação lazy para evitar
    # ciclo core ↔ engine — core importa engine, engine não importa core)
    try:
        from core import get_registry
        entry = get_registry().get(target_node)
        if entry and entry.get("ip"):
            return entry["ip"], int(entry.get("port", config.API_PORT))
    except (ImportError, Exception):
        pass   # core ainda não inicializado ou registry indisponível

    # Fallback: config estático
    node_info = config.NETWORK_NODES.get(target_node, {})
    ip   = node_info.get("ip", "")
    port = int(node_info.get("port", config.API_PORT))
    return ip, port


def send_node_command(
    target_node: str,
    command: str,
    payload: Optional[dict] = None,
    timeout: int = 8,
) -> CommandResult:
    """
    Envia um comando para outro nó via HTTP POST na porta 2026 (v2.0).

    Rota alvo: POST http://<node_ip>:2026/cmd

    Resolução de IP (em ordem de prioridade):
        1. NodeRegistry (descoberto via mDNS em runtime)
        2. config.NETWORK_NODES (estático / seed)

    Body JSON:
        {
            "command":  "speak",
            "text":     "...",
            "origin":   "seven",
            "secret":   "<API_SECRET>"        ← obrigatório para autenticação
        }

    Para operações privilegiadas (run, shutdown):
        Adicionar "admin_secret": "<ADMIN_SECRET>" no payload.

    Args:
        target_node: tipo do nó alvo ("seven" | "spark" | "mobile" | qualquer)
        command:     ação a executar no nó alvo
        payload:     campos adicionais no body JSON
        timeout:     timeout HTTP em segundos

    Returns:
        CommandResult com stdout = JSON da resposta.
    """
    if not _REQUESTS_OK:
        return CommandResult(success=False, returncode=-1,
                             error_msg="requests não instalado.")

    ip, port = _resolve_node_address(target_node)

    if not ip:
        msg = (
            f"IP de '{target_node}' não encontrado — "
            f"nó não descoberto via mDNS e sem IP estático em config.NETWORK_NODES."
        )
        logger.error(f"[NODE-CMD] {msg}")
        return CommandResult(success=False, returncode=-1, error_msg=msg)

    url  = f"http://{ip}:{port}/cmd"
    body = {
        "command": command,
        "origin":  config.NODE_TYPE,
        "secret":  config.API_SECRET,
        **(payload or {}),
    }

    logger.info(f"[NODE-CMD] → {target_node} ({ip}:{port}) | cmd={command!r}")

    try:
        resp = _requests.post(url, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[NODE-CMD] ← {target_node} | {resp.status_code}")
        return CommandResult(
            stdout=json.dumps(data, ensure_ascii=False),
            returncode=0, success=True,
        )
    except _requests.exceptions.ConnectTimeout:
        msg = f"Timeout conectando {target_node} ({ip}:{port})."
        logger.error(f"[NODE-CMD] {msg}")
        return CommandResult(success=False, returncode=-1, error_msg=msg)
    except _requests.exceptions.ConnectionError:
        msg = f"'{target_node}' ({ip}:{port}) inacessível."
        logger.error(f"[NODE-CMD] {msg}")
        return CommandResult(success=False, returncode=-1, error_msg=msg)
    except Exception as exc:
        logger.error(f"[NODE-CMD] {exc}", exc_info=True)
        return CommandResult(success=False, returncode=-1, error_msg=str(exc))


def broadcast_node_command(command: str, payload: Optional[dict] = None) -> dict[str, CommandResult]:
    """
    Envia o mesmo comando para TODOS os outros nós da rede em paralelo.

    Returns:
        Dict { node_type: CommandResult }
    """
    import concurrent.futures

    peers = config.get_peer_nodes()
    results: dict[str, CommandResult] = {}

    def _send(node_type: str) -> tuple[str, CommandResult]:
        return node_type, send_node_command(node_type, command, payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(peers)) as pool:
        futures = {pool.submit(_send, nt): nt for nt in peers}
        for future in concurrent.futures.as_completed(futures):
            try:
                node, result = future.result()
                results[node] = result
            except Exception as exc:
                node = futures[future]
                results[node] = CommandResult(success=False, returncode=-1, error_msg=str(exc))

    return results


# ---------------------------------------------------------------------------
# ★  TERMUX — comandos nativos do Android
# ---------------------------------------------------------------------------

def termux_speak(text: str) -> CommandResult:
    """Síntese de voz nativa do Termux (termux-tts-speak)."""
    return run_local(f'termux-tts-speak "{text}"', timeout=20)


def termux_vibrate(duration_ms: int = 500) -> CommandResult:
    """Vibração do celular via Termux API."""
    return run_local(f"termux-vibrate -d {duration_ms} -f")


def termux_notify(title: str, content: str, vibrate: bool = True) -> CommandResult:
    """Notificação push via Termux API."""
    vib = "--vibrate" if vibrate else ""
    return run_local(
        f'termux-notification --title "{title}" --content "{content}" {vib} --id k7core'
    )


def termux_torch(on: bool = True) -> CommandResult:
    """Controla a lanterna do celular."""
    state = "on" if on else "off"
    return run_local(f"termux-torch {state}")


# ---------------------------------------------------------------------------
# Sistema
# ---------------------------------------------------------------------------

def get_system_info() -> dict[str, str]:
    """Coleta métricas do sistema local."""
    def _q(cmd: str) -> str:
        return run_local(cmd).stdout or "N/A"

    info = {
        "node_type": config.NODE_TYPE,
        "hostname":  _q("hostname"),
        "platform":  _q("uname -s -r"),
    }

    if not config.IS_ANDROID:
        info.update({
            "uptime":       _q("uptime -p"),
            "cpu_percent":  _q("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'"),
            "mem_used":     _q("free -m | awk '/^Mem:/{print $3}'"),
            "mem_total":    _q("free -m | awk '/^Mem:/{print $2}'"),
            "disk_used":    _q("df -h / | awk 'NR==2{print $3}'"),
            "disk_total":   _q("df -h / | awk 'NR==2{print $2}'"),
            "disk_percent": _q("df -h / | awk 'NR==2{print $5}'"),
        })
    else:
        # No Android, comandos diferentes
        info.update({
            "uptime":      _q("uptime"),
            "mem_total":   _q("cat /proc/meminfo | grep MemTotal | awk '{print $2}'"),
            "mem_free":    _q("cat /proc/meminfo | grep MemAvailable | awk '{print $2}'"),
            "battery":     _q("termux-battery-status 2>/dev/null | python3 -c "
                              "\"import sys,json; d=json.load(sys.stdin); "
                              "print(d.get('percentage','?'),'%')\" 2>/dev/null || echo 'N/A'"),
        })

    return info
