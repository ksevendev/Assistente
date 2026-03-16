"""
K7-Core v4.1 - Assistente Distribuído com Suporte a Updates e Health Checks
Compatível com: Debian, Ubuntu, Termux (Android)
Autor: Desenvolvedor Sênior
Mantém compatibilidade 100% com k7-core v4
"""

import os
import sys
import json
import subprocess
import threading
import queue
import platform
import socket
import time
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# ============================================================================
# CONFIGURAÇÃO BÁSICA
# ============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-k7-core-v4-1')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Diretórios do projeto
BASE_DIR = Path(__file__).parent
COMMANDS_DIR = BASE_DIR / 'commands'
LOGS_DIR = BASE_DIR / 'logs'
DATA_DIR = BASE_DIR / 'data'

# Criar diretórios se não existirem
COMMANDS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'k7core.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DETECÇÃO DE PLATAFORMA
# ============================================================================

def detect_platform():
    """Detecta a plataforma (Debian/Ubuntu ou Termux)"""
    system = platform.system()
    is_termux = os.path.exists('/data/data/com.termux') or os.environ.get('TERM') == 'xterm-256color'
    
    return {
        'system': system,
        'is_termux': is_termux,
        'hostname': socket.gethostname(),
        'release': platform.release(),
        'machine': platform.machine()
    }

PLATFORM_INFO = detect_platform()

# ============================================================================
# MODELO DE USUÁRIO (Flask-Login)
# ============================================================================

class User:
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
    
    def get_id(self):
        return str(self.id)

# Usuário dummy para demonstração (substitua com banco de dados real)
USERS = {
    'admin': {
        'password': generate_password_hash('admin123'),
        'node_id': 'seven'  # Nó associado
    }
}

@login_manager.user_loader
def load_user(user_id):
    for username, data in USERS.items():
        if username == user_id:
            return User(username, username)
    return None

# ============================================================================
# CLASSE NODE - Representação de um Nó
# ============================================================================

class K7Node:
    def __init__(self, node_id, name, node_type='controller', color='#00BCD4'):
        self.node_id = node_id
        self.name = name
        self.node_type = node_type  # 'controller' ou 'worker'
        self.color = color
        self.status = 'offline'
        self.last_heartbeat = None
        self.version = '4.1'
        self.uptime = 0
        self.platform_info = PLATFORM_INFO if node_id == os.environ.get('NODE_ID', 'seven') else {}
    
    def to_dict(self):
        return {
            'node_id': self.node_id,
            'name': self.name,
            'node_type': self.node_type,
            'color': self.color,
            'status': self.status,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'version': self.version,
            'uptime': self.uptime,
            'platform_info': self.platform_info
        }

# ============================================================================
# GERENCIADOR DE NÓS
# ============================================================================

