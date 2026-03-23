# =============================================================================
# k7-core v3.0 | intelligence.py
# Motor de Inteligência — Raciocínio + Personalidade + Autonomia Supervisionada
#
# RESPONSABILIDADES:
#   1. IntelligenceEngine  → orquestra RAG, LLM e geração de resposta
#   2. PersonalityLayer    → transforma respostas técnicas em Seven ou Spark
#   3. SituationalAwareness → monitora logs dos nós e detecta anomalias
#   4. AutonomyEngine      → propõe ações, aguarda OK, executa
#
# BACKENDS LLM suportados (em ordem de prioridade):
#   a) Ollama local         → llama3, mistral, codestral (zero custo)
#   b) Gemini API           → gemini-1.5-flash (rápido, barato)
#   c) Fallback heurístico  → sem LLM — usa apenas RAG + templates
#
# FLUXO DE UMA PERGUNTA:
#   usuário faz pergunta
#     → KnowledgeBase.search() → chunks relevantes dos projetos
#     → EpisodicStore.recall() → contexto recente (últimas interações)
#     → LLM.generate()        → resposta com RAG como contexto
#     → PersonalityLayer      → voz e estilo de Seven ou Spark
#     → speak() ou chat UI    → entrega ao usuário
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional

logger = logging.getLogger("k7.intelligence")

# Import interno
try:
    from knowledge_base import KnowledgeBase
    _KB_OK = True
except ImportError:
    _KB_OK = False
    logger.warning("[INTEL] knowledge_base não disponível.")

try:
    import config
    NODE_TYPE      = config.NODE_TYPE
    ASSISTANT_NAME = config.ASSISTANT_NAME
    DATA_DIR       = config.DATA_DIR
except ImportError:
    NODE_TYPE      = "seven"
    ASSISTANT_NAME = "Seven"
    DATA_DIR       = str(Path(__file__).parent / "data")

# ─── LLM backends ─────────────────────────────────────────────────────────────
try:
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False


# =============================================================================
# PERSONALIDADE — Seven e Spark têm vozes distintas
# =============================================================================

class PersonalityLayer:
    """
    Transforma uma resposta técnica bruta na voz de Seven ou Spark.

    Seven (Azul/Estabilidade):
      - Calmo, metódico, reflexivo
      - Usa analogias de engenharia e sistemas
      - Prefere contexto antes de resposta
      - Fala na primeira pessoa do plural ("vamos verificar...")

    Spark (Laranja/Energia):
      - Direto, energético, entusiasmado
      - Vai direto ao ponto, usa frases curtas
      - Propõe ação imediata
      - Usa verbos de ação ("bora resolver", "já vejo o problema")
    """

    SEVEN_TRAITS = {
        "opener": [
            "Deixa eu analisar isso com calma.",
            "Vamos entender o contexto primeiro.",
            "Interessante. Pensando bem sobre isso...",
            "Com base no que sei dos seus projetos,",
            "Analisando os dados disponíveis,",
        ],
        "transition": [
            "O que eu percebo aqui é",
            "Considerando a arquitetura atual,",
            "Do ponto de vista sistêmico,",
            "Vale notar que",
        ],
        "action": [
            "Sugiro que a gente",
            "Uma abordagem sólida seria",
            "Podemos trabalhar nisso da seguinte forma:",
            "A estratégia mais robusta seria",
        ],
        "tone": "calmo, analítico, encorajador",
    }

    SPARK_TRAITS = {
        "opener": [
            "Direto ao ponto:",
            "Já vi esse padrão antes —",
            "Isso é interessante! Olha:",
            "Bora resolver isso.",
            "Sem enrolação:",
        ],
        "transition": [
            "O problema real é",
            "O que tá travando é",
            "A sacada aqui é",
            "Importante:",
        ],
        "action": [
            "Faz assim:",
            "Minha sugestão:",
            "Executa isso:",
            "O próximo passo é",
        ],
        "tone": "direto, energético, prático",
    }

    def __init__(self, node_type: str = "seven"):
        self.node_type = node_type
        self.traits    = self.SEVEN_TRAITS if node_type == "seven" else self.SPARK_TRAITS

    def wrap(self, raw_response: str, context_type: str = "general") -> str:
        """
        Aplica a personalidade sobre uma resposta bruta.
        Não modifica o conteúdo técnico — apenas o framing.
        """
        import random
        if not raw_response.strip():
            return raw_response

        # Se resposta já parece personalizada, retorna como está
        if len(raw_response) < 40:
            return raw_response

        openers      = self.traits["opener"]
        transitions  = self.traits["transition"]

        # Adiciona opener somente se a resposta não começar com um
        first_word = raw_response.split()[0].lower().rstrip('.,!')
        skip_opener_words = {
            "o", "a", "os", "as", "um", "uma", "sim", "não",
            "ok", "certo", "aqui", "isso", "esse"
        }
        needs_opener = first_word not in skip_opener_words and len(raw_response) > 100

        if needs_opener and random.random() > 0.4:
            opener = random.choice(openers)
            raw_response = f"{opener} {raw_response}"

        return raw_response.strip()

    def format_for_voice(self, text: str) -> str:
        """Remove markdown e formata para TTS."""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', 'ver código na tela', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Remove markdown
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'#{1,6}\s+', '', text)
        text = re.sub(r'\n{2,}', '. ', text)
        text = re.sub(r'\n', ' ', text)
        # Limita para TTS
        if len(text) > 500:
            sentences = re.split(r'(?<=[.!?])\s+', text)
            short = []
            total = 0
            for s in sentences:
                total += len(s)
                short.append(s)
                if total > 400:
                    break
            text = ' '.join(short)
        return text.strip()


