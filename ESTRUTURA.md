# k7-core v2.0 — Estrutura Completa de Arquivos

> Mapa de referência de cada arquivo, classe, função e variável do projeto.

---

## Árvore de Diretórios

```
k7-core/
│
├── config.py                   # Fonte única de verdade — configuração global
├── core.py                     # Cérebro — Flask, mDNS, CommandLoader, voz
├── engine.py                   # Motor — subprocess, SSH, WoL, API inter-nós
├── updater.py                  # Auto-update — GitHub + credencial distribuída
├── manage_auth.py              # CLI — gestão de usuários do dashboard
│
├── commands/                   # Módulos de comando (hot-reload sem reinício)
│   ├── __init__.py             # Pacote Python (arquivo vazio)
│   └── default.py             # Comandos padrão do assistente
│
├── templates/                  # Templates Jinja2 (Flask)
│   ├── dashboard.html          # Dashboard v2.0 completo
│   └── login.html              # Tela de login
│
├── requirements.txt            # Dependências Python com versões mínimas
├── setup.sh                   # Instalação automatizada Linux + Termux
│
├── data/                      # ← gerado em runtime (não comitar)
│   ├── k7auth.db              # SQLite: tabelas users + audit_log
│   ├── update_history.json    # Histórico JSON de auto-updates (máx 50)
│   └── .update.lock           # File-lock PID para updates concorrentes
│
├── logs/                      # ← gerado em runtime
│   └── {node_type}.log        # Log rotativo 2 MB × 3 arquivos
│
└── tmp/                       # ← gerado em runtime
    └── _tts.mp3               # Arquivo temporário do gTTS
```

---

## config.py

Importado por todos os outros módulos. Não contém lógica de negócio —
apenas variáveis e funções puras de leitura.

### Seções e variáveis