class NodesManager:
    def __init__(self):
        self.nodes = {}
        self.load_nodes()
    
    def load_nodes(self):
        """Carrega nós do arquivo de configuração ou cria padrão"""
        config_file = DATA_DIR / 'nodes.json'
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    for node_data in data:
                        node = K7Node(**node_data)
                        self.nodes[node.node_id] = node
            except Exception as e:
                logger.error(f"Erro ao carregar nós: {e}")
                self._create_default_nodes()
        else:
            self._create_default_nodes()
            self.save_nodes()
    
    def _create_default_nodes(self):
        """Cria nós padrão"""
        self.nodes = {
            'seven': K7Node('seven', 'Seven', 'controller', '#00BCD4'),
            'spark': K7Node('spark', 'Spark', 'worker', '#FF9800'),
        }
    
    def save_nodes(self):
        """Salva nós em arquivo JSON"""
        config_file = DATA_DIR / 'nodes.json'
        try:
            with open(config_file, 'w') as f:
                json.dump([node.to_dict() for node in self.nodes.values()], f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar nós: {e}")
    
    def get_all_nodes(self):
        """Retorna todos os nós"""
        return list(self.nodes.values())
    
    def get_node(self, node_id):
        """Retorna um nó específico"""
        return self.nodes.get(node_id)
    
    def update_node_status(self, node_id, status, uptime=None):
        """Atualiza status do nó"""
        if node_id in self.nodes:
            self.nodes[node_id].status = status
            self.nodes[node_id].last_heartbeat = datetime.now()
            if uptime is not None:
                self.nodes[node_id].uptime = uptime
            return True
        return False

# Instância global
nodes_manager = NodesManager()

# ============================================================================
# UPDATE SYSTEM - Sistema de Atualização
# ============================================================================

class UpdateManager:
    def __init__(self):
        self.update_queue = {}
        self.update_threads = {}
    
    def start_update(self, node_id, callback=None):
        """Inicia atualização de um nó"""
        if node_id in self.update_threads and self.update_threads[node_id].is_alive():
            return {'error': 'Atualização já em progresso'}
        
        # Cria fila para logs
        log_queue = queue.Queue()
        self.update_queue[node_id] = log_queue
        
        # Inicia thread de atualização
        thread = threading.Thread(
            target=self._update_worker,
            args=(node_id, log_queue),
            daemon=True
        )
        self.update_threads[node_id] = thread
        thread.start()
        
        return {'status': 'updating', 'node_id': node_id}
    
    def _update_worker(self, node_id, log_queue):
        """Worker que executa a atualização"""
        try:
            # Script de atualização
            update_script = BASE_DIR / 'scripts' / 'update.sh'
            
            if not update_script.exists():
                log_queue.put({'type': 'error', 'message': 'Script de update não encontrado'})
                return
            
            # Executar script
            process = subprocess.Popen(
                ['bash', str(update_script), node_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                log_queue.put({'type': 'log', 'message': line.strip()})
            
            return_code = process.wait()
            
            if return_code == 0:
                log_queue.put({'type': 'success', 'message': 'Atualização concluída com sucesso'})
                nodes_manager.update_node_status(node_id, 'online')
            else:
                log_queue.put({'type': 'error', 'message': f'Atualização falhou com código {return_code}'})
        
        except Exception as e:
            log_queue.put({'type': 'error', 'message': str(e)})
    
    def get_update_logs(self, node_id):
        """Retorna logs de atualização em tempo real"""
        if node_id not in self.update_queue:
            return []
        
        logs = []
        queue_obj = self.update_queue[node_id]
        
        while not queue_obj.empty():
            try:
                logs.append(queue_obj.get_nowait())
            except queue.Empty:
                break
        
        return logs

# Instância global
update_manager = UpdateManager()

# ============================================================================
# HEALTH CHECK SYSTEM
# ============================================================================

class HealthChecker:
    @staticmethod
    def check_microphone(is_termux=False):
        """Verifica disponibilidade do microfone"""
        if is_termux:
            return {'available': False, 'reason': 'Não disponível em Termux'}
        
        try:
            import pyaudio
            audio = pyaudio.PyAudio()
            device_count = audio.get_device_count()
            audio.terminate()
            
            return {
                'available': device_count > 0,
                'devices': device_count,
                'status': 'online' if device_count > 0 else 'offline'
            }
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    @staticmethod
    def check_tts(is_termux=False):
        """Verifica disponibilidade de TTS"""
        if is_termux:
            return {'available': False, 'reason': 'Não disponível em Termux'}
        
        checks = {
            'alsa': False,
            'gtts': False,
            'espeak': False
        }
        
        try:
            result = subprocess.run(['which', 'espeak'], capture_output=True)
            checks['espeak'] = result.returncode == 0
        except:
            pass
        
        try:
            result = subprocess.run(['which', 'aplay'], capture_output=True)
            checks['alsa'] = result.returncode == 0
        except:
            pass
        
        try:
            import gtts
            checks['gtts'] = True
        except:
            pass
        
        return {
            'available': any(checks.values()),
            'drivers': checks,
            'status': 'online' if any(checks.values()) else 'offline'
        }
    
    @staticmethod
    def check_docker(is_termux=False):
        """Verifica containers Docker ativos"""
        if is_termux:
            return {'available': False, 'reason': 'Não disponível em Termux'}
        
        try:
            result = subprocess.run(
                ['docker', 'ps', '--format', '{{json .}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                containers = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        containers.append(json.loads(line))
                
                return {
                    'available': True,
                    'containers': len(containers),
                    'list': containers,
                    'status': 'online' if containers else 'idle'
                }
            else:
                return {'available': False, 'error': 'Docker não respondeu'}
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    @staticmethod
    def check_internet(hostname='8.8.8.8', port=53, timeout=3):
        """Verifica conectividade de internet (ping)"""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).connect((hostname, port))
            
            # Medir latência
            start = time.time()
            subprocess.run(['ping', '-c', '1', hostname], 
                         capture_output=True, timeout=timeout)
            latency = (time.time() - start) * 1000
            
            return {
                'available': True,
                'status': 'online',
                'latency_ms': round(latency, 2),
                'host': hostname
            }
        except Exception as e:
            return {
                'available': False,
                'status': 'offline',
                'error': str(e)
            }
    
    @staticmethod
    def check_disk_space():
        """Verifica espaço em disco"""
        try:
            result = subprocess.run(
                ['df', BASE_DIR],
                capture_output=True,
                text=True
            )
            
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                total = int(parts[1]) * 1024  # em bytes
                used = int(parts[2]) * 1024
                available = int(parts[3]) * 1024
                
                return {
                    'total_gb': round(total / (1024**3), 2),
                    'used_gb': round(used / (1024**3), 2),
                    'available_gb': round(available / (1024**3), 2),
                    'usage_percent': round((used / total) * 100, 1)
                }
        except Exception as e:
            logger.error(f"Erro ao verificar espaço em disco: {e}")
        
        return {}
    
    @staticmethod
    def check_memory():
        """Verifica uso de memória"""
        try:
            result = subprocess.run(
                ['free', '-b'],
                capture_output=True,
                text=True
            )
            
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                total = int(parts[1])
                used = int(parts[2])
                
                return {
                    'total_mb': round(total / (1024**2), 1),
                    'used_mb': round(used / (1024**2), 1),
                    'usage_percent': round((used / total) * 100, 1)
                }
        except Exception as e:
            logger.error(f"Erro ao verificar memória: {e}")
        
        return {}

# ============================================================================
# GERENCIADOR DE COMANDOS
# ============================================================================

class CommandsManager:
    @staticmethod
    def list_commands():
        """Lista todos os arquivos .py em /commands"""
        commands = []
        try:
            for file in COMMANDS_DIR.glob('*.py'):
                if file.name != '__init__.py':
                    try:
                        with open(file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        commands.append({
                            'id': file.stem,
                            'name': file.name,
                            'path': str(file),
                            'size': file.stat().st_size,
                            'created': file.stat().st_ctime,
                            'modified': file.stat().st_mtime,
                            'lines': len(content.split('\n')),
                            'preview': content[:200]
                        })
                    except Exception as e:
                        logger.error(f"Erro ao ler {file}: {e}")
        except Exception as e:
            logger.error(f"Erro ao listar comandos: {e}")
        
        return commands
    
    @staticmethod
    def get_command(command_id):
        """Retorna conteúdo completo de um comando"""
        file = COMMANDS_DIR / f"{command_id}.py"
        
        if file.exists():
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    return {
                        'id': command_id,
                        'name': file.name,
                        'content': f.read()
                    }
            except Exception as e:
                logger.error(f"Erro ao ler comando: {e}")
        
        return None
    
    @staticmethod
    def save_command(command_id, content):
        """Salva ou cria um comando"""
        file = COMMANDS_DIR / f"{command_id}.py"
        
        try:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'message': f'Comando {command_id} salvo'}
        except Exception as e:
            logger.error(f"Erro ao salvar comando: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def delete_command(command_id):
        """Deleta um comando"""
        file = COMMANDS_DIR / f"{command_id}.py"
        
        try:
            if file.exists():
                file.unlink()
                return {'success': True, 'message': f'Comando {command_id} deletado'}
            return {'success': False, 'error': 'Comando não encontrado'}
        except Exception as e:
            logger.error(f"Erro ao deletar comando: {e}")
            return {'success': False, 'error': str(e)}

# ============================================================================
# ROTAS - AUTENTICAÇÃO
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and check_password_hash(USERS[username]['password'], password):
            user = User(username, username)
            login_user(user)
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='Credenciais inválidas')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ============================================================================
# ROTAS - DASHBOARD
# ============================================================================

@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# ============================================================================
# ROTAS - API
# ============================================================================

@app.route('/api/nodes', methods=['GET'])
@login_required
def api_get_nodes():
    """Retorna lista de nós"""
    nodes = nodes_manager.get_all_nodes()
    return jsonify([node.to_dict() for node in nodes])

@app.route('/api/node/<node_id>', methods=['GET'])
@login_required
def api_get_node(node_id):
    """Retorna detalhes de um nó específico"""
    node = nodes_manager.get_node(node_id)
    
    if not node:
        return jsonify({'error': 'Nó não encontrado'}), 404
    
    return jsonify(node.to_dict())

@app.route('/api/node/<node_id>/health', methods=['GET'])
@login_required
def api_node_health(node_id):
    """Retorna health check completo de um nó"""
    is_termux = PLATFORM_INFO.get('is_termux', False)
    
    health = {
        'node_id': node_id,
        'timestamp': datetime.now().isoformat(),
        'hardware': {
            'microphone': HealthChecker.check_microphone(is_termux),
            'tts': HealthChecker.check_tts(is_termux),
            'docker': HealthChecker.check_docker(is_termux),
            'internet': HealthChecker.check_internet(),
            'disk': HealthChecker.check_disk_space(),
            'memory': HealthChecker.check_memory()
        }
    }
    
    return jsonify(health)

@app.route('/api/node/<node_id>/update', methods=['POST'])
@login_required
def api_node_update(node_id):
    """Inicia atualização de um nó"""
    node = nodes_manager.get_node(node_id)
    
    if not node:
        return jsonify({'error': 'Nó não encontrado'}), 404
    
    result = update_manager.start_update(node_id)
    return jsonify(result)

@app.route('/api/node/<node_id>/update/logs', methods=['GET'])
@login_required
def api_update_logs(node_id):
    """Retorna logs de atualização em tempo real (SSE)"""
    logs = update_manager.get_update_logs(node_id)
    return jsonify({'logs': logs})

@app.route('/api/commands', methods=['GET'])
@login_required
def api_list_commands():
    """Lista todos os comandos"""
    commands = CommandsManager.list_commands()
    return jsonify(commands)

@app.route('/api/command/<command_id>', methods=['GET'])
@login_required
def api_get_command(command_id):
    """Retorna conteúdo de um comando"""
    command = CommandsManager.get_command(command_id)
    
    if not command:
        return jsonify({'error': 'Comando não encontrado'}), 404
    
    return jsonify(command)

@app.route('/api/command', methods=['POST'])
@login_required
def api_save_command():
    """Salva um comando novo ou existente"""
    data = request.get_json()
    command_id = data.get('id')
    content = data.get('content')
    
    if not command_id or not content:
        return jsonify({'error': 'ID e conteúdo são obrigatórios'}), 400
    
    result = CommandsManager.save_command(command_id, content)
    return jsonify(result)

@app.route('/api/command/<command_id>', methods=['DELETE'])
@login_required
def api_delete_command(command_id):
    """Deleta um comando"""
    result = CommandsManager.delete_command(command_id)
    return jsonify(result)

@app.route('/node/<node_id>')
@login_required
def node_detail(node_id):
    """Página de detalhes do nó"""
    node = nodes_manager.get_node(node_id)
    
    if not node:
        return "Nó não encontrado", 404
    
    return render_template('node_detail.html', node=node.to_dict())

# ============================================================================
# ROTAS - PÁGINA DE DETALHES DO NÓ
# ============================================================================

@app.route('/api/terminal/<node_id>/execute', methods=['POST'])
@login_required
def api_terminal_execute(node_id):
    """Executa comando no terminal (com segurança)"""
    data = request.get_json()
    command = data.get('command', '')
    
    # Lista branca de comandos permitidos
    ALLOWED_COMMANDS = [
        'ls', 'pwd', 'cat', 'echo', 'date', 'uptime', 'whoami',
        'ps', 'top -bn1', 'df', 'free', 'uname', 'systemctl status'
    ]
    
    # Verificar se comando está na whitelist (início)
    is_allowed = any(command.startswith(allowed) for allowed in ALLOWED_COMMANDS)
    
    if not is_allowed:
        return jsonify({'error': 'Comando não permitido'}), 403
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return jsonify({
            'output': result.stdout,
            'error': result.stderr,
            'return_code': result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Comando expirou'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

if __name__ == '__main__':
    # Criar diretório scripts se não existir
    scripts_dir = BASE_DIR / 'scripts'
    scripts_dir.mkdir(exist_ok=True)
    
    logger.info(f"K7-Core v4.1 iniciando em {PLATFORM_INFO['hostname']}")
    logger.info(f"Plataforma: {PLATFORM_INFO['system']} ({'Termux' if PLATFORM_INFO['is_termux'] else 'Desktop'})")
    
    # Iniciar Flask
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_ENV') == 'development',
        use_reloader=False
    )
