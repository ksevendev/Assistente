"""
Comando de Exemplo: System Info
Exibe informações do sistema
"""

import platform
import socket
import os
from datetime import datetime

def get_system_info():
    """Retorna informações do sistema"""
    
    info = {
        'timestamp': datetime.now().isoformat(),
        'hostname': socket.gethostname(),
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'python_version': platform.python_version(),
        'uptime_seconds': os.popen('uptime -p').read().strip() if os.name != 'nt' else 'N/A',
        'user': os.environ.get('USER', 'Unknown'),
    }
    
    return info

if __name__ == '__main__':
    import json
    print(json.dumps(get_system_info(), indent=2))