```
❶ IDENTIDADE DO NÓ
   NODE_TYPE           str   "seven"|"spark"|"mobile"  — tipo lógico deste nó
   ASSISTANT_NAME      str   Nome falado e exibido no dashboard
   ASSISTANT_LANG      str   Idioma STT ("pt-BR", "en-US", ...)

❷ MODO DE OPERAÇÃO
   NODE_MODE           str   "master"|"worker"
   ENABLE_DASHBOARD    bool  False = força modo headless (Worker)
   is_master()         fn    → True se ENABLE_DASHBOARD and NODE_MODE=="master"
   is_worker()         fn    → not is_master()

❸ DESCOBERTA mDNS
   DISCOVERY_SERVICE_TYPE    str   "_k7core._tcp.local."
   DISCOVERY_NODE_NAME       str   Vazio = usa "k7-{NODE_TYPE}"
   DISCOVERY_TTL             int   60 segundos
   DISCOVERY_BOOT_WAIT       float Segundos aguardando peers no boot
   DISCOVERY_RECHECK_INTERVAL int  Segundos entre re-verificações
   get_discovery_name()      fn    → "k7-seven._k7core._tcp.local."

❹ API SERVER
   API_HOST            str   "0.0.0.0" (todas as interfaces)
   API_PORT            int   2026
   API_SECRET          str   Token inter-nós (igual em todos os nós)
   ADMIN_SECRET        str   Token para operações privilegiadas (run, shutdown)

❺ PALETAS DE COR
   NODE_PALETTES       dict  {node_type: {label, ansi_primary, ansi_secondary,
                              hex_primary, hex_secondary, hex_bg, hex_glow}}
   get_palette(nt?)    fn    → dict da paleta (fallback: "default")

❻ TOPOLOGIA ESTÁTICA
   NETWORK_NODES       dict  {node_type: {name, ip, port, mac, type, specs, icon}}
   get_node_info(nt?)  fn    → dict do nó (padrão: NODE_TYPE)
   get_peer_nodes()    fn    → NETWORK_NODES sem o nó atual
   get_nodes_with_palette() fn → lista fundindo NETWORK_NODES + NODE_PALETTES

❼ AUTENTICAÇÃO
   AUTH_DB_PATH        str   Resolvido após BASE_DIR (data/k7auth.db)
   FLASK_SECRET_KEY    str   Chave de sessão Flask
   DEFAULT_USER        str   "mestre"
   DEFAULT_PASSWORD    str   "k7mestre" (altere imediatamente)
   SESSION_LIFETIME    int   3600 * 8 segundos

❽ AUTO-UPDATE
   GH_CREDENTIAL       str   Base64 de "usuario:token:owner/repo" (blob opaco)
   ENABLE_AUTO_UPDATE  bool  Liga/desliga o sistema de update
   GH_BRANCH           str   Branch alvo ("main")
   GH_CHECK_INTERVAL   int   Segundos entre verificações (0 = só manual)
   GH_RESTART_ON_UPDATE bool Reinicia o processo após update bem-sucedido
   GH_LOCK_FILE        str   Resolvido após BASE_DIR (data/.update.lock)

❾ VOZ / TTS
   VOICE_ENGINE        str   "espeak"|"gtts"|"termux"
   ESPEAK_VOICE        str   "pt" (código de voz)
   ESPEAK_SPEED        int   150 palavras por minuto
   ESPEAK_VOLUME       int   180 (0-200)

❿ SSH
   SSH_USER            str   Usuário nos nós remotos
   SSH_KEY             str   Caminho da chave RSA privada
   SSH_TIMEOUT         int   10 segundos
   SSH_PORT            int   22
   PC_IP               str   Alias: IP do nó Spark (legacy)
   PC_MAC              str   Alias: MAC do nó Spark (legacy)
   REMOTE_PCS          dict  {alias: (ip, mac)} — gerado de NETWORK_NODES

⓫ WAKE-ON-LAN
   WOL_PORT            int   9 (UDP padrão)
   WOL_BROADCAST       str   "255.255.255.255"

⓬ RECONHECIMENTO DE VOZ
   MIC_ENERGY_THRESHOLD  int   400 (sensibilidade)
   MIC_TIMEOUT           float 5.0 s (espera início da fala)
   MIC_PHRASE_TIME_LIMIT float 12.0 s (duração máxima da frase)
   MIC_PAUSE_THRESHOLD   float 0.9 s (silêncio = fim da frase)

⓭ DETECÇÃO DE AMBIENTE
   is_android()        fn    → True se variáveis Termux presentes
   is_headless()       fn    → True se sem DISPLAY/WAYLAND_DISPLAY
   IS_ANDROID          bool  Cache de is_android()
   IS_HEADLESS         bool  Cache de is_headless()

⓮ DIRETÓRIOS
   BASE_DIR            str   Diretório do config.py
   COMMANDS_DIR        str   BASE_DIR/commands
   TEMPLATES_DIR       str   BASE_DIR/templates
   LOG_DIR             str   BASE_DIR/logs
   TEMP_DIR            str   BASE_DIR/tmp
   DATA_DIR            str   BASE_DIR/data
   LOG_FILE            str   LOG_DIR/{NODE_TYPE}.log

⓯ LOGGING
   LOG_LEVEL           str   "INFO" (DEBUG|INFO|WARNING|ERROR)
   LOG_TO_FILE         bool  True
   LOG_TO_CONSOLE      bool  True
```

---

## core.py

Módulo principal. Importa `config`, `engine` e todos os módulos de `commands/`.

### Classes

