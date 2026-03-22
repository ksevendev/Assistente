
# k7-core v2.0 — Assistente Virtual Distribuído

> Sistema de assistentes de voz em rede local com descoberta automática via mDNS,
> dashboard web em tempo real, auto-update via GitHub e terminal remoto integrado.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura de Arquivos](#3-estrutura-de-arquivos)
4. [Pré-requisitos](#4-pré-requisitos)
5. [Instalação](#5-instalação)
6. [Configuração](#6-configuração)
7. [Modos de Operação](#7-modos-de-operação)
8. [Dashboard Web](#8-dashboard-web)
9. [Auto-Update GitHub](#9-auto-update-github)
10. [Comandos de Voz](#10-comandos-de-voz)
11. [Terminal Remoto](#11-terminal-remoto)
12. [Criando Módulos de Comando](#12-criando-módulos-de-comando)
13. [API REST](#13-api-rest)
14. [Gestão de Usuários](#14-gestão-de-usuários)
15. [Wake-on-LAN](#15-wake-on-lan)
16. [Android / Termux](#16-android--termux)
17. [Segurança](#17-segurança)
18. [Solução de Problemas](#18-solução-de-problemas)
19. [Referência de Variáveis](#19-referência-de-variáveis)
20. [Changelog](#20-changelog)

---

## 1. Visão Geral

O **k7-core** é uma biblioteca Python que transforma qualquer máquina Linux ou Android
em um nó de um assistente virtual distribuído. Os nós se descobrem automaticamente
na rede local via mDNS (Zeroconf), se comunicam via API REST autenticada e são
controlados através de um dashboard web com métricas em tempo real.

### Instâncias padrão

| Nó | Dispositivo | Paleta | Papel padrão |
|---|---|---|---|
| **Seven** | Notebook (Debian 12) | 🔵 Ciano `#00E5FF` | Master — dashboard + voz |
| **Spark** | PC Desktop (Ubuntu) | 🟠 Laranja `#FF6D00` | Worker — SSH server + playerctl |
| **Mobile** | Android (Termux) | 🟣 Violeta `#AA00FF` | Worker — TTS nativo + notificações |

---

## 2. Arquitetura

```
                    REDE LOCAL Wi-Fi / Ethernet
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
       ┌────▼────┐       ┌────▼────┐      ┌────▼────┐
       │  SEVEN  │◄─────►│  SPARK  │◄────►│ MOBILE  │
       │ Master  │  API  │ Worker  │ API  │ Worker  │
       │  :2026  │       │  :2026  │      │  :2026  │
       │  mDNS   │       │  mDNS   │      │  mDNS   │
       └────┬────┘       └─────────┘      └─────────┘
            │
       ┌────▼────────────────────────┐
       │   Dashboard Web :2026       │
       │   /dashboard  (autenticado) │
       │   /api/*      (REST JSON)   │
       └─────────────────────────────┘

Descoberta automática: cada nó anuncia _k7core._tcp.local. via mDNS.
O Master descobre Workers sem IPs estáticos no config.py.
```

### Fluxo de inicialização

```
Assistant.__init__()
    └── CommandLoader      → carrega commands/*.py
    └── NodeRegistry       → seeds estáticos do config.py
    └── ZeroconfManager    → prepara ServiceInfo deste nó

Assistant.run()
    ├── ZeroconfManager.start()   → anuncia mDNS + inicia ServiceBrowser
    ├── sleep(DISCOVERY_BOOT_WAIT) → aguarda peers responderem
    ├── UpdateManager.start_scheduler() → timer periódico de update
    ├── Thread: _run_flask_server()
    │     ├── Master → _build_master_app() (dashboard + auth + /api/*)
    │     └── Worker → _build_worker_app() (headless, /cmd + /health)
    └── Loop de voz / modo texto / modo Android
```

---

## 3. Estrutura de Arquivos

```
k7-core/
│
├── config.py               # ★ Fonte única de verdade — edite aqui
├── core.py                 # Cérebro: Flask, mDNS, CommandLoader, loop de voz
├── engine.py               # Motor: subprocess local, SSH, WoL, API inter-nós
├── updater.py              # Auto-update via GitHub (credencial distribuída)
├── manage_auth.py          # CLI para gestão de usuários do dashboard
│
├── commands/               # Módulos de comando (hot-reload)
│   ├── __init__.py
│   └── default.py          # status, VSCode, música, WoL, avisar, lanterna
│
├── templates/              # Templates Jinja2 do dashboard
│   ├── dashboard.html      # Dashboard v2.0 — métricas, terminal, update
│   └── login.html          # Tela de autenticação
│
├── requirements.txt        # Dependências Python
├── setup.sh                # Instalação automatizada (Linux + Termux)
│
├── data/                   # Gerado em runtime (ignorar no git)
│   ├── k7auth.db           # SQLite — usuários e audit log
│   ├── update_history.json # Histórico de auto-updates
│   └── .update.lock        # File-lock de update concorrente
│
├── logs/                   # Gerado em runtime
│   └── seven.log           # Logs rotativos (2 MB × 3 arquivos)
│
└── tmp/                    # Gerado em runtime
    └── _tts.mp3            # Arquivo temporário do gTTS
```

### Arquivos gerados em runtime (não comitar)

```gitignore
data/
logs/
tmp/
.venv/
__pycache__/
*.pyc
```

---

## 4. Pré-requisitos

### Sistema operacional

- **Debian 12** (Bookworm) — testado em CLI e desktop
- **Ubuntu 24.04 LTS** — testado em CLI e desktop
- **Android** com [Termux](https://f-droid.org/packages/com.termux/) e
  [Termux:API](https://f-droid.org/packages/com.termux.api/) instalados

### Python

- **Python 3.10+** (verificado com `python3 --version`)

### Sistema (Linux)

```
git espeak espeak-ng portaudio19-dev libportaudio2
alsa-utils openssh-client playerctl ffmpeg build-essential
```

### Rede

- Todos os nós na **mesma rede local** (Wi-Fi ou Ethernet)
- Porta **2026 TCP** liberada no firewall de cada nó
- mDNS habilitado (padrão em redes domésticas)

---

## 5. Instalação

### Linux (Seven / Spark)

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USER/k7-core.git
cd k7-core

# 2. Execute o setup (instala dependências de sistema + venv Python)
chmod +x setup.sh && ./setup.sh

# 3. Ative o ambiente virtual
source .venv/bin/activate

# 4. Configure o nó (veja seção 6)
nano config.py

# 5. Inicie
python core.py
```

### Android (Termux / Mobile)

```bash
# No Termux:
pkg update && pkg install python git

# Clone
git clone https://github.com/SEU_USER/k7-core.git
cd k7-core

# Setup Termux (detectado automaticamente)
chmod +x setup.sh && ./setup.sh --termux

# Instale o app Termux:API pela F-Droid (necessário para TTS e vibração)

# Inicie (NODE_TYPE=mobile é setado automaticamente)
python core.py
```

### Verificar instalação

```bash
# Testa se o servidor sobe
python core.py &
sleep 2
curl http://localhost:2026/health | python3 -m json.tool
kill %1
```

---

## 6. Configuração

Todo o sistema é configurado em **um único arquivo**: `config.py`.

### 6.1 Identidade do nó

```python
# Altere para cada máquina onde o k7-core é instalado
NODE_TYPE:      str = "seven"    # "seven" | "spark" | "mobile"
ASSISTANT_NAME: str = "Seven"    # Nome falado pelo TTS
ASSISTANT_LANG: str = "pt-BR"   # Idioma do STT e espeak
```

### 6.2 Modo de operação

```python
NODE_MODE:        str  = "master"  # "master" → dashboard completo
                                   # "worker" → headless, só API
ENABLE_DASHBOARD: bool = True      # False = força modo worker
```

### 6.3 IPs da rede (opcional com mDNS)

Com mDNS funcionando, os IPs são descobertos automaticamente.
Preencha apenas como fallback ou para redes que bloqueiam mDNS:

```python
NETWORK_NODES: dict = {
    "seven": {
        "name":  "Seven",
        "ip":    "192.168.1.10",   # deixe "" para descoberta automática
        "port":  2026,
        "mac":   "AA:BB:CC:DD:EE:01",  # para Wake-on-LAN
        "type":  "desktop",
        "specs": "Notebook · Debian 12",
        "icon":  "laptop",
    },
    "spark": { ... },
    "mobile": { ... },
}
```

### 6.4 Segredos

```python
API_SECRET:   str = "mude-este-valor"   # mesmo em TODOS os nós
ADMIN_SECRET: str = "diferente-do-api"  # operações privilegiadas

FLASK_SECRET_KEY: str = "chave-aleatoria-longa"  # sessões web
```

> ⚠️ **Os três valores acima devem ser iguais em todos os nós da mesma rede.**

### 6.5 SSH

```python
SSH_USER: str = "seu_usuario_linux"
SSH_KEY:  str = os.path.expanduser("~/.ssh/id_rsa")
```

Distribuir a chave pública:

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa
ssh-copy-id usuario@192.168.1.11   # para o Spark
```

### 6.6 Credencial do GitHub (Auto-Update)

```bash
# Gere o blob Base64
python updater.py --gen-cred
# → Informe usuário, token e repo
# → Copie o resultado para config.py
```

```python
GH_CREDENTIAL: str = "SEU_BLOB_BASE64_AQUI"
ENABLE_AUTO_UPDATE:   bool = True
GH_BRANCH:            str  = "main"
GH_CHECK_INTERVAL:    int  = 3600   # segundos (0 = só manual)
GH_RESTART_ON_UPDATE: bool = True
```

---

## 7. Modos de Operação

### Master (padrão)

```python
NODE_MODE = "master"
ENABLE_DASHBOARD = True
```

Sobe:
- Dashboard completo em `/dashboard`
- Autenticação com SQLite
- Todas as rotas `/api/*`
- Buscador mDNS (descobre Workers)
- Scheduler de auto-update
- Loop de voz (se microfone disponível)

### Worker

```python
NODE_MODE = "worker"     # ou ENABLE_DASHBOARD = False
```

Sobe apenas:
- `GET /health` — health check público
- `POST /cmd`   — executa comandos (exige `API_SECRET`)
- Anúncio mDNS (é descoberto pelo Master)
- Loop de voz local (opcional)

### Android (automático)

Detectado via variáveis de ambiente do Termux. Força automaticamente:
```python
NODE_TYPE      = "mobile"
NODE_MODE      = "worker"
ENABLE_DASHBOARD = False
VOICE_ENGINE   = "termux"
```

---

## 8. Dashboard Web

### Acesso

```
http://SEU_IP:2026/dashboard
```

**Credenciais padrão:** `mestre` / `k7mestre`
(altere imediatamente pelo painel ou `python manage_auth.py create-user`)

### Abas

#### Nós da Rede
- Cards dinâmicos para cada nó (estático + descoberto via mDNS)
- Status Online/Offline em tempo real
- Métricas: Uptime, CPU%, RAM%
- **Sparklines SVG** — gráfico dos últimos 60 segundos (polling 5s)
- Botões: Ligar (WoL), Desligar (shutdown), Falar (TTS), Terminal
- Botão ℹ️ abre o **Drawer de Informações** lateral

#### Métricas
- Visão geral da rede (nós, online, CPU e RAM médias)
- Sparklines por nó — CPU histórico lado a lado

#### Update
- Repositório, branch e commits (local vs remoto)
- Botão **Verificar** — consulta API GitHub sem aplicar
- Botão **Aplicar** — fetch + reset + reinício opcional
- Tabela de histórico dos últimos 20 updates

#### Broadcast
- Campo para enviar mensagem TTS para todos os nós de uma vez
- Grid de envio individual por nó

### Drawer de Informações (por nó)

Clique em ℹ️ em qualquer card para abrir:
- Identificação completa (tipo, IP, porta, MAC, modo)
- Sparklines de CPU e RAM exclusivos (atualizados ao vivo)
- Grid de sistema (CPU%, RAM com MB, uptime, comandos ativos, bateria, disco)
- Atalhos de ação diretos

---

## 9. Auto-Update GitHub

### Como funciona

```
1. Consulta SHA do último commit via API REST do GitHub (sem git fetch)
2. Compara com o SHA do HEAD local
3. Se diferente: git fetch <URL autenticada> + git reset --hard FETCH_HEAD
4. Salva resultado em data/update_history.json
5. Se GH_RESTART_ON_UPDATE=True: os.execv() reinicia o processo
```

### Uso via CLI

```bash
# Gerar credencial Base64
python updater.py --gen-cred

# Verificar sem aplicar
python updater.py --check

# Aplicar se houver update
python updater.py --apply

# Forçar aplicação (ignora file-lock)
python updater.py --apply --force

# Ver histórico e status
python updater.py --status
```

### Uso via Dashboard

Acesse a aba **Update** → botões *Verificar* e *Aplicar*.

### Segurança da credencial

O blob `GH_CREDENTIAL` em `config.py` é Base64 puro de `"usuario:token:owner/repo"`.
A decodificação e separação dos três campos ocorre **exclusivamente** em `updater.py`,
em três funções propositalmente distribuídas em regiões diferentes do arquivo:

- `_gh_identity()` → linha ~63 → campo `[0]` (usuário)
- `_gh_secret()`   → linha ~101 → campo `[1]` (token)
- `_gh_target()`   → linha ~160 → campo `[2]` (owner/repo)

O token **nunca aparece em logs** — `_redact()` mascara antes de qualquer saída.

---

## 10. Comandos de Voz

O assistente responde apenas a falas que começam com o seu nome.
Exemplo: **"Seven, status do sistema"**

| Fala | Ação |
|------|------|
| `Seven, status` | CPU, RAM, disco e uptime deste nó |
| `Seven, abrir vscode` | Abre VS Code no PC remoto via SSH |
| `Seven, música` / `pausar` / `próxima` / `anterior` | playerctl via SSH no Spark |
| `Seven, ligar desktop` | Magic Packet Wake-on-LAN |
| `Seven, verificar spark` | Checa se o nó Spark está online |
| `Seven, verificar rede` | Verifica todos os nós |
| `Seven, avisar Spark: mensagem` | TTS no nó Spark |
| `Seven, avisar Mobile que chegou café` | TTS + vibração + notificação no celular |
| `Seven, avisar todos: reunião em 5min` | Broadcast para todos os nós |
| `Seven, ligar lanterna do celular` | `termux-torch on` via API |
| `Seven, recarregar módulos` | Hot-reload dos commands/*.py |
| `Seven, encerrar` / `tchau` | Desliga o assistente |

### Gatilho de hot-reload

Adicione ou modifique qualquer arquivo em `commands/` e diga
**"Seven, recarregar módulos"** — nenhum reinício necessário.

---

## 11. Terminal Remoto

O terminal embutido no dashboard suporta:

| Atalho / Comportamento | Descrição |
|---|---|
| `Enter` | Executa o comando no nó selecionado |
| `↑ / ↓` | Navega pelo histórico de comandos (comportamento bash) |
| `Ctrl+C` | Cancela o input atual (mostra `^C` no terminal) |
| `Ctrl+L` | Limpa a tela do terminal |
| `clear` | Limpa (comando built-in, sem round-trip) |
| `exit` | Fecha o painel do terminal |
| `help` | Lista atalhos disponíveis |
| Botão 🧹 | Limpa o output |
| Botão 📋 | Copia todo o output para a área de transferência |
| Coloração | Verde = sucesso, vermelho = erro, amarelo = warning, azul = info |

**Operações privilegiadas** (run, shutdown) exigem `ADMIN_SECRET` no payload —
o dashboard os envia automaticamente quando autenticado.

---

## 12. Criando Módulos de Comando

Crie `commands/meu_modulo.py`:

```python
# commands/meu_modulo.py
from __future__ import annotations
from typing import Callable
import engine, config

DESCRIPTION = "Meu módulo de exemplo"

def cmd_hello(text: str, speak: Callable) -> None:
    """Responde com uma saudação."""
    speak(f"Olá! Você disse: {text}")

def cmd_ping_spark(text: str, speak: Callable) -> None:
    """Verifica se o Spark está online."""
    ip = config.NETWORK_NODES.get("spark", {}).get("ip", "")
    if ip and engine.is_host_reachable(ip, port=2026):
        speak("Spark está online.")
    else:
        speak("Spark não está respondendo.")

def cmd_executar_remoto(text: str, speak: Callable) -> None:
    """Executa uptime no Spark via API."""
    result = engine.send_node_command("spark", "run", {"shell": "uptime -p"})
    speak(result.stdout[:200] if result else "Falha na execução remota.")

# Obrigatório — mapeamento gatilho (lowercase) → handler
COMMANDS: dict = {
    "olá":              cmd_hello,
    "oi":               cmd_hello,
    "ping spark":       cmd_ping_spark,
    "executar remoto":  cmd_executar_remoto,
}
```

Ative sem reiniciar: **"Seven, recarregar módulos"**

### Protocolo do módulo

| Elemento | Obrigatório | Descrição |
|---|---|---|
| `DESCRIPTION: str` | Não | Aparece nos logs ao carregar |
| `COMMANDS: dict` | **Sim** | Mapeamento `"gatilho" → função` |
| Assinatura do handler | **Sim** | `def fn(text: str, speak: Callable) -> None` |

- Gatilhos são **case-insensitive** (convertidos para lowercase internamente)
- Gatilhos mais longos têm **prioridade** sobre mais curtos
- O `text` recebido é a fala completa **sem o nome do assistente**
- A função `speak` é injetada pelo core — use-a para qualquer TTS

---

## 13. API REST

Porta padrão: **2026**. Autenticação: sessão web ou `"secret"` no body JSON.

### Rotas públicas

```
GET  /health         → status do nó (sem autenticação)
GET  /login          → formulário de login
POST /login          → autentica e cria sessão
GET  /logout         → encerra sessão
```

### Rotas do dashboard (requer login)

```
GET  /dashboard               → painel HTML
GET  /api/config              → topologia e paletas (JSON)
GET  /api/nodes               → status de todos os nós (polling)
GET  /api/update/status       → estado do auto-update
GET  /api/update/check        → verifica commit remoto (sem aplicar)
POST /api/update/apply        → aplica update imediato
POST /api/wake   { node }     → Wake-on-LAN
POST /api/shutdown { node }   → envia shutdown ao nó
POST /api/speak  { node, text } → TTS no nó
POST /api/terminal { node, cmd } → executa shell no nó
POST /api/reload              → hot-reload dos módulos
POST /change-password         → altera senha do usuário
```

### Rota inter-nós (aceita `secret` ou sessão)

```
POST /cmd  { command, text, origin, secret }
```

#### Comandos suportados em `/cmd`

| `"command"` | Parâmetros extras | Efeito |
|---|---|---|
| `"speak"` | `"text": "..."` | TTS no nó receptor |
| `"vibrate"` | `"duration": 500` | Vibração (Android only) |
| `"notify"` | `"title": "..."`, `"text": "..."` | Notificação push |
| `"torch"` | `"state": "on"\|"off"` | Lanterna (Android only) |
| `"run"` | `"shell": "..."`, `"admin_secret": "..."` | Executa shell |
| `"status"` | — | Retorna info do sistema |
| `"reload"` | — | Hot-reload dos módulos |

#### Exemplo curl

```bash
# Faz o Spark falar
curl -X POST http://192.168.1.11:2026/cmd \
  -H "Content-Type: application/json" \
  -d '{
    "command": "speak",
    "text":    "Olá do terminal!",
    "origin":  "terminal",
    "secret":  "k7-secret-local-network"
  }'

# Executa comando no Spark (exige admin_secret)
curl -X POST http://192.168.1.11:2026/cmd \
  -H "Content-Type: application/json" \
  -d '{
    "command":      "run",
    "shell":        "uptime",
    "origin":       "seven",
    "secret":       "k7-secret-local-network",
    "admin_secret": "k7-admin-secret-change-this"
  }'

# Health check
curl http://192.168.1.10:2026/health | python3 -m json.tool
```

---

## 14. Gestão de Usuários

```bash
# Criar usuário
python manage_auth.py create-user

# Listar usuários
python manage_auth.py list-users

# Redefinir senha
python manage_auth.py reset-password mestre

# Remover usuário
python manage_auth.py delete-user usuario_antigo

# Ver audit log (últimas 50 ações)
python manage_auth.py audit
```

O banco SQLite é criado automaticamente em `data/k7auth.db` na primeira inicialização
com o usuário padrão `mestre` / `k7mestre`. **Altere a senha imediatamente.**

---

## 15. Wake-on-LAN

Configure o MAC address em `config.py`:

```python
NETWORK_NODES = {
    "spark": {
        "mac": "AA:BB:CC:DD:EE:02",  # MAC da placa de rede
        ...
    }
}
```

Habilite WoL na placa de rede do PC alvo:

```bash
# No PC Spark (Debian/Ubuntu):
sudo apt install ethtool
sudo ethtool -s enp3s0 wol g         # substitua enp3s0 pela sua interface
sudo ethtool enp3s0 | grep Wake-on   # deve mostrar: Wake-on: g

# Para persistir após reboot (systemd):
sudo tee /etc/systemd/system/wol.service > /dev/null << 'EOF'
[Unit]
Description=Wake-on-LAN
After=network.target

[Service]
ExecStart=/usr/bin/ethtool -s enp3s0 wol g
Type=oneshot

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now wol.service
```

Habilite também na **BIOS/UEFI** do PC (seção Power Management → Wake-on-LAN).

Por voz: **"Seven, ligar Spark"**
Via dashboard: botão **⚡ Ligar** no card do nó.

---

## 16. Android / Termux

### Instalação completa

```bash
# No Termux
pkg update -y
pkg install -y python git

# Clone
git clone https://github.com/SEU_USER/k7-core.git && cd k7-core

# Setup
chmod +x setup.sh && ./setup.sh --termux

# Instale Termux:API pela F-Droid
# (necessário para TTS, vibração, notificações, lanterna)

# Inicie
python core.py
```

### Capabilities do Mobile

| Recurso | Comando Termux | Acesso via API |
|---|---|---|
| Fala (TTS) | `termux-tts-speak` | `POST /cmd` → `"speak"` |
| Vibração | `termux-vibrate -d 500` | `POST /cmd` → `"vibrate"` |
| Notificação | `termux-notification` | `POST /cmd` → `"notify"` |
| Lanterna | `termux-torch on/off` | `POST /cmd` → `"torch"` |
| Bateria | `termux-battery-status` | `GET /health` → `system.battery` |

### Manter rodando em background (Termux)

```bash
# Opção 1: tmux
pkg install tmux
tmux new-session -d -s k7 "python core.py"
tmux attach -t k7

# Opção 2: nohup
nohup python core.py > logs/seven.log 2>&1 &
```

### Acessar o Dashboard pelo Chrome Android

```
http://IP_DO_SEVEN:2026/dashboard
```

O dashboard é responsivo e otimizado para Chrome no Android —
todas as funcionalidades funcionam no mobile incluindo terminal e broadcast.

---

## 17. Segurança

### Camadas de autenticação

| Camada | Mecanismo | Onde |
|---|---|---|
| Dashboard web | Sessão Flask + senha hasheada (pbkdf2:sha256) | SQLite `k7auth.db` |
| API inter-nós | `API_SECRET` no body JSON | Todas as rotas `/cmd` |
| Operações root | `ADMIN_SECRET` adicional | `run`, `shutdown` via `/cmd` |
| mDNS filtering | SHA-256 fingerprint do `API_SECRET` | ZeroconfManager |
| Auto-update | Token GitHub via Base64 distribuído | updater.py |

### Boas práticas

```python
# config.py — altere todos os três valores
API_SECRET:       str = "gere-um-uuid-aleatorio-aqui"
ADMIN_SECRET:     str = "outro-uuid-diferente-do-api"
FLASK_SECRET_KEY: str = "string-de-32-chars-aleatoria"
```

Gerar valores seguros:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### O que NÃO está protegido

- `GET /health` é **público** (necessário para o mDNS health check entre Masters)
- A rede local é considerada confiável — não exponha a porta 2026 na internet
- Use VPN (WireGuard, Tailscale) se precisar de acesso remoto externo

### Audit log

Todas as ações do dashboard são registradas em `data/k7auth.db` (tabela `audit_log`):
login, logout, comandos executados, updates aplicados, senha alterada.

```bash
python manage_auth.py audit
```

---

## 18. Solução de Problemas

### Nó não aparece no dashboard

```bash
# 1. Verifique se o outro nó está rodando
curl http://IP_DO_NO:2026/health

# 2. Verifique se mDNS está funcionando
python3 -c "
from zeroconf import Zeroconf, ServiceBrowser
import time
zc = Zeroconf()
class L:
    def add_service(self, zc, type, name): print('Encontrado:', name)
    def remove_service(self, *a): pass
    def update_service(self, *a): pass
b = ServiceBrowser(zc, '_k7core._tcp.local.', L())
time.sleep(5); zc.close()
"

# 3. Verifique firewall
sudo ufw status
sudo ufw allow 2026/tcp    # se necessário
sudo ufw allow 5353/udp    # mDNS
```

### Falha no STT (reconhecimento de voz)

```bash
# Testa microfone
python3 -c "
import speech_recognition as sr
r = sr.Recognizer()
with sr.Microphone() as s:
    print('Fale algo...')
    audio = r.listen(s, timeout=5)
    print(r.recognize_google(audio, language='pt-BR'))
"

# Ajustar energia do microfone em config.py
MIC_ENERGY_THRESHOLD: int = 300   # diminuir se não captura
```

### Falha no TTS (espeak)

```bash
espeak-ng -v pt "teste de voz"           # testa espeak-ng
espeak -v pt "teste de voz"              # fallback espeak
aplay /dev/null                          # testa ALSA
pulseaudio --start                       # inicia PulseAudio se necessário
```

### Auto-update falha com 401

```bash
# Verifique se o token ainda é válido
python3 -c "
import base64, config
raw = base64.b64decode(config.GH_CREDENTIAL).decode()
user, token, repo = raw.split(':', 2)
print(f'user={user}, repo={repo}, token={token[:8]}...')
"

# Regere a credencial
python updater.py --gen-cred
```

### Port 2026 já em uso

```bash
lsof -i :2026              # quem está usando
kill -9 PID_DO_PROCESSO    # mata o processo
# ou altere API_PORT em config.py
```

### SQLite — banco corrompido

```bash
rm data/k7auth.db          # remove o banco
python core.py             # recria com usuário padrão na inicialização
python manage_auth.py create-user  # cria seu usuário
```

---

## 19. Referência de Variáveis

### config.py — variáveis principais

| Variável | Tipo | Padrão | Descrição |
|---|---|---|---|
| `NODE_TYPE` | `str` | `"seven"` | Tipo do nó: `seven`, `spark`, `mobile` |
| `ASSISTANT_NAME` | `str` | `"Seven"` | Nome falado e exibido |
| `ASSISTANT_LANG` | `str` | `"pt-BR"` | Idioma STT e espeak |
| `NODE_MODE` | `str` | `"master"` | `"master"` ou `"worker"` |
| `ENABLE_DASHBOARD` | `bool` | `True` | False = headless (Worker) |
| `API_PORT` | `int` | `2026` | Porta HTTP de todos os nós |
| `API_SECRET` | `str` | — | Token inter-nós (igual em todos) |
| `ADMIN_SECRET` | `str` | — | Token para operações root |
| `FLASK_SECRET_KEY` | `str` | — | Chave de sessão web |
| `GH_CREDENTIAL` | `str` | — | Base64 de `user:token:owner/repo` |
| `ENABLE_AUTO_UPDATE` | `bool` | `True` | Liga/desliga auto-update |
| `GH_BRANCH` | `str` | `"main"` | Branch do repositório |
| `GH_CHECK_INTERVAL` | `int` | `3600` | Segundos entre verificações (0=manual) |
| `GH_RESTART_ON_UPDATE` | `bool` | `True` | Reinicia após update |
| `VOICE_ENGINE` | `str` | `"espeak"` | `"espeak"`, `"gtts"` ou `"termux"` |
| `SSH_USER` | `str` | `"usuario"` | Usuário SSH nos nós remotos |
| `SSH_KEY` | `str` | `~/.ssh/id_rsa` | Chave RSA privada |
| `DISCOVERY_BOOT_WAIT` | `float` | `2.0` | Segundos aguardando mDNS no boot |
| `DISCOVERY_SERVICE_TYPE` | `str` | `"_k7core._tcp.local."` | Tipo mDNS |
| `MIC_ENERGY_THRESHOLD` | `int` | `400` | Sensibilidade do microfone |
| `MIC_TIMEOUT` | `float` | `5.0` | Timeout de escuta (segundos) |
| `LOG_LEVEL` | `str` | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### NETWORK_NODES — campos por nó

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | `str` | Nome de exibição |
| `ip` | `str` | IP na rede local (vazio = mDNS automático) |
| `port` | `int` | Porta da API (padrão 2026) |
| `mac` | `str` | MAC para Wake-on-LAN (vazio = sem WoL) |
| `type` | `str` | `"desktop"` ou `"mobile"` |
| `specs` | `str` | Texto livre exibido no card |
| `icon` | `str` | Nome do ícone Material Icons |

---

## 20. Changelog

### v2.0 (atual)

- **Dashboard v2.0** — quatro abas com tab-router client-side
- **Sparklines SVG** em tempo real (CPU e RAM, janela de 60s, polling 5s)
- **Terminal robusto** — histórico ↑↓, Ctrl+C, Ctrl+L, coloração semântica, copy
- **Drawer de informações** — painel lateral por nó com métricas exclusivas
- **Aba Métricas** — visão consolidada da rede, sparklines por nó
- **Aba Update** — controle total do auto-update com histórico e progress bar
- **Aba Broadcast** — broadcast global e envio individual por nó
- **Auto-update GitHub** — credencial Base64 com decode distribuído em updater.py
- **mDNS discovery** — nós se encontram automaticamente via Zeroconf
- **NodeRegistry** — registro em memória com merge estático + dinâmico
- **Master/Worker split** — Flask carrega rotas diferentes por modo
- **Porta 2026** — alterada de 7007

### v1.x (histórico)

- v1.3 — Dashboard básico com cards e terminal inline
- v1.2 — Autenticação SQLite com Flask-Login
- v1.1 — API inter-nós com secret validation
- v1.0 — Assistente de voz local com CommandLoader e hot-reload

---

## Licença

Uso pessoal e privado. Não distribua sem autorização.

---

*k7-core v2.0 — construído iterativamente como sistema de automação doméstica pessoal.*