# =============================================================================
# BACKENDS LLM — Ollama e Gemini com fallback
# =============================================================================

class OllamaBackend:
    """Ollama rodando localmente. Zero custo, privado."""

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "llama3"):
        self.base_url = base_url.rstrip('/')
        self.model    = model

    def is_available(self) -> bool:
        if not _REQUESTS_OK:
            return False
        try:
            r = _req.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, system: str = "",
                 max_tokens: int = 600, stream: bool = False) -> str:
        """Gera resposta via Ollama."""
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.65,
                "top_p": 0.9,
            }
        }
        try:
            r = _req.post(
                f"{self.base_url}/api/generate",
                json=payload, timeout=90
            )
            if r.status_code == 200:
                return r.json().get("response", "").strip()
            logger.error(f"[OLLAMA] HTTP {r.status_code}: {r.text[:200]}")
            return ""
        except Exception as exc:
            logger.error(f"[OLLAMA] {exc}")
            return ""

    def list_models(self) -> list[str]:
        try:
            r = _req.get(f"{self.base_url}/api/tags", timeout=3)
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


class GeminiBackend:
    """Google Gemini API. Rápido para perguntas longas."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model   = model

    def is_available(self) -> bool:
        return bool(self.api_key) and _REQUESTS_OK

    def generate(self, prompt: str, system: str = "",
                 max_tokens: int = 600, stream: bool = False) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature":     0.65,
                "topP":            0.9,
            }
        }
        url = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        try:
            r = _req.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                return " ".join(p.get("text", "") for p in parts).strip()
            logger.error(f"[GEMINI] HTTP {r.status_code}: {r.text[:200]}")
            return ""
        except Exception as exc:
            logger.error(f"[GEMINI] {exc}")
            return ""


class FallbackBackend:
    """
    Sem LLM — usa apenas RAG + templates simples.
    Garante que o sistema funcione mesmo sem Ollama ou Gemini.
    """

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, system: str = "",
                 max_tokens: int = 600, stream: bool = False) -> str:
        """
        Extrai informação relevante dos chunks RAG embutidos no prompt.
        Retorna os trechos mais relevantes formatados.
        """
        # Extrai seção de contexto do prompt
        context_match = re.search(
            r'CONTEXTO DOS PROJETOS:(.*?)PERGUNTA:', prompt, re.DOTALL
        )
        if context_match:
            raw_context = context_match.group(1).strip()
            # Pega os primeiros 3 blocos de contexto
            blocks = re.split(r'---+', raw_context)
            snippets = []
            for block in blocks[:3]:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if lines:
                    snippets.append('\n'.join(lines[:4]))
            if snippets:
                return (
                    "Com base nos seus projetos indexados:\n\n" +
                    "\n\n".join(snippets) +
                    "\n\n(Instale Ollama ou configure a API Gemini para respostas mais elaboradas.)"
                )
        return (
            "Não tenho informação suficiente nos projetos indexados para responder isso. "
            "Tente reindexar com: python knowledge_base.py --index"
        )


# =============================================================================
# CONSCIÊNCIA SITUACIONAL — monitora saúde dos nós
# =============================================================================

class SituationalAwareness:
    """
    Monitora logs de /health e /cmd de todos os nós.
    Detecta anomalias e gera alertas com diagnóstico contextualizado.
    """

    # Padrões de erro que indicam problemas sérios
    ERROR_PATTERNS = [
        (re.compile(r'disk.*full|no space left|ENOSPC', re.I),
         "disco cheio", "critical"),
        (re.compile(r'out of memory|OOM|killed', re.I),
         "falta de memória", "critical"),
        (re.compile(r'connection refused|ECONNREFUSED', re.I),
         "serviço recusando conexão", "warning"),
        (re.compile(r'syntax error|SyntaxError|IndentationError', re.I),
         "erro de sintaxe no código", "error"),
        (re.compile(r'import error|ModuleNotFoundError|ImportError', re.I),
         "dependência faltando", "error"),
        (re.compile(r'permission denied|EACCES|EPERM', re.I),
         "permissão negada", "warning"),
        (re.compile(r'timeout|ETIMEDOUT', re.I),
         "timeout de conexão", "warning"),
        (re.compile(r'traceback|exception', re.I),
         "exceção Python", "error"),
        (re.compile(r'cpu.*9[0-9]%|cpu.*100%', re.I),
         "CPU sobrecarregada", "warning"),
        (re.compile(r'disk.*9[5-9]%|disk.*100%', re.I),
         "disco quase cheio", "warning"),
    ]

    def __init__(self, kb: "KnowledgeBase"):
        self.kb        = kb
        self._log_lock = threading.Lock()
        self._log_buf: list[dict] = []   # buffer de eventos recentes

    def ingest_health(self, node: str, health_data: dict,
                      session_id: str = "monitor"):
        """Processa dados do /health de um nó."""
        sys_info = health_data.get("system", {})

        # Verifica disco
        disk_pct = sys_info.get("disk_percent", "").rstrip('%')
        if disk_pct.isdigit() and int(disk_pct) >= 90:
            self._alert(
                node, session_id,
                f"Disco em {disk_pct}% no nó {node}",
                "disk_warning", {"disk_percent": disk_pct}
            )

        # Verifica CPU
        cpu = sys_info.get("cpu_percent", "0")
        try:
            if float(cpu) >= 85:
                self._alert(
                    node, session_id,
                    f"CPU em {float(cpu):.0f}% no nó {node}",
                    "cpu_warning", {"cpu_percent": cpu}
                )
        except ValueError:
            pass

        # Registra episódio de saúde
        self.kb.remember(
            session_id, node, "health_check",
            json.dumps(sys_info),
            {"node": node, "timestamp": datetime.now().isoformat()}
        )

    def ingest_log_line(self, node: str, line: str,
                        session_id: str = "monitor"):
        """Analisa uma linha de log em busca de padrões de erro."""
        with self._log_lock:
            self._log_buf.append({"node": node, "line": line, "ts": time.time()})
            # Mantém apenas últimas 200 linhas
            if len(self._log_buf) > 200:
                self._log_buf = self._log_buf[-200:]

        for pattern, description, severity in self.ERROR_PATTERNS:
            if pattern.search(line):
                self._alert(
                    node, session_id,
                    f"[{severity.upper()}] {description} detectado no nó {node}: {line[:120]}",
                    f"log_{severity}",
                    {"pattern": description, "line": line[:200], "severity": severity}
                )
                break

    def _alert(self, node: str, session_id: str,
               message: str, event_type: str, metadata: dict):
        """Registra alerta na memória episódica."""
        logger.warning(f"[AWARENESS] {message}")
        self.kb.remember(session_id, node, event_type, message, metadata)

    def analyze_failure(self, node: str, error_context: str) -> dict:
        """
        Quando um nó falha, analisa o contexto usando o conhecimento indexado.
        Retorna diagnóstico + causa provável + sugestão de ação.
        """
        # Busca código relacionado ao erro nos projetos
        related = self.kb.search(
            f"erro {error_context} {node}",
            n=4,
            project=None
        )

        # Identifica padrão de erro
        severity = "unknown"
        pattern_name = "desconhecido"
        for pattern, name, sev in self.ERROR_PATTERNS:
            if pattern.search(error_context):
                pattern_name = name
                severity     = sev
                break

        # Recupera histórico recente do nó
        recent = self.kb.recall(n=5, node=node, event_type="log_error")

        return {
            "node":          node,
            "error":         error_context[:300],
            "pattern":       pattern_name,
            "severity":      severity,
            "related_code":  related[:2],
            "recent_events": len(recent),
            "diagnosis":     self._build_diagnosis(node, error_context, related, pattern_name),
        }

    def _build_diagnosis(self, node: str, error: str,
                         related: list[dict], pattern: str) -> str:
        """Constrói diagnóstico textual baseado no contexto."""
        parts = [f"Erro detectado no nó {node}: {pattern}."]

        if related:
            proj = related[0].get("project", "")
            file_ = related[0].get("file_path", "")
            parts.append(
                f"O código mais relacionado está em '{proj}/{file_}'. "
                "Verifique esse arquivo primeiro."
            )

        return " ".join(parts)


# =============================================================================
# MOTOR DE AUTONOMIA — propõe e executa ações com supervisão
# =============================================================================

class AutonomyEngine:
    """
    Detecta problemas, propõe soluções via Dashboard/Mobile e executa
    SOMENTE após aprovação explícita do usuário.

    Fluxo:
        1. SituationalAwareness detecta anomalia
        2. IntelligenceEngine diagnostica com RAG
        3. AutonomyEngine.propose() → registra ação pendente no DB
        4. Dashboard exibe o card "Aguardando sua aprovação"
        5. Usuário clica OK (ou diz "Seven, pode executar")
        6. AutonomyEngine.execute_approved() → roda a ação
    """

    # Ações automáticas pré-aprovadas (sem necessidade de OK)
    AUTO_APPROVED_TYPES = {
        "log_rotate",     # rotação de logs
        "tmp_clean",      # limpeza de tmp/
        "health_report",  # relatório de saúde
    }

    def __init__(self, kb: "KnowledgeBase"):
        self.kb = kb

    def propose(self, node: str, action_type: str,
                description: str, command: str,
                auto: bool = False) -> int:
        """
        Propõe uma ação ao usuário.

        Args:
            node:        nó onde a ação será executada
            action_type: tipo ("disk_cleanup", "service_restart", etc.)
            description: explicação em linguagem natural
            command:     comando shell a executar (se aprovado)
            auto:        True = executa sem aprovação (tipos seguros)

        Returns:
            ID da ação pendente
        """
        action_id = self.kb.propose_action(
            node, action_type, description,
            details={"command": command, "auto": auto}
        )

        if auto or action_type in self.AUTO_APPROVED_TYPES:
            self.kb.approve_action(action_id, approved_by="system_auto")
            logger.info(f"[AUTONOMY] Ação auto-aprovada: {action_type} em {node}")

        return action_id

    def get_pending(self) -> list[dict]:
        """Retorna ações aguardando OK do usuário."""
        return self.kb.get_pending_actions()

    def approve_and_execute(self, action_id: int,
                            approved_by: str = "user") -> dict:
        """
        Aprova e executa uma ação pendente.
        NUNCA chame sem autorização explícita do usuário.
        """
        ok = self.kb.approve_action(action_id, approved_by)
        if not ok:
            return {"ok": False, "error": "Ação não encontrada ou já processada."}

        # Recupera detalhes da ação
        try:
            import config as cfg
            conn = sqlite3.connect(cfg.AUTH_DB_PATH.replace("k7auth.db", "episodic.db"))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM pending_actions WHERE id = ?", (action_id,)
            ).fetchone()
            conn.close()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        if not row:
            return {"ok": False, "error": "Ação não encontrada."}

        details = json.loads(row["details"] or "{}")
        command = details.get("command", "")
        node    = row["node"]

        if not command:
            return {"ok": False, "error": "Comando não definido na ação."}

        # Executa
        import engine as eng
        if node == config.NODE_TYPE if 'config' in dir() else "seven":
            result = eng.run_local(command, timeout=60)
        else:
            result = eng.send_node_command(node, "run", {
                "shell":        command,
                "admin_secret": getattr(config, "ADMIN_SECRET", ""),
            })

        # Marca como executada
        try:
            conn = sqlite3.connect(cfg.AUTH_DB_PATH.replace("k7auth.db", "episodic.db"))
            conn.execute(
                "UPDATE pending_actions SET status='executed', executed_at=datetime('now') WHERE id=?",
                (action_id,)
            )
            conn.commit(); conn.close()
        except Exception:
            pass

        return {
            "ok":       result.success,
            "action_id": action_id,
            "command":  command,
            "stdout":   result.stdout[:500],
            "stderr":   result.stderr[:200],
        }


# =============================================================================
# MOTOR DE INTELIGÊNCIA — peça central da v3.0
# =============================================================================

class IntelligenceEngine:
    """
    Orquestra RAG + LLM + Personalidade + Autonomia.

    É o cérebro que:
    - Recebe uma pergunta em linguagem natural
    - Busca contexto nos projetos indexados (RAG)
    - Recupera episódios recentes (memória)
    - Gera resposta com o LLM escolhido
    - Aplica personalidade de Seven ou Spark
    - Entrega para TTS ou Chat UI
    """

    _instance: Optional["IntelligenceEngine"] = None

    def __init__(self, node_type: str = "seven"):
        self.node_type   = node_type
        self.personality = PersonalityLayer(node_type)
        self.session_id  = str(uuid.uuid4())[:8]
        self._kb         = None
        self._awareness  = None
        self._autonomy   = None
        self._llm        = None
        self._init_lock  = threading.Lock()
        logger.info(f"[INTEL] IntelligenceEngine iniciado para nó '{node_type}'")

    @classmethod
    def get(cls, node_type: str = "seven") -> "IntelligenceEngine":
        if cls._instance is None:
            cls._instance = cls(node_type)
        return cls._instance

    def _ensure_ready(self):
        """Inicialização lazy de todos os componentes pesados."""
        if self._kb is not None:
            return
        with self._init_lock:
            if self._kb is not None:
                return

            if _KB_OK:
                self._kb        = KnowledgeBase.get()
                self._awareness = SituationalAwareness(self._kb)
                self._autonomy  = AutonomyEngine(self._kb)
            else:
                logger.warning("[INTEL] KnowledgeBase indisponível — modo degradado.")

            self._llm = self._select_llm()

    def _select_llm(self):
        """Seleciona o melhor LLM disponível."""
        # 1. Tenta Ollama
        try:
            ollama_url   = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            ollama_model = os.environ.get("OLLAMA_MODEL", "llama3")
            backend = OllamaBackend(ollama_url, ollama_model)
            if backend.is_available():
                models = backend.list_models()
                logger.info(f"[INTEL] Usando Ollama ({ollama_model}). Modelos: {models[:3]}")
                return backend
        except Exception:
            pass

        # 2. Tenta Gemini
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if gemini_key:
            backend = GeminiBackend(gemini_key)
            if backend.is_available():
                logger.info("[INTEL] Usando Gemini API.")
                return backend

        # 3. Fallback heurístico
        logger.warning(
            "[INTEL] Nenhum LLM disponível. Usando fallback RAG.\n"
            "  Para ativar Ollama: ollama serve\n"
            "  Para usar Gemini:   export GEMINI_API_KEY=sua_chave"
        )
        return FallbackBackend()

    def _build_system_prompt(self) -> str:
        """Constrói o system prompt com personalidade e contexto do nó."""
        if self.node_type == "seven":
            personality = (
                "Você é Seven, o assistente de desenvolvimento do projeto k7-core. "
                "Sua personalidade é calma, analítica e encorajadora. "
                "Você pensa antes de responder, usa analogias de engenharia e sistemas, "
                "e prefere contextualizar antes de dar a resposta. "
                "Fale em português brasileiro, de forma técnica mas acessível. "
                "Quando detectar um problema, sugira soluções mas sempre consulte o usuário antes de executar."
            )
        else:
            personality = (
                "Você é Spark, o assistente de computação do projeto k7-core. "
                "Sua personalidade é direta, energética e prática. "
                "Vai direto ao ponto, usa frases curtas e propõe ação imediata. "
                "Fale em português brasileiro. "
                "Quando encontrar um problema, já diga como resolver sem enrolação."
            )

        return (
            f"{personality}\n\n"
            "Você tem acesso ao código dos projetos: k7-core, K7 Barber, KSigner, SYNAP e Keryon. "
            "Use o contexto fornecido para dar respostas precisas e relevantes. "
            "Seja conciso — respostas de voz devem ter no máximo 3 parágrafos curtos. "
            "Nunca invente código que não está nos projetos. "
            "Se não souber, diga claramente."
        )

    def _build_rag_prompt(self, question: str, chunks: list[dict],
                          episodes: list[dict]) -> str:
        """Monta o prompt com contexto RAG + memória episódica."""
        # Contexto dos projetos
        context_parts = []
        for i, chunk in enumerate(chunks[:5], 1):
            proj  = chunk.get("project", "?")
            fpath = chunk.get("file_path", "?")
            rel   = chunk.get("relevance", 0)
            content = chunk.get("content", "")[:400]
            context_parts.append(
                f"[{i}] {proj}/{fpath} (relevância: {rel:.2f})\n{content}"
            )

        context_str = "\n---\n".join(context_parts) if context_parts else "Nenhum contexto relevante encontrado."

        # Memória recente
        memory_parts = []
        for ep in episodes[:3]:
            ts      = ep.get("timestamp", "")[:16]
            content = ep.get("content", "")[:100]
            etype   = ep.get("event_type", "")
            memory_parts.append(f"  [{ts}] {etype}: {content}")
        memory_str = "\n".join(memory_parts) if memory_parts else "  (sem interações recentes)"

        return (
            f"CONTEXTO DOS PROJETOS:\n{context_str}\n\n"
            f"MEMÓRIA RECENTE:\n{memory_str}\n\n"
            f"PERGUNTA: {question}\n\n"
            "Responda baseando-se no contexto acima. "
            "Seja específico sobre qual arquivo/projeto está sendo referenciado."
        )

    def chat(self, question: str,
             for_voice: bool = False,
             project_filter: str = None) -> dict:
        """
        Processa uma pergunta e retorna resposta completa.

        Args:
            question:       texto da pergunta
            for_voice:      True = formata para TTS (sem markdown)
            project_filter: busca apenas em um projeto específico

        Returns:
            {
                "answer":   str,        resposta final
                "sources":  list[dict], chunks usados
                "model":    str,        LLM usado
                "latency":  float,      tempo em segundos
                "actions":  list[dict], ações propostas (se houver)
            }
        """
        self._ensure_ready()
        t0 = time.time()

        # 1. Busca RAG
        chunks = []
        if self._kb:
            chunks = self._kb.search(question, n=5, project=project_filter)

        # 2. Recupera memória recente
        episodes = []
        if self._kb:
            episodes = self._kb.recall(n=5)

        # 3. Registra a pergunta como episódio
        if self._kb:
            self._kb.remember(
                self.session_id, self.node_type, "user_question",
                question[:300],
                {"has_context": len(chunks) > 0}
            )

        # 4. Gera resposta com LLM
        system_prompt = self._build_system_prompt()
        rag_prompt    = self._build_rag_prompt(question, chunks, episodes)

        raw_answer = self._llm.generate(
            prompt     = rag_prompt,
            system     = system_prompt,
            max_tokens = 500,
        )

        # 5. Aplica personalidade
        answer = self.personality.wrap(raw_answer)

        # 6. Formata para voz se necessário
        if for_voice:
            answer = self.personality.format_for_voice(answer)

        # 7. Registra resposta como episódio
        if self._kb:
            self._kb.remember(
                self.session_id, self.node_type, "assistant_response",
                answer[:300],
                {"question": question[:100], "sources": len(chunks)}
            )

        # 8. Verifica se há ações pendentes a propor
        pending = []
        if self._autonomy:
            pending = self._autonomy.get_pending()

        model_name = type(self._llm).__name__.replace("Backend", "")

        return {
            "answer":   answer,
            "sources":  chunks[:3],
            "model":    model_name,
            "latency":  round(time.time() - t0, 2),
            "actions":  pending,
            "session":  self.session_id,
        }

    def analyze_node_failure(self, node: str, error_log: str) -> dict:
        """
        Analisa uma falha de nó com contexto RAG.
        Propõe ação de recuperação se disponível.
        """
        self._ensure_ready()

        # Diagnóstico situacional
        diagnosis = {}
        if self._awareness:
            diagnosis = self._awareness.analyze_failure(node, error_log)

        # Pergunta ao LLM com contexto do diagnóstico
        related  = diagnosis.get("related_code", [])
        question = (
            f"O nó {node} apresentou o seguinte erro: {error_log[:200]}. "
            f"Padrão identificado: {diagnosis.get('pattern', 'desconhecido')}. "
            "Qual é a causa mais provável e como resolver?"
        )
        result = self.chat(question, for_voice=False)

        # Propõe ação de recuperação se for algo acionável
        action_id = None
        if self._autonomy:
            pattern = diagnosis.get("pattern", "")
            if "disco cheio" in pattern:
                action_id = self._autonomy.propose(
                    node=node,
                    action_type="disk_cleanup",
                    description=f"Limpar arquivos temporários e logs antigos no nó {node}.",
                    command="find /tmp -mtime +7 -delete && journalctl --vacuum-time=7d",
                )
            elif "falta de memória" in pattern:
                action_id = self._autonomy.propose(
                    node=node,
                    action_type="service_restart",
                    description=f"Reiniciar serviços com alto consumo de memória no nó {node}.",
                    command="systemctl --user restart k7core",
                )

        result["diagnosis"]  = diagnosis
        result["action_id"]  = action_id
        result["node"]       = node
        return result

    def process_voice_command(self, text: str,
                              speak_fn: Callable[[str], None]) -> bool:
        """
        Processa um comando de voz que começa com "Seven/Spark, [pergunta]".
        Retorna True se a pergunta foi processada como conversa (não como comando).
        """
        # Gatilhos de conversa/mentoria
        conversation_triggers = [
            "me fala sobre", "explica", "como funciona", "o que é",
            "me ajuda com", "analisa", "revisa", "o que você acha",
            "como eu faço", "por que", "qual a diferença",
            "me dá uma ideia", "sugere", "o projeto", "o código",
        ]

        lower = text.lower()
        is_conversation = any(t in lower for t in conversation_triggers)

        if not is_conversation:
            return False

        # Processa como conversa
        speak_fn(f"Deixa eu verificar nos projetos...")
        result = self.chat(text, for_voice=True)
        answer = result.get("answer", "Não encontrei informação relevante.")

        if not answer:
            answer = "Não encontrei nada relacionado nos projetos indexados."

        speak_fn(answer)
        return True

    def get_status(self) -> dict:
        """Status do motor de inteligência."""
        self._ensure_ready()
        llm_name = type(self._llm).__name__ if self._llm else "none"
        kb_status = self._kb.status() if self._kb else {}
        return {
            "node":       self.node_type,
            "session":    self.session_id,
            "llm":        llm_name,
            "kb_ready":   bool(self._kb),
            "kb_chunks":  kb_status.get("chroma_chunks", 0),
            "kb_projects":len(kb_status.get("projects", [])),
            "pending_actions": len(self._autonomy.get_pending()) if self._autonomy else 0,
        }