```
_NodeFormatter(logging.Formatter)
   Formata logs com a cor ANSI da paleta do nó atual.
   LEVEL_COLORS: dict  Mapeamento nível → código ANSI

NodeRegistry
   Registro em memória de todos os nós conhecidos (thread-safe).
   
   __init__()              Carrega seeds do config.NETWORK_NODES
   get_all() → list        Todos os nós (thread-safe)
   get(nt) → dict|None     Nó pelo tipo
   resolve_ip(nt) → str    IP com prioridade: registry > config estático
   upsert(nt, data)        Adiciona/atualiza nó no registry
   remove(nt)              Remove nó (ficou offline)
   get_with_palette() → list  Funde dados do nó com paleta de cores
   _load_static()          Carrega seeds com IP preenchido do config

ZeroconfManager
   Gerencia anúncio mDNS e descoberta de peers.
   
   __init__(registry)
   start() → bool          Registra serviço + inicia ServiceBrowser
   stop()                  Cancela registro e para browser
   _service_name() → str   "k7-seven._k7core._tcp.local."
   _get_local_ip() → str   IP local que alcança a rede (UDP trick)
   _register_self()        Cria e registra ServiceInfo com TXT record
   _start_browser()        Inicia ServiceBrowser callback
   _on_service_state_change(...)  Callback: Added/Updated/Removed
   _on_node_discovered(name, info)  Adiciona nó ao NodeRegistry
   _on_node_removed(name)          Remove nó do NodeRegistry

User(UserMixin)
   Modelo Flask-Login.
   
   __init__(id_, username, role)
   get(user_id) → User|None        Busca por ID no SQLite
   get_by_username(u) → Row|None   Busca por username com password hash

CommandLoader
   Carrega dinamicamente arquivos .py de commands/.
   
   __init__(commands_dir)
   registry → dict         Cópia somente-leitura do registro
   reload()                Hot-reload: limpa sys.modules + recarrega tudo
   dispatch(text, speak_fn) → bool  Encontra e executa o gatilho mais específico
   _load_all()             Varre commands/*.py (exclui _*.py)
   _load_module(path) → tuple  Importa e registra um módulo

Assistant
   Gerencia o ciclo de vida completo do nó.
   
   __init__()
     Instancia: CommandLoader, NodeRegistry, ZeroconfManager
     Configura: sr.Recognizer (se STT disponível)
     
   run()
     1. ZeroconfManager.start()
     2. UpdateManager.start_scheduler()
     3. Thread: _run_flask_server() [daemon]
     4. Despacha para: _android_mode | _voice_loop | _text_loop
     
   _voice_loop()       Loop de escuta por microfone
   _text_loop()        Loop de entrada por teclado (fallback)
   _android_mode()     Aguarda comandos da rede (sem microfone)
   _process(raw)       Pipeline: verificar nome → extrair → executar
   _greet()            Frase de boas-vindas na inicialização
   _handle_internal(cmd) → bool  Gatilhos built-in (reload, exit)
   _EXIT_WORDS: set    {"encerrar", "desligar", "tchau", ...}
   _RELOAD_TRIGGER: str  "recarregar módulos"
```

### Funções de módulo

```
_setup_logging()        Configura handlers de log (console + arquivo rotativo)
_icon_for_node(nt) → str  Ícone Material para um tipo de nó

# SQLite / Auth
_db_connect() → Connection    Abre conexão com k7auth.db (row_factory=Row)
_db_init()                    Cria tabelas + usuário padrão (só no Master)
_audit(user, action, detail, ip)  Registra ação no audit_log

# TTS
speak(text)             Faz o nó falar (seleciona engine automaticamente)
_speak_espeak(text)     TTS via espeak-ng / espeak
_speak_termux(text)     TTS via termux-tts-speak
_speak_gtts(text)       TTS online via gTTS + pygame

# STT
listen(recognizer, mic) → str|None  Ouve microfone e retorna texto

# Flask
_handle_cmd_request(data, loader, registry) → tuple  Lógica compartilhada /cmd
_build_worker_app(loader, registry) → Flask     Headless: /cmd + /health
_build_master_app(loader, registry) → Flask     Completo: dashboard + /api/*
_run_flask_server(loader, registry)             Inicia Flask (thread daemon)
_send_to_node(nt, entry, cmd, extra) → CommandResult  HTTP POST /cmd

# Rotas do Master app (funções Flask decoradas com @login_required):
  login_page()          GET/POST /login
  logout_page()         GET /logout
  change_password()     POST /change-password
  dashboard()           GET /dashboard → render dashboard.html
  api_config()          GET /api/config → JSON topologia + paletas
  api_nodes()           GET /api/nodes → JSON status paralelo de todos os nós
  api_wake()            POST /api/wake → WoL
  api_shutdown()        POST /api/shutdown → shutdown via API
  api_speak()           POST /api/speak → TTS
  api_terminal()        POST /api/terminal → shell no nó
  api_reload()          POST /api/reload → hot-reload
  api_update_status()   GET /api/update/status → estado do updater
  api_update_check()    GET /api/update/check → verifica commit remoto
  api_update_apply()    POST /api/update/apply → aplica update (thread)
  health()              GET /health → JSON status público
  master_cmd()          POST /cmd → aceita secret ou sessão

# Singleton
_registry: NodeRegistry   Instância global do NodeRegistry
get_registry() → NodeRegistry   Acessor público (usado por engine.py)

# Entry point
main()   Instancia e executa Assistant
```

