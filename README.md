# k7-core v3 — Rede de Assistentes Distribuídos

Sistema de assistentes virtuais em rede local com três instâncias que se comunicam via HTTP.

---

## Arquitetura de Nós

```
                    REDE LOCAL (192.168.1.x)
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐       ┌────▼────┐      ┌────▼────┐
    │  SEVEN  │◄─────►│  SPARK  │◄────►│ MOBILE  │
    │ Notebook│  API  │  PC/DT  │ API  │ Android │
    │  :7007  │       │  :7007  │      │  :7007  │
    │  CIANO  │       │LARANJA  │      │VIOLETA  │
    └─────────┘       └─────────┘      └─────────┘
         │                 │                 │
    Microfone          Microfone         Termux TTS
    espeak/gTTS        espeak/gTTS       Notificações
    SSH client         SSH client        Vibração
    WoL sender         WoL sender        Lanterna
```

---

## Estrutura de Arquivos

```
k7-core/
├── core.py           ← Cérebro: loop de voz, API Flask, CommandLoader
├── config.py         ← Identidade do nó, paletas, mapa de rede
├── engine.py         ← subprocess, SSH, WoL, send_node_command(), Termux
├── requirements.txt
├── setup.sh          ← Instalação (Linux) e Termux (--termux)
├── run_seven.sh      ← Inicia como nó Seven
├── run_spark.sh      ← Inicia como nó Spark
└── commands/
    ├── __init__.py
    └── default.py    ← status, VSCode, música, WoL, avisar, lanterna
```

---

## Instalação

### Linux (Seven / Spark)
```bash
chmod +x setup.sh && ./setup.sh
# Edite config.py com os IPs reais
./run_seven.sh   # ou ./run_spark.sh
```

### Android (Termux / Mobile)
```bash
# No Termux:
pkg install python
chmod +x setup.sh && ./setup.sh --termux
# Edite config.py: NODE_TYPE = "mobile"
python core.py
```

---

## Configuração — config.py

```python
# Defina o tipo deste nó antes de iniciar
NODE_TYPE: str = "seven"   # "seven" | "spark" | "mobile"

# IPs reais de cada dispositivo na rede
NETWORK_NODES: dict = {
    "seven":  {"name": "Seven",  "ip": "192.168.1.10", "port": 7007, ...},
    "spark":  {"name": "Spark",  "ip": "192.168.1.11", "port": 7007, ...},
    "mobile": {"name": "Mobile", "ip": "192.168.1.12", "port": 7007, ...},
}

# Token de autenticação da API (deve ser igual em todos os nós)
API_SECRET: str = "k7-secret-local-network"
```

---

## API REST — Porta 7007

### Health Check
```bash
curl http://192.168.1.10:7007/health
```

### Enviar Comando
```bash
curl -X POST http://192.168.1.10:7007/cmd \
  -H "Content-Type: application/json" \
  -d '{
    "command": "speak",
    "text":    "Olá do terminal!",
    "origin":  "terminal",
    "secret":  "k7-secret-local-network"
  }'
```

### Comandos disponíveis na API (`"command"`)

| command    | Parâmetros         | Efeito                              |
|------------|--------------------|-------------------------------------|
| `speak`    | `text`             | TTS no nó receptor                  |
| `vibrate`  | `duration` (ms)    | Vibra o celular (Android only)      |
| `notify`   | `title`, `text`    | Notificação push (Android/console)  |
| `torch`    | `state` (on/off)   | Controla lanterna (Android only)    |
| `run`      | `shell`            | Executa comando shell               |
| `status`   | —                  | Retorna info do sistema             |
| `reload`   | —                  | Hot-reload dos módulos de comando   |
| `<gatilho>`| `text`             | Executa qualquer gatilho registrado |

---

## Comandos de Voz

| Fala                                        | Ação                              |
|---------------------------------------------|-----------------------------------|
| Seven, status                               | CPU/RAM/disco deste nó            |
| Seven, avisar Spark: o build terminou       | TTS no PC Spark                   |
| Seven, avisar Mobile que tem café           | TTS + vibração + notificação      |
| Seven, avisar todos: reunião em 5 minutos   | Broadcast para todos os nós       |
| Seven, abrir vscode no Spark                | Abre VS Code via API/SSH          |
| Seven, pausar / próxima / anterior          | playerctl via SSH no Spark        |
| Seven, ligar Spark                          | Wake-on-LAN                       |
| Seven, verificar rede                       | Checa todos os nós                |
| Seven, ligar lanterna do celular            | Termux torch via API              |
| Seven, recarregar módulos                   | Hot-reload imediato               |

---

## Criar Novo Módulo de Comando

```python
# commands/meu_modulo.py
DESCRIPTION = "Meu módulo"

def cmd_exemplo(text: str, speak) -> None:
    import engine, config
    # Acessa outros nós
    engine.send_node_command("spark", "speak", {"text": "Comando recebido!"})
    speak("Feito!")

COMMANDS = {
    "meu comando": cmd_exemplo,
}
```

Diga **"Seven, recarregar módulos"** — ativo imediatamente.
