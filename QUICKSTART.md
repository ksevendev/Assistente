# K7-Core v4.1 - Quick Start (5 minutos)

## ⚡ Início Rápido

### 1. **Instalação Básica**
```bash
# Clonar repositório
git clone https://seu-repo/k7-core.git
cd k7-core

# Instalar dependências
pip install -r requirements.txt

# Criar estrutura de diretórios
mkdir -p logs data scripts commands backups
chmod +x scripts/update.sh
```

### 2. **Iniciar a Aplicação**
```bash
# Desenvolvimento
python3 core.py

# A aplicação estará disponível em: http://localhost:5000
```

### 3. **Fazer Login**
```
Usuário: admin
Senha: admin123
```

---

## 🎯 Principais Features

### 📊 Dashboard Principal
- **Visualizar nós**: Cards com status, versão, uptime
- **Botão Update**: Atualiza nó com logs em tempo real
- **Gerenciador de Comandos**: Criar, editar, deletar scripts Python

### 🔍 Detalhes do Nó (`/node/<node_id>`)
- **Health Check**: Verifica Microfone, TTS, Docker, Internet, Disco, Memória
- **Terminal Web**: Execute comandos seguros (ls, pwd, ps, df, free, etc)
- **Métricas**: Gráficos de uso de recursos
- **Logs**: Acompanhamento em tempo real

### 🔧 Gerenciador de Comandos
```bash
# No Dashboard:
1. Clique em "+ Novo Comando"
2. Digite o ID: "meu_script"
3. Cole o código Python
4. Clique em "Salvar"

# Para editar:
1. Clique em "Editar" na tabela
2. Modifique e salve

# Para deletar:
1. Clique em "Deletar"
2. Confirme
```

### 🚀 Sistema de Update
```bash
# Via Dashboard:
1. Clique em "⬆ Update" no card do nó
2. Acompanhe o log da atualização
3. Processo automático:
   - git pull
   - pip install -r requirements.txt
   - Reinicia serviço systemd

# Via CLI:
bash scripts/update.sh seven
```

---

## 📱 Compatibilidade Termux

### Instalar no Termux (Android)
```bash
# 1. Instalar Python e Git
pkg install python3 git

# 2. Clonar e configurar
git clone https://seu-repo/k7-core.git
cd k7-core
pip install -r requirements.txt

# 3. Iniciar
python3 core.py

# 4. Acessar pelo browser do celular
# Digite: http://localhost:5000
```

✅ **Funciona 100% em Termux:**
- Dashboard completo
- Terminal web
- Update script
- Gerenciador de comandos
- Sem necessidade de systemd

❌ **Desativado em Termux:**
- Health check de microfone/TTS
- Docker
- Mas todos os outros recursos funcionam!

---

## 🔑 Credenciais Padrão

```
Usuário: admin
Senha: admin123
```

⚠️ **IMPORTANTE**: Mude a senha em produção!

---

## 📁 Estrutura de Arquivos Essencial

```
k7-core/
├── core.py                 ← Aplicação principal
├── requirements.txt        ← Dependências
├── scripts/
│   └── update.sh          ← Script de update
├── templates/
│   ├── dashboard.html
│   ├── node_detail.html
│   └── login.html
├── commands/              ← Seus comandos Python
├── logs/                  ← Logs automáticos
└── data/
    └── nodes.json         ← Configuração dos nós
```

---

## 🐛 Solução Rápida de Problemas

### Porta 5000 já está em uso
```bash
PORT=5001 python3 core.py
```

### Módulo não encontrado
```bash
pip install -r requirements.txt
```

### Arquivo update.sh não é executável
```bash
chmod +x scripts/update.sh
```

### Terminal não funciona
- Comando deve estar na whitelist
- Exemplos válidos: `ls`, `pwd`, `ps`, `df`, `free`
- Timeout máximo: 5 segundos

---

## 🎨 Personalizações

### Mudar cor do nó
Edite `data/nodes.json`:
```json
{
  "node_id": "seven",
  "color": "#00BCD4"  ← Mude para qualquer cor hex
}
```

### Adicionar novo nó
Adicione em `data/nodes.json`:
```json
{
  "node_id": "novo_no",
  "name": "Novo Nó",
  "node_type": "worker",
  "color": "#2196F3"
}
```

### Adicionar comando
1. Crie arquivo em `commands/meu_comando.py`
2. Ou use o gerenciador no Dashboard
3. Arquivo será acessível via API

---

## 📊 Recursos Disponíveis

| Feature | Desktop | Termux | Status |
|---------|---------|--------|--------|
| Dashboard | ✅ | ✅ | Completo |
| Terminal Web | ✅ | ✅ | Completo |
| Health Check | ✅ | ⚠️ | Parcial* |
| Microfone | ✅ | ❌ | Desktop only |
| TTS | ✅ | ❌ | Desktop only |
| Docker | ✅ | ❌ | Desktop only |
| Update Script | ✅ | ✅ | Completo |
| Gerenciador | ✅ | ✅ | Completo |

*Em Termux: apenas Internet, Disco e Memória

---

## 🔒 Segurança

- ✅ Autenticação via Flask-Login
- ✅ Senhas hasheadas
- ✅ Terminal com lista branca de comandos
- ✅ Timeouts em execuções
- ✅ Backup automático antes de update
- ✅ Validação de sintaxe Python

---

## 📞 Próximos Passos

1. **Explore o Dashboard**: Veja todos os nós e status
2. **Teste o Terminal**: Execute `ls`, `pwd`, `uptime`
3. **Crie um Comando**: Adicione via gerenciador
4. **Faça um Update**: Teste o sistema de atualização
5. **Configure Systemd**: Para iniciar automaticamente no boot

---

## 📚 Documentação Completa

Para mais informações, consulte `INSTALL.md`:
- Instalação detalhada
- Configuração de systemd
- API REST completa
- Troubleshooting avançado
- Desenvolvimento de features

---

**Pronto para começar!** 🚀

Qualquer dúvida, consulte a documentação ou os logs em `logs/k7core.log`