---

## engine.py

Motor de execução. Não inicia threads nem servidores — apenas executa comandos.

### Classe

```
CommandResult (dataclass)
   stdout:     str   Output do comando
   stderr:     str   Output de erro
   returncode: int   Código de retorno (0 = sucesso)
   success:    bool  True se returncode == 0
   error_msg:  str   Mensagem de erro legível
   __bool__()  → success
   __str__()   → stdout ou "[ERRO] error_msg"
```

### Funções

```
# Execução local
run_local(command, timeout=30, shell=True) → CommandResult
   Executa comando no sistema local via subprocess.run()

run_local_background(command) → Popen|None
   Inicia processo desacoplado (start_new_session=True), não bloqueia

# SSH
_get_ssh_client → removido (inline em run_ssh)
run_ssh(command, host=None, alias=None, timeout=30) → CommandResult
   SSH com chave RSA. Prioridade host: argumento > alias > config.PC_IP

is_host_reachable(host, port=None, timeout=2) → bool
   TCP handshake para verificar conectividade (sem autenticação)

# Wake-on-LAN
send_magic_packet(mac, broadcast=None, port=None) → bool
   Monta 102 bytes (0xFF×6 + MAC×16) e envia por UDP broadcast

wake_pc(alias=None, mac=None) → bool
   Resolve MAC pelo alias e chama send_magic_packet()

# API inter-nós
_resolve_node_address(nt) → tuple[str, int]
   Resolução de IP: NodeRegistry (mDNS) → config.NETWORK_NODES (estático)
   Importação lazy de core.get_registry() para evitar ciclo de importação

send_node_command(target_node, command, payload=None, timeout=8) → CommandResult
   POST /cmd no nó alvo com API_SECRET no body
   Usa _resolve_node_address() — funciona mesmo sem IP no config.py

broadcast_node_command(command, payload=None) → dict[str, CommandResult]
   Envia para todos os peers em paralelo via ThreadPoolExecutor

# Termux
termux_speak(text) → CommandResult     termux-tts-speak
termux_vibrate(ms=500) → CommandResult termux-vibrate -d {ms} -f
termux_notify(title, content, vibrate=True) → CommandResult
termux_torch(on=True) → CommandResult  termux-torch on|off

# Sistema
get_system_info() → dict[str, str]
   CPU, RAM, disco, uptime, hostname — adaptado para Android vs Linux
```

---

## updater.py

Auto-update via API REST do GitHub. Credencial distribuída em três funções isoladas.

### Funções de extração (intencionalmente separadas no arquivo)

```
_gh_identity() → str    # linha ~63  — campo [0]: usuário GitHub
   Decodifica Base64 de config.GH_CREDENTIAL, retorna parte antes do 1º ':'

_redact(value) → str    # entre as extrações
   Mascara para logs: "ghp_AbCd1234" → "ghp_Ab****4"

_gh_secret() → str      # linha ~101 — campo [1]: Personal Access Token
   Decodifica Base64, retorna parte entre 1º e 2º ':'

_gh_target() → str      # linha ~160 — campo [2]: owner/repositorio
   Decodifica Base64, retorna parte após o 2º ':'
```

### Classe

