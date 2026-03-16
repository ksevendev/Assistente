# K7-Core v4.1 - Documentação Completa

## 📋 Índice
1. [Instalação](#instalação)
2. [Estrutura de Arquivos](#estrutura-de-arquivos)
3. [Configuração](#configuração)
4. [API REST](#api-rest)
5. [Features Novas v4.1](#features-novas-v41)
6. [Troubleshooting](#troubleshooting)

---

## Instalação

### Pré-requisitos
- Python 3.8+
- pip (gerenciador de pacotes Python)
- Git (para atualizações)
- Systemd (para gerenciar serviços - opcional em Termux)

### 1. Clonar o Repositório
```bash
git clone https://seu-repo/k7-core.git
cd k7-core
```

### 2. Instalar Dependências
```bash
# Criar virtualenv (opcional mas recomendado)
python3 -m venv venv
source venv/bin/activate  # Em Windows: venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

### 3. Criar Estrutura de Diretórios
```bash
mkdir -p logs data scripts commands backups
chmod +x scripts/update.sh
```

### 4. Configurar Variáveis de Ambiente
```bash
# Criar arquivo .env
cat > .env << EOF
FLASK_ENV=production
SECRET_KEY=sua-chave-secreta-aqui
PORT=5000
NODE_ID=seven
EOF
```

### 5. Configurar Systemd (Linux Desktop/Server)
```bash
# Criar arquivo de serviço
sudo tee /etc/systemd/system/k7-core-seven.service > /dev/null << EOF
[Unit]
Description=K7-Core v4.1 - Node Seven
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
ExecStart=$(which python3) core.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Ativar serviço
sudo systemctl daemon-reload
sudo systemctl enable k7-core-seven.service
sudo systemctl start k7-core-seven.service

# Verificar status
sudo systemctl status k7-core-seven.service
```

### 6. Iniciar a Aplicação
```bash
# Desenvolvimento
python3 core.py

# Produção (com gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 core:app
```

---

## Estrutura de Arquivos

```
k7-core/
├── core.py                 # Aplicação principal Flask
├── update.sh              # Script de atualização
├── requirements.txt       # Dependências Python
├── .env                   # Variáveis de ambiente
│
├── templates/             # Templates HTML
│   ├── dashboard.html     # Dashboard principal
│   ├── node_detail.html   # Página de detalhes do nó
│   ├── login.html         # Página de login
│   └── base.html          # Template base (opcional)
│
├── static/                # Arquivos estáticos
│   ├── css/
│   ├── js/
│   └── images/
│
├── commands/              # Comandos gerenciáveis
│   ├── hello_world.py
│   └── system_info.py
│
├── scripts/               # Scripts de sistema
│   └── update.sh
│
├── logs/                  # Arquivos de log
│   ├── k7core.log
│   └── update_*.log
│
├── data/                  # Dados persistentes
│   └── nodes.json         # Configuração de nós
│
├── backups/               # Backups automáticos
│   └── k7-core_*.tar.gz
│
└── venv/                  # Ambiente virtual (git ignored)
```

---

## Configuração

### Arquivo `config.py` (Não Alterar)
A estrutura atual é mantida 100% compatível com v4.0. Não há necessidade de modificar `config.py`.

### Arquivo `nodes.json`
Define os nós do sistema:

```json
[
  {
    "node_id": "seven",
    "name": "Seven",
    "node_type": "controller",
    "color": "#00BCD4",
    "status": "offline",
    "version": "4.1"
  },
  {
    "node_id": "spark",
    "name": "Spark",
    "node_type": "worker",
    "color": "#FF9800",
    "status": "offline",
    "version": "4.1"
  }
]
```

### Arquivo `requirements.txt`
```
Flask==2.3.3
Flask-Login==0.6.2
Werkzeug==2.3.7
python-dotenv==1.0.0
```

---

## API REST

### Autenticação
Todas as rotas da API requerem login via Flask-Login.

### Endpoints

#### Nós
```bash
# Listar todos os nós
GET /api/nodes

# Obter detalhes de um nó
GET /api/node/<node_id>

# Atualizar status do nó
POST /api/node/<node_id>/status
```

#### Health Check
```bash
# Health check completo do nó
GET /api/node/<node_id>/health

# Resposta:
{
  "node_id": "seven",
  "timestamp": "2025-01-15T10:30:45.123456",
  "hardware": {
    "microphone": {
      "available": true,
      "devices": 2,
      "status": "online"
    },
    "tts": {
      "available": true,
      "drivers": {
        "alsa": true,
        "gtts": true,
        "espeak": true
      },
      "status": "online"
    },
    "docker": {
      "available": true,
      "containers": 3,
      "list": [...],
      "status": "online"
    },
    "internet": {
      "available": true,
      "status": "online",
      "latency_ms": 15.5,
      "host": "8.8.8.8"
    },
    "disk": {
      "total_gb": 100.5,
      "used_gb": 45.2,
      "available_gb": 55.3,
      "usage_percent": 45.0
    },
    "memory": {
      "total_mb": 8192,
      "used_mb": 4096,
      "usage_percent": 50.0
    }
  }
}
```

#### Updates
```bash
# Iniciar atualização de um nó
POST /api/node/<node_id>/update

# Obter logs de atualização (polling)
GET /api/node/<node_id>/update/logs

# Resposta:
{
  "logs": [
    {
      "type": "log",
      "message": "[INFO] Atualizando repositório Git..."
    },
    {
      "type": "success",
      "message": "Atualização concluída com sucesso"
    }
  ]
}
```

#### Comandos
```bash
# Listar todos os comandos
GET /api/commands

# Obter um comando específico
GET /api/command/<command_id>

# Salvar/criar comando
POST /api/command
Body: {
  "id": "nome_comando",
  "content": "código Python..."
}

# Deletar comando
DELETE /api/command/<command_id>
```

#### Terminal (SSH Web)
```bash
# Executar comando no terminal
POST /api/terminal/<node_id>/execute
Body: {
  "command": "ls -la"
}

# Resposta:
{
  "output": "drwxr-xr-x  5 user...",
  "error": "",
  "return_code": 0
}
```

---

## Features Novas v4.1

### 1. Sistema de Update Inteligente ✅
- **Botão Update** no Dashboard para cada nó
- Executa:
  1. `git pull` - Atualiza código
  2. `pip install -r requirements.txt` - Instala dependências
  3. Reinicia serviço systemd
- **Log em tempo real** na tela
- **Suporte a múltiplas plataformas** (Debian, Ubuntu, Termux)

**Uso:**
```bash
# Manual (via CLI)
bash scripts/update.sh seven

# Via Dashboard
# 1. Clique em "Update" no card do nó
# 2. Acompanhe o log em tempo real
```

### 2. Deep View - Página de Detalhes ✅
Acesse `/node/<node_id>` para:

#### 📊 Sidebar - Informações
- ID, Nome, Status, Versão
- Tipo (Controller/Worker)
- Uptime
- Informações da plataforma (SO, Arquitetura, Hostname)

#### 🏥 Health Check
- **Microfone**: Detecta PyAudio e dispositivos
- **TTS**: Verifica ALSA, gTTS, eSpeak
- **Docker**: Lista containers ativos
- **Internet**: Ping + Latência
- **Disco**: Uso e espaço disponível
- **Memória**: Consumo e porcentagem

#### 🖥️ Terminal SSH Web
- Lista branca de comandos seguros
- Execução interativa
- Comandos permitidos:
  - `ls`, `pwd`, `cat`, `echo`, `date`, `uptime`, `whoami`
  - `ps`, `top`, `df`, `free`, `uname`, `systemctl status`

#### 📈 Métricas
- Uso de Memória (% com barra)
- Uso de Disco (% com barra)
- Latência de Rede (ms)

#### 📝 Logs
- Logs do sistema em tempo real

### 3. Gerenciador de Comandos ✅
Interface completa no Dashboard:

#### Listar Comandos
- Tabela com: Nome, Tamanho, Linhas de código
- Ações: Editar, Deletar

#### Criar Comando
```bash
# Via Dashboard
1. Clique em "+ Novo Comando"
2. Digite o ID (ex: "meu_comando")
3. Escreva o código Python
4. Clique em "Salvar"
```

#### Editar Comando
```bash
# Via Dashboard
1. Clique em "Editar" na tabela
2. Modifique o código
3. Clique em "Salvar"
```

#### Deletar Comando
```bash
# Via Dashboard
1. Clique em "Deletar" na tabela
2. Confirme a exclusão
```

---

## Compatibilidade com Termux (Android)

A aplicação detecta automaticamente se está rodando em Termux e:
- ✅ Desativa health checks de hardware (microfone, TTS)
- ✅ Desativa Docker (não suporta containers)
- ✅ Funciona 100% sem systemd
- ✅ Mantém terminal web ativo
- ✅ Suporta update via shell script

### Iniciar em Termux
```bash
# 1. Instalar dependências
pkg install python3 git

# 2. Clonar e configurar
git clone https://seu-repo/k7-core.git
cd k7-core
pip install -r requirements.txt

# 3. Iniciar
python3 core.py

# 4. Acessar via browser do celular
# Digite na barra de endereço: http://localhost:5000
```

---

## Paleta de Cores

### Nó Seven (Controlador)
- **Cor Principal**: Ciano (`#00BCD4`)
- **Gradiente**: Ciano → Azul escuro

### Nó Spark (Worker)
- **Cor Principal**: Laranja (`#FF9800`)
- **Gradiente**: Laranja → Laranja escuro

### Sistema
- **Fundo**: Gradiente azul escuro (`#051E3E` → `#0D1B2A`)
- **Acentos**: Branco (`#FFFFFF`)
- **Sucesso**: Verde (`#4CAF50`)
- **Erro**: Vermelho (`#F44336`)
- **Aviso**: Amarelo (`#FFC107`)

---

## Troubleshooting

### Erro: "Port already in use"
```bash
# Verificar processo usando a porta
lsof -i :5000

# Matar processo
kill -9 <PID>

# Ou usar porta diferente
PORT=5001 python3 core.py
```

### Erro: "Permission denied" em update.sh
```bash
chmod +x scripts/update.sh
```

### Erro: "Módulo não encontrado"
```bash
# Reativar virtualenv
source venv/bin/activate

# Reinstalar dependências
pip install -r requirements.txt
```

### Update falhando
```bash
# Verificar logs
tail -f logs/k7core.log

# Executar update manualmente com debug
bash -x scripts/update.sh seven
```

### Serviço não inicia
```bash
# Verificar status
sudo systemctl status k7-core-seven.service

# Ver logs
sudo journalctl -u k7-core-seven.service -n 50
```

### Terminal não executa comandos
- Verificar se comando está na whitelist
- Comandos devem ser separados por espaços
- Timeouts ocorrem após 5 segundos

---

## Segurança

### Autenticação
- Flask-Login com hashing de senhas (Werkzeug)
- Sessions seguras com SECRET_KEY

### Terminal Web
- **Lista branca de comandos** (não execute arbitrary commands)
- Timeout de 5 segundos por comando
- Sem acesso a shell interativo

### API
- Todas as rotas requerem autenticação
- Validação de node_id
- Sem acesso a diretórios fora de BASE_DIR

### Update Script
- Backup automático antes de atualizar
- Validação de sintaxe Python
- Logs detalhados de cada etapa

---

## Desenvolvimento

### Adicionar Novo Endpoint
```python
@app.route('/api/novo-endpoint', methods=['GET'])
@login_required
def novo_endpoint():
    return jsonify({'status': 'ok'})
```

### Adicionar Nova Feature ao Health Check
```python
@staticmethod
def check_nova_feature():
    return {
        'available': True,
        'status': 'online'
    }
```

### Estender o Dashboard
1. Adicionar seção HTML em `dashboard.html`
2. Criar função JavaScript para carregar dados
3. Criar endpoint API em `core.py`
4. Consumir dados com `fetch()`

---

## Contato & Suporte

Para reportar bugs ou sugerir features:
- Abrir issue no repositório
- Enviar logs (`logs/k7core.log`)
- Descrever ambiente (SO, versão Python, etc)

---

**Última atualização**: 2025-01-15  
**Versão**: K7-Core v4.1  
**Status**: Produção ✅