```
UpdateResult (dataclass)
   timestamp:     str   ISO 8601
   success:       bool
   had_update:    bool  True se havia commit novo
   old_commit:    str   SHA antes
   new_commit:    str   SHA depois
   branch:        str
   repo:          str
   message:       str   Mensagem de sucesso ou erro legível
   error:         str   Detalhe técnico do erro
   files_changed: list  Arquivos alterados no update
   __bool__() → success
   to_dict() → dict

UpdateManager
   Thread-safe via file-lock em config.GH_LOCK_FILE.
   
   __init__()
     Valida as três partes da credencial na inicialização (fail-fast)
     
   check_and_apply(force=False) → UpdateResult
     1. Verifica ENABLE_AUTO_UPDATE
     2. Adquire file-lock
     3. Chama _run_update()
     4. Libera lock + persiste histórico
     
   check_only() → dict
     Consulta SHA remoto via API sem modificar o repo local
     Retorna: {has_update, local_commit, remote_commit, branch, repo}
     
   status() → dict
     Commit atual + histórico + configuração
     
   start_scheduler()   Timer daemon que chama check_and_apply() periodicamente
   stop_scheduler()    Cancela o timer
   
   _run_update(result) → UpdateResult
     Compara SHAs → git fetch autenticado → diff → git reset --hard → restart
     
   _authenticated_url() → str
     Monta "https://user:token@github.com/owner/repo.git"
     Token descartado após montagem da string
     
   _git(args, safe_log=None) → str|None
     Executa "git {args}" no BASE_DIR com timeout 60s
     safe_log substitui args nos logs (oculta URLs com token)
     
   _sanitize(text) → str   Remove token de strings antes de logar
   _local_sha() → str      SHA do HEAD local
   _remote_sha() → str     SHA via API GitHub (não modifica repo local)
   _restart()              os.execv() com mesmo sys.argv
   _enqueue()              Agenda próxima verificação
   _tick()                 Executa check_and_apply() e reagenda
   _persist(result)        Salva em data/update_history.json (máx 50)
   _load_history() → list  Carrega histórico do JSON
   _acquire_lock(wait, timeout) → bool  File-lock com verificação de PID vivo
   _release_lock()         Remove arquivo de lock
```

### Funções de módulo

```
get_update_manager() → UpdateManager|None
   Singleton lazy. Retorna None se desabilitado ou credencial inválida.

generate_credential(user, token, repo) → str
   Gera Base64 para colar em config.GH_CREDENTIAL

_cli()   Entrypoint argparse: --gen-cred, --check, --apply, --force, --status
```

---

## manage_auth.py

CLI para gestão de usuários. Executa no mesmo diretório do projeto.

```
_db() → Connection         Abre k7auth.db com row_factory
_ensure_tables()           CREATE TABLE IF NOT EXISTS users + audit_log

cmd_create_user(args)      Cria novo usuário com senha hasheada (getpass)
cmd_list_users(args)       Lista id, username, role, created
cmd_reset_password(args)   Redefine senha de um usuário existente
cmd_delete_user(args)      Remove usuário (pede confirmação)
cmd_audit(args)            Últimas 50 entradas do audit_log

CLI: create-user | list-users | reset-password USERNAME | delete-user USERNAME | audit
```

---

## commands/default.py

Módulo de comandos padrão. Carregado automaticamente pelo CommandLoader.

### Funções (handlers)

```
cmd_status(text, speak)          Status CPU/RAM/disco local (ou bateria no Android)
cmd_abrir_vscode(text, speak)    Abre VS Code no Spark via API ou SSH
cmd_musica(text, speak)          Controla playerctl no Spark via SSH (play/pause/next/prev)
cmd_acordar_pc(text, speak)      Wake-on-LAN + verifica se ficou online após 8s
cmd_verificar(text, speak)       Checa conectividade de um ou todos os nós
cmd_avisar(text, speak)          TTS em outro nó + vibração/notificação se Mobile
cmd_avisar_todos(text, speak)    Broadcast para todos os peers via broadcast_node_command()
cmd_lanterna(text, speak)        termux-torch via API no Mobile
cmd_ajuda(text, speak)           Lista comandos disponíveis

_detect_alias_or_node(text) → str|None   Detecta alias em REMOTE_PCS ou NETWORK_NODES
```

### COMMANDS (dict de gatilhos)

```python
# Exemplos dos mapeamentos
"status do sistema"  → cmd_status
"abrir vscode"       → cmd_abrir_vscode
"música" / "musica"  → cmd_musica
"pausar" / "próxima" → cmd_musica
"acordar" / "ligar"  → cmd_acordar_pc
"verificar"          → cmd_verificar
"avisar todos"       → cmd_avisar_todos
"avisar"             → cmd_avisar
"lanterna"           → cmd_lanterna
"ajuda"              → cmd_ajuda
```

---

## templates/dashboard.html

SPA (Single Page Application) em HTML/CSS/JS puro. Sem frameworks externos.

### CSS

```
Variáveis CSS custom properties:
  --host-color / --host-sec / --host-glow / --host-bg   Paleta do nó servidor (injetada via Jinja)
  --card-color / --card-bg / --card-glow / --card-border Paleta por card (injetada via style=)
  --bg / --bg2 / --bg3 / --bg4                           Camadas de background
  --border / --border2                                   Bordas
  --success / --danger / --warn / --info                 Cores semânticas

Classes principais:
  .shell         → grid 3 linhas: topbar + tab-nav + conteúdo
  .topbar        → barra superior sticky com logo, indicadores e botões
  .tab-nav       → navegação entre abas (overflow-x: auto para mobile)
  .tab-btn       → botão de aba com .active
  .tab-page      → página de aba com display:none / .active
  .node-card     → card de nó com CSS vars injetadas
  .card-stats    → grid 3 colunas de métricas
  .sparkline-row → linha de sparklines SVG
  .terminal-panel → terminal embutido no card
  .term-titlebar  → barra com dots macOS
  .drawer-overlay / .drawer → painel lateral de info do nó
  .update-card   → painel de auto-update
  .metrics-grid  → grid de metric cards
  .history-table → tabela de histórico de updates
  .toast         → notificação temporária
  .modal-overlay / .modal → modal de troca de senha
```

### JavaScript — State

```javascript
_known  Set<string>          Tipos de nós conhecidos (inicializado via Jinja)
_data   {nt: NodeData}       Último snapshot de cada nó (do /api/nodes)
_hist   {nt: {cpu[], ram[]}} Histórico de métricas por nó (janela 60 pontos)
_th     {nt: string[]}       Histórico de comandos do terminal por nó
_thi    {nt: int}            Índice no histórico do terminal (para ↑↓)
_drwNt  string|null          Nó atualmente aberto no Drawer
MAX_H   60                   Tamanho máximo da janela de histórico
```

### JavaScript — Funções

```javascript
// Utilitários
toast(msg, type?, dur?)     Notificação temporária bottom-right
openModal(id)               Abre modal-overlay pelo id
closeModal(e, id)           Fecha modal (click no overlay ou botão)
$post(url, body) → Promise  fetch POST JSON
$get(url) → Promise         fetch GET
el(id) → HTMLElement        document.getElementById(id)

// Tab Router
switchTab(t)                Comuta tab-page e tab-btn .active
                            Dispara lazy loaders por aba

// Sparklines
_pushH(nt, cpu, ram)        Adiciona ponto ao histórico (janela deslizante)
_spark(svgId, vals, color, h=28)  Desenha sparkline SVG (área + linha)

// Polling
poll()                      GET /api/nodes, atualiza todos os cards
_updateCard(nt, data, cpu, ram)  Atualiza badge, stats, barras e sparklines
_buildCard(nt, info) → str  HTML completo de um novo card (mDNS discovery)

// Node Actions
wakeNode(nt)                POST /api/wake
shutdownNode(nt)            POST /api/shutdown (com confirm())
sendSpeak(nt)               POST /api/speak
toggleSpeak(nt)             Abre/fecha speak-panel

// Terminal
toggleTerminal(nt)          Abre/fecha terminal-panel + mensagem inicial
clearTerm(nt)               Limpa output do terminal
copyTerm(nt)                Copia output para clipboard
_tw(nt, text, cls)          Adiciona linha ao terminal (limite 400 linhas)
termKey(event, nt)          Handlers: Enter, ↑↓ (histórico), Ctrl+C, Ctrl+L
sendTerm(nt)                POST /api/terminal + coloração do output
                            Built-ins: clear, exit, help (sem round-trip)

// Broadcast
sendBroadcast()             Promise.allSettled para todos os nós em _known
buildIndSpeak()             Cria grid de envio individual por nó
iSpeak(nt)                  Envio individual via POST /api/speak

// Métricas
renderMetrics()             Atualiza met-total, met-online, met-cpu, met-ram
                            Recria per-node sparklines

// Drawer
openDrawer(nt)              Abre painel lateral com dados do nó
_refreshDrw(data)           Atualiza métricas e sparklines do drawer
closeDrawer(e?)             Fecha drawer (click no overlay ou botão)

// Update
loadUpdStatus()             GET /api/update/status → preenche campos
checkUpdate()               GET /api/update/check → compara commits
applyUpdate()               POST /api/update/apply → progress bar + toast
_renderHistory(history[])   Renderiza tabela de histórico de updates
```

---

## templates/login.html

Tela de login minimalista. Dark mode, grid background, paleta do nó injetada.

```
Formulário POST /login com campos:
  username  (text, autocomplete="username")
  password  (password, autocomplete="current-password")

Exibe flash messages com .alert-error e .alert-success
Badge no canto superior direito com NODE_TYPE.upper()
```

---

## requirements.txt

```
flask>=3.0.0          # Framework web
flask-login>=0.6.3    # Gestão de sessões autenticadas
werkzeug>=3.0.0       # Password hashing + WSGI
requests>=2.31.0      # HTTP cliente (API inter-nós)
zeroconf>=0.131.0     # mDNS/Bonjour discovery
SpeechRecognition>=3.10.0  # STT via Google
PyAudio>=0.2.14       # Captura de microfone
paramiko>=3.4.0       # SSH com chave RSA
gTTS>=2.5.0           # TTS online
pygame>=2.5.0         # Reprodução de áudio gTTS

# Auto-update usa apenas stdlib: base64, urllib, subprocess, json, os
# git deve estar instalado no sistema
```

---

## setup.sh

Script bash de instalação dual (Linux desktop + Termux).

```bash
# Detecta ambiente
IS_TERMUX   bool  Via $TERMUX_VERSION ou /data/data/com.termux
IS_ANDROID  bool  Igual IS_TERMUX

# Caminho A: Termux
  pkg install python python-pip termux-api
  pip install flask flask-login werkzeug requests zeroconf paramiko

# Caminho B: Linux
  apt install: python3 python3-pip python3-venv python3-dev
               espeak espeak-ng espeak-ng-data
               portaudio19-dev libportaudio2 libportaudiocpp0
               alsa-utils libasound2-dev build-essential gcc
               openssh-client net-tools playerctl ffmpeg
  
  Cria .venv/ via python3 -m venv
  pip install todos os pacotes de requirements.txt
  
  Gera ~/.ssh/id_rsa se não existir
  Cria run.sh, run_seven.sh, run_spark.sh
```

---

## Tabelas de Referência Rápida

### Rotas Flask — Master

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/login` | ✗ | Formulário de login |
| POST | `/login` | ✗ | Autentica |
| GET | `/logout` | ✓ | Encerra sessão |
| POST | `/change-password` | ✓ | Troca senha |
| GET | `/` | ✓ | Redirect → /dashboard |
| GET | `/dashboard` | ✓ | HTML do dashboard |
| GET | `/health` | ✗ | JSON status do nó |
| POST | `/cmd` | secret ou sessão | Executa comando |
| GET | `/api/config` | ✓ | Topologia + paletas |
| GET | `/api/nodes` | ✓ | Status de todos os nós |
| POST | `/api/wake` | ✓ | Wake-on-LAN |
| POST | `/api/shutdown` | ✓ | Shutdown de nó |
| POST | `/api/speak` | ✓ | TTS em nó |
| POST | `/api/terminal` | ✓ | Shell em nó |
| POST | `/api/reload` | ✓ | Hot-reload módulos |
| GET | `/api/update/status` | ✓ | Estado do updater |
| GET | `/api/update/check` | ✓ | Verifica commit remoto |
| POST | `/api/update/apply` | ✓ | Aplica update |

### Rotas Flask — Worker

| Método | Rota | Auth | Descrição |
|--------|------|------|-----------|
| GET | `/health` | ✗ | JSON status do nó |
| POST | `/cmd` | secret | Executa comando |

### Comandos POST /cmd

| command | Parâmetros | Restrição |
|---------|-----------|-----------|
| `speak` | `text` | Nenhuma |
| `vibrate` | `duration` (ms) | Android only |
| `notify` | `title`, `text` | — |
| `torch` | `state` (on/off) | Android only |
| `run` | `shell`, `admin_secret` | Exige ADMIN_SECRET |
| `status` | — | Nenhuma |
| `reload` | — | Nenhuma |

### Paletas por nó

| Nó | Primary | Secondary | Label |
|----|---------|-----------|-------|
| seven | `#00E5FF` | `#00B8D4` | Cyan |
| spark | `#FF6D00` | `#E65100` | Orange |
| mobile | `#AA00FF` | `#7B00D4` | Violet |
| default | `#90A4AE` | `#607D8B` | Gray |

---

*Estrutura de referência do k7-core v2.0*
