# =============================================================================
# k7-core v3.0 | knowledge_base.py
# Script de Indexação de Conhecimento — "O Estudo do Robô"
#
# Este módulo é o PRIMEIRO a executar na v3.0. Ele lê todos os seus
# repositórios de código locais e os transforma em vetores semânticos
# armazenados no ChromaDB. Sem este script, a IA não sabe nada sobre
# seus projetos — com ele, ela pode conversar, analisar e sugerir.
#
# ARQUITETURA DE MEMÓRIA HÍBRIDA:
#   ┌─────────────────────────────────────────────────────────────┐
#   │  SQLite (episódico)     ChromaDB (semântico/vetorial)       │
#   │  ├─ eventos no tempo    ├─ chunks de código indexados       │
#   │  ├─ logs de interação   ├─ README/docs dos projetos         │
#   │  ├─ decisões tomadas    ├─ logs de erros categorizados      │
#   │  └─ contexto de sessão  └─ "o que este arquivo faz"        │
#   └─────────────────────────────────────────────────────────────┘
#
# USO:
#   python knowledge_base.py --index          # indexa todos os projetos
#   python knowledge_base.py --index --force  # reindexação completa
#   python knowledge_base.py --query "como funciona o autenticador"
#   python knowledge_base.py --status         # mostra o que está indexado
#   python knowledge_base.py --watch          # monitora e reindexação auto
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Import condicional de dependências de IA ─────────────────────────────────
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_OK = True
except ImportError:
    _CHROMA_OK = False

try:
    from sentence_transformers import SentenceTransformer
    _ST_OK = True
except ImportError:
    _ST_OK = False

# Importa config do projeto
sys.path.insert(0, str(Path(__file__).parent))
try:
    import config
    BASE_DIR  = config.BASE_DIR
    DATA_DIR  = config.DATA_DIR
except ImportError:
    BASE_DIR  = str(Path(__file__).parent)
    DATA_DIR  = str(Path(__file__).parent / "data")

logger = logging.getLogger("k7.knowledge")

# =============================================================================
# CONFIGURAÇÃO DE INDEXAÇÃO
# =============================================================================

# Extensões de arquivo que serão indexadas
INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".scss", ".vue",
    ".md", ".txt", ".rst",
    ".json", ".yaml", ".yml", ".toml",
    ".sh", ".bash", ".zsh",
    ".sql", ".env.example",
    ".dockerfile", "dockerfile",
    ".gitignore", ".editorconfig",
}

# Diretórios ignorados na varredura
SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".next", ".nuxt", "dist", "build", ".cache", ".tox",
    "coverage", ".pytest_cache", "eggs", ".eggs",
    "htmlcov", ".mypy_cache", ".ruff_cache",
}

# Tamanho máximo de arquivo para indexar (bytes)
MAX_FILE_SIZE = 200_000   # 200 KB

# Tamanho de cada chunk (caracteres)
CHUNK_SIZE    = 1_200
CHUNK_OVERLAP = 200

# Modelo de embeddings — leve, offline, funciona sem GPU
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # 90 MB, 384 dims, rápido

# Coleção no ChromaDB
COLLECTION_NAME = "k7_knowledge"


# =============================================================================
# ESTRUTURAS DE DADOS
# =============================================================================

@dataclass
class IndexedChunk:
    """Um pedaço de código/texto indexado no ChromaDB."""
    chunk_id:    str          # hash único do conteúdo
    project:     str          # "k7-barber", "ksigner", etc.
    file_path:   str          # caminho relativo à raiz do projeto
    file_type:   str          # extensão sem ponto
    content:     str          # texto do chunk
    start_line:  int          # linha de início no arquivo
    end_line:    int          # linha de fim
    summary:     str          # resumo automático gerado
    indexed_at:  str          = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProjectConfig:
    """Configuração de um projeto a ser indexado."""
    name:         str          # nome legível
    path:         str          # caminho absoluto no disco
    description:  str          # descrição do projeto
    tech_stack:   list[str]    # tecnologias usadas
    priority:     int   = 1    # 1=alta, 2=média, 3=baixa
    enabled:      bool  = True


# =============================================================================
# PROJETOS CONHECIDOS — Edite aqui para adicionar seus repositórios
# =============================================================================

def get_project_configs() -> list[ProjectConfig]:
    """
    Retorna a lista de projetos a serem indexados.
    Adicione seus projetos aqui. O caminho pode ser absoluto ou
    relativo a HOME (~).
    """
    home = str(Path.home())
    return [
        ProjectConfig(
            name="k7-core",
            path=BASE_DIR,
            description="Ecossistema de assistência virtual distribuída em rede local. Flask, mDNS, Python.",
            tech_stack=["python", "flask", "zeroconf", "sqlite", "chromadb"],
            priority=1,
        ),
        ProjectConfig(
            name="K7 Barber",
            path=os.path.join(home, "projetos/k7-barber"),
            description="Sistema de agendamento para barbearia. Clientes, serviços, horários e pagamentos.",
            tech_stack=["python", "django", "postgresql", "redis", "celery"],
            priority=1,
        ),
        ProjectConfig(
            name="KSigner",
            path=os.path.join(home, "projetos/ksigner"),
            description="Plataforma de assinatura digital e gestão de documentos eletrônicos.",
            tech_stack=["python", "fastapi", "jwt", "cryptography", "postgresql"],
            priority=1,
        ),
        ProjectConfig(
            name="SYNAP",
            path=os.path.join(home, "projetos/synap"),
            description="Sistema de neurologia e análise de padrões. Processamento de dados médicos.",
            tech_stack=["python", "numpy", "pandas", "scikit-learn", "pytorch"],
            priority=2,
        ),
        ProjectConfig(
            name="Keryon",
            path=os.path.join(home, "projetos/keryon"),
            description="Framework de automação e orquestração de tarefas distribuídas.",
            tech_stack=["python", "asyncio", "redis", "celery", "docker"],
            priority=2,
        ),
    ]


# =============================================================================
# EPISODIC STORE — SQLite para memória temporal e eventos
# =============================================================================

class EpisodicStore:
    """
    Banco de memória episódica em SQLite.
    Armazena eventos no tempo, interações e contexto de sessão.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
                    node        TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    metadata    TEXT DEFAULT '{}',
                    resolved    INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS file_index (
                    file_hash   TEXT PRIMARY KEY,
                    project     TEXT NOT NULL,
                    file_path   TEXT NOT NULL,
                    indexed_at  TEXT NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    file_size   INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS project_stats (
                    project         TEXT PRIMARY KEY,
                    last_indexed    TEXT,
                    total_files     INTEGER DEFAULT 0,
                    total_chunks    INTEGER DEFAULT 0,
                    total_bytes     INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS pending_actions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    node        TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    details     TEXT DEFAULT '{}',
                    status      TEXT DEFAULT 'pending',
                    approved_by TEXT,
                    approved_at TEXT,
                    executed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_episodes_session   ON episodes(session_id);
                CREATE INDEX IF NOT EXISTS idx_episodes_type      ON episodes(event_type);
                CREATE INDEX IF NOT EXISTS idx_episodes_node      ON episodes(node);
                CREATE INDEX IF NOT EXISTS idx_pending_status     ON pending_actions(status);
            """)

    def log_episode(self, session_id: str, node: str, event_type: str,
                    content: str, metadata: dict = None) -> int:
        """Registra um episódio na memória temporal."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO episodes (session_id, node, event_type, content, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, node, event_type, content,
                 json.dumps(metadata or {}))
            )
            return cur.lastrowid

    def get_recent_episodes(self, n: int = 20, node: str = None,
                            event_type: str = None) -> list[dict]:
        """Recupera episódios recentes para contexto de conversa."""
        clauses, params = [], []
        if node:
            clauses.append("node = ?"); params.append(node)
        if event_type:
            clauses.append("event_type = ?"); params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM episodes {where} ORDER BY id DESC LIMIT ?",
                params + [n]
            ).fetchall()
        return [dict(r) for r in rows]

    def register_file(self, file_hash: str, project: str, file_path: str,
                      chunk_count: int, file_size: int):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO file_index
                   (file_hash, project, file_path, indexed_at, chunk_count, file_size)
                   VALUES (?, ?, ?, datetime('now'), ?, ?)""",
                (file_hash, project, file_path, chunk_count, file_size)
            )

    def is_file_indexed(self, file_hash: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM file_index WHERE file_hash = ?", (file_hash,)
            ).fetchone()
        return row is not None

    def update_project_stats(self, project: str, files: int, chunks: int, bytes_: int):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO project_stats
                   (project, last_indexed, total_files, total_chunks, total_bytes)
                   VALUES (?, datetime('now'), ?, ?, ?)""",
                (project, files, chunks, bytes_)
            )

    def get_project_stats(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM project_stats ORDER BY project").fetchall()
        return [dict(r) for r in rows]

    def add_pending_action(self, node: str, action_type: str,
                           description: str, details: dict = None) -> int:
        """Registra uma ação que aguarda aprovação do usuário."""
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO pending_actions
                   (node, action_type, description, details)
                   VALUES (?, ?, ?, ?)""",
                (node, action_type, description, json.dumps(details or {}))
            )
            return cur.lastrowid

    def approve_action(self, action_id: int, approved_by: str) -> bool:
        with self._conn() as conn:
            conn.execute(
                """UPDATE pending_actions
                   SET status='approved', approved_by=?, approved_at=datetime('now')
                   WHERE id=? AND status='pending'""",
                (approved_by, action_id)
            )
            return conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0

    def get_pending_actions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_actions WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]


# =============================================================================
# SEMANTIC STORE — ChromaDB para busca vetorial
# =============================================================================

class SemanticStore:
    """
    Armazenamento vetorial com ChromaDB + sentence-transformers.
    Permite busca semântica: "encontre código sobre autenticação JWT"
    retorna os chunks mais relevantes mesmo sem palavras exatas.
    """

    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self._client   = None
        self._collection = None
        self._model    = None
        self._lock     = threading.Lock()

    def _lazy_init(self):
        """Inicialização lazy — carrega modelos apenas quando necessário."""
        if self._client is not None:
            return

        if not _CHROMA_OK:
            raise ImportError(
                "ChromaDB não instalado. Execute: pip install chromadb"
            )
        if not _ST_OK:
            raise ImportError(
                "sentence-transformers não instalado. "
                "Execute: pip install sentence-transformers"
            )

        logger.info(f"[KB] Inicializando ChromaDB em {self.persist_dir}...")
        os.makedirs(self.persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False)
        )

        logger.info(f"[KB] Carregando modelo de embeddings: {EMBEDDING_MODEL}...")
        self._model = SentenceTransformer(EMBEDDING_MODEL)

        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[KB] Coleção '{COLLECTION_NAME}' pronta. "
                    f"Documentos: {self._collection.count()}")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings para uma lista de textos."""
        return self._model.encode(texts, show_progress_bar=False).tolist()

    def add_chunks(self, chunks: list[IndexedChunk]) -> int:
        """Adiciona chunks ao índice vetorial."""
        if not chunks:
            return 0

        with self._lock:
            self._lazy_init()

            ids        = [c.chunk_id for c in chunks]
            documents  = [c.content for c in chunks]
            metadatas  = [
                {
                    "project":    c.project,
                    "file_path":  c.file_path,
                    "file_type":  c.file_type,
                    "start_line": c.start_line,
                    "end_line":   c.end_line,
                    "summary":    c.summary,
                    "indexed_at": c.indexed_at,
                }
                for c in chunks
            ]

            # Remove IDs que já existem para evitar duplicatas
            existing = set(self._collection.get(ids=ids)["ids"])
            new_chunks = [
                (i, d, m) for i, d, m in zip(ids, documents, metadatas)
                if i not in existing
            ]

            if not new_chunks:
                return 0

            n_ids, n_docs, n_metas = zip(*new_chunks)
            embeddings = self._embed(list(n_docs))

            self._collection.add(
                ids=list(n_ids),
                documents=list(n_docs),
                embeddings=embeddings,
                metadatas=list(n_metas),
            )
            return len(new_chunks)

    def query(self, question: str, n_results: int = 6,
              project_filter: str = None) -> list[dict]:
        """
        Busca semântica: retorna os chunks mais relevantes para a pergunta.

        Args:
            question:       texto da pergunta em linguagem natural
            n_results:      quantos resultados retornar
            project_filter: filtrar por projeto específico

        Returns:
            Lista de dicts com content, metadata e distance
        """
        with self._lock:
            self._lazy_init()

            where = {"project": project_filter} if project_filter else None
            embedding = self._embed([question])[0]

            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=min(n_results, self._collection.count() or 1),
                where=where,
                include=["documents", "metadatas", "distances"],
            )

        if not results["ids"][0]:
            return []

        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "content":    doc,
                "project":    meta.get("project"),
                "file_path":  meta.get("file_path"),
                "file_type":  meta.get("file_type"),
                "start_line": meta.get("start_line"),
                "end_line":   meta.get("end_line"),
                "summary":    meta.get("summary"),
                "relevance":  round(1 - dist, 3),  # 1=perfeito, 0=irrelevante
            })

        return sorted(output, key=lambda x: x["relevance"], reverse=True)

    def count(self) -> int:
        """Total de chunks indexados."""
        with self._lock:
            self._lazy_init()
            return self._collection.count()

    def delete_project(self, project: str) -> int:
        """Remove todos os chunks de um projeto (para reindexação)."""
        with self._lock:
            self._lazy_init()
            results = self._collection.get(where={"project": project})
            ids = results["ids"]
            if ids:
                self._collection.delete(ids=ids)
            return len(ids)


# =============================================================================
# INDEXADOR — lê repositórios e gera chunks
# =============================================================================

class RepositoryIndexer:
    """
    Varre repositórios de código, divide em chunks e os envia ao SemanticStore.
    """

    def __init__(self, semantic: SemanticStore, episodic: EpisodicStore):
        self.semantic = semantic
        self.episodic = episodic

    def _file_hash(self, content: str, path: str) -> str:
        """Hash único baseado no conteúdo + caminho."""
        data = f"{path}:{content}"
        return hashlib.sha256(data.encode()).hexdigest()[:24]

    def _chunk_text(self, text: str, file_path: str,
                    start_line: int = 0) -> list[tuple[str, int, int]]:
        """
        Divide um texto em chunks com overlap.
        Retorna: [(chunk_text, start_line, end_line), ...]
        """
        lines   = text.split('\n')
        chunks  = []
        i       = 0
        chars   = 0
        chunk_lines: list[str] = []
        chunk_start = start_line

        for line_num, line in enumerate(lines, start_line):
            chars += len(line) + 1
            chunk_lines.append(line)

            if chars >= CHUNK_SIZE:
                chunk_text = '\n'.join(chunk_lines).strip()
                if chunk_text:
                    chunks.append((chunk_text, chunk_start, line_num))

                # Overlap: mantém as últimas N chars
                overlap_text = chunk_text[-CHUNK_OVERLAP:]
                overlap_lines = overlap_text.split('\n')
                chunk_lines = overlap_lines
                chars       = sum(len(l) + 1 for l in chunk_lines)
                chunk_start = line_num - len(overlap_lines) + 1

        # Chunk final
        if chunk_lines:
            chunk_text = '\n'.join(chunk_lines).strip()
            if chunk_text:
                chunks.append((chunk_text, chunk_start, start_line + len(lines) - 1))

        return chunks

    def _generate_summary(self, content: str, file_path: str, project: str) -> str:
        """
        Gera um resumo textual curto do chunk.
        (Heurística simples — sem LLM aqui para manter o script leve.)
        """
        ext  = Path(file_path).suffix.lower()
        name = Path(file_path).stem

        # Extrai primeira docstring/comentário
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        summary_lines = []

        for line in lines[:5]:
            if line.startswith(('"""', "'''", '#', '//', '/*', '*')):
                clean = re.sub(r'^[#\'"*/\s]+', '', line).strip()
                if len(clean) > 10:
                    summary_lines.append(clean)
                    break

        # Extrai definições de funções/classes
        definitions = []
        for line in lines:
            m = re.match(r'^(def |class |function |async def |const |let |var )', line)
            if m:
                definitions.append(line[:80])
                if len(definitions) >= 3:
                    break

        parts = [f"[{project}/{name}{ext}]"]
        if summary_lines:
            parts.append(summary_lines[0][:120])
        if definitions:
            parts.append("Contém: " + "; ".join(d[:50] for d in definitions))

        return " — ".join(parts)[:300]

    def _should_index_file(self, path: Path) -> bool:
        """Retorna True se o arquivo deve ser indexado."""
        if path.stat().st_size > MAX_FILE_SIZE:
            return False
        if path.suffix.lower() in INDEXABLE_EXTENSIONS:
            return True
        if path.name.lower() in INDEXABLE_EXTENSIONS:
            return True
        return False

    def index_project(self, project: ProjectConfig,
                      force: bool = False) -> tuple[int, int, int]:
        """
        Indexa um projeto completo.

        Returns:
            (files_indexed, chunks_added, files_skipped)
        """
        root = Path(project.path)
        if not root.exists():
            logger.warning(f"[KB] Projeto '{project.name}' não encontrado: {root}")
            return 0, 0, 0

        logger.info(f"[KB] Indexando projeto '{project.name}' em {root}...")

        files_indexed  = 0
        chunks_added   = 0
        files_skipped  = 0
        total_bytes    = 0
        batch: list[IndexedChunk] = []

        # Adiciona contexto do projeto como primeiro chunk
        project_context = (
            f"PROJETO: {project.name}\n"
            f"DESCRIÇÃO: {project.description}\n"
            f"TECNOLOGIAS: {', '.join(project.tech_stack)}\n"
            f"CAMINHO: {project.path}"
        )
        batch.append(IndexedChunk(
            chunk_id   = f"ctx_{project.name.lower().replace(' ', '_')}",
            project    = project.name,
            file_path  = "_project_context",
            file_type  = "meta",
            content    = project_context,
            start_line = 0,
            end_line   = 4,
            summary    = f"Contexto do projeto {project.name}",
        ))

        # Varre arquivos
        for file_path in sorted(root.rglob("*")):
            # Pula diretórios e arquivos não elegíveis
            if file_path.is_dir():
                if file_path.name in SKIP_DIRS:
                    continue
                continue

            # Verifica se algum parent está em SKIP_DIRS
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue

            if not self._should_index_file(file_path):
                continue

            try:
                content   = file_path.read_text(encoding="utf-8", errors="ignore")
                file_size = file_path.stat().st_size
                rel_path  = str(file_path.relative_to(root))
                file_hash = self._file_hash(content, rel_path)

                if not force and self.episodic.is_file_indexed(file_hash):
                    files_skipped += 1
                    continue

                # Divide em chunks
                raw_chunks = self._chunk_text(content, rel_path)
                file_chunks = []

                for chunk_text, start_ln, end_ln in raw_chunks:
                    chunk_id = f"{file_hash}_{start_ln}"
                    summary  = self._generate_summary(chunk_text, rel_path, project.name)
                    file_chunks.append(IndexedChunk(
                        chunk_id   = chunk_id,
                        project    = project.name,
                        file_path  = rel_path,
                        file_type  = file_path.suffix.lstrip('.') or file_path.name,
                        content    = chunk_text,
                        start_line = start_ln,
                        end_line   = end_ln,
                        summary    = summary,
                    ))

                batch.extend(file_chunks)

                # Flush em batches de 50
                if len(batch) >= 50:
                    added = self.semantic.add_chunks(batch)
                    chunks_added += added
                    batch = []

                self.episodic.register_file(
                    file_hash, project.name, rel_path,
                    len(file_chunks), file_size
                )
                files_indexed += 1
                total_bytes   += file_size

                logger.debug(f"[KB]   ✓ {rel_path} ({len(file_chunks)} chunks)")

            except Exception as exc:
                logger.error(f"[KB] Erro ao indexar {file_path}: {exc}")

        # Flush final
        if batch:
            added = self.semantic.add_chunks(batch)
            chunks_added += added

        self.episodic.update_project_stats(
            project.name, files_indexed, chunks_added, total_bytes
        )

        logger.info(
            f"[KB] '{project.name}' concluído: "
            f"{files_indexed} arquivos, {chunks_added} chunks novos, "
            f"{files_skipped} já indexados."
        )
        return files_indexed, chunks_added, files_skipped


# =============================================================================
# KNOWLEDGE BASE — fachada principal usada por intelligence.py
# =============================================================================

class KnowledgeBase:
    """
    Fachada unificada que expõe SemanticStore + EpisodicStore.
    É a interface que intelligence.py e core.py usam.
    """

    _instance: Optional["KnowledgeBase"] = None

    def __init__(self):
        self.semantic = SemanticStore(
            persist_dir=os.path.join(DATA_DIR, "chroma")
        )
        self.episodic = EpisodicStore(
            db_path=os.path.join(DATA_DIR, "episodic.db")
        )
        self.indexer  = RepositoryIndexer(self.semantic, self.episodic)
        self._ready   = False
        logger.info("[KB] KnowledgeBase instanciada.")

    @classmethod
    def get(cls) -> "KnowledgeBase":
        """Singleton lazy."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def index_all(self, force: bool = False) -> dict:
        """Indexa todos os projetos configurados."""
        projects = get_project_configs()
        results  = {}
        for proj in projects:
            if not proj.enabled:
                continue
            path = Path(proj.path)
            if not path.exists():
                logger.warning(f"[KB] Pulando '{proj.name}' — caminho não existe: {path}")
                results[proj.name] = {"status": "not_found", "path": str(path)}
                continue
            files, chunks, skipped = self.indexer.index_project(proj, force=force)
            results[proj.name] = {
                "status":  "ok",
                "files":   files,
                "chunks":  chunks,
                "skipped": skipped,
            }
        self._ready = True
        return results

    def search(self, query: str, n: int = 6,
               project: str = None) -> list[dict]:
        """Busca semântica na base de conhecimento."""
        if not _CHROMA_OK or not _ST_OK:
            return []
        try:
            return self.semantic.query(query, n_results=n, project_filter=project)
        except Exception as exc:
            logger.error(f"[KB] Erro na busca: {exc}")
            return []

    def remember(self, session_id: str, node: str, event_type: str,
                 content: str, metadata: dict = None):
        """Grava um episódio na memória temporal."""
        self.episodic.log_episode(session_id, node, event_type, content, metadata)

    def recall(self, n: int = 10, node: str = None,
               event_type: str = None) -> list[dict]:
        """Recupera episódios recentes para contexto."""
        return self.episodic.get_recent_episodes(n=n, node=node, event_type=event_type)

    def propose_action(self, node: str, action_type: str,
                       description: str, details: dict = None) -> int:
        """Propõe uma ação que aguarda aprovação do usuário."""
        return self.episodic.add_pending_action(node, action_type, description, details)

    def get_pending_actions(self) -> list[dict]:
        """Retorna ações aguardando aprovação."""
        return self.episodic.get_pending_actions()

    def approve_action(self, action_id: int, approved_by: str = "user") -> bool:
        """Aprova uma ação pendente."""
        return self.episodic.approve_action(action_id, approved_by)

    def status(self) -> dict:
        """Retorna estatísticas da base de conhecimento."""
        stats = self.episodic.get_project_stats()
        total_chunks = sum(s.get("total_chunks", 0) for s in stats)
        chroma_count = 0
        try:
            chroma_count = self.semantic.count()
        except Exception:
            pass
        return {
            "projects":      stats,
            "total_chunks":  total_chunks,
            "chroma_chunks": chroma_count,
            "chroma_ok":     _CHROMA_OK,
            "embeddings_ok": _ST_OK,
            "ready":         self._ready,
        }


# =============================================================================
# CLI — uso direto do script
# =============================================================================

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_status(kb: KnowledgeBase):
    st = kb.status()
    print(f"\n{'━'*60}")
    print(f"  k7-core | Base de Conhecimento — Status")
    print(f"{'━'*60}")
    print(f"  ChromaDB:         {'✓ disponível' if st['chroma_ok'] else '✗ não instalado'}")
    print(f"  Sentence-Trans:   {'✓ disponível' if st['embeddings_ok'] else '✗ não instalado'}")
    print(f"  Chunks (chroma):  {st['chroma_chunks']}")
    print(f"\n  {'Projeto':<20} {'Arquivos':>8} {'Chunks':>8} {'Última indexação'}")
    print(f"  {'─'*55}")
    for p in st["projects"]:
        print(f"  {p['project']:<20} {p.get('total_files',0):>8} "
              f"{p.get('total_chunks',0):>8}  {p.get('last_indexed','—')[:16]}")
    print()


def main():
    _setup_logging()
    os.makedirs(DATA_DIR, exist_ok=True)

    parser = argparse.ArgumentParser(
        description="k7-core v3.0 — Indexador de Base de Conhecimento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python knowledge_base.py --index           # indexa projetos novos/modificados
  python knowledge_base.py --index --force   # reindexação completa
  python knowledge_base.py --query "como funciona o login do KSigner"
  python knowledge_base.py --status          # relatório de indexação
  python knowledge_base.py --watch           # monitora e reindexação auto
        """
    )
    parser.add_argument("--index",  action="store_true", help="Indexa projetos")
    parser.add_argument("--force",  action="store_true", help="Força reindexação de tudo")
    parser.add_argument("--query",  type=str,            help="Faz uma busca semântica")
    parser.add_argument("--status", action="store_true", help="Mostra status da base")
    parser.add_argument("--watch",  action="store_true", help="Reindexação automática (5 min)")
    parser.add_argument("--project", type=str,           help="Filtra por projeto (--query)")
    args = parser.parse_args()

    if not any([args.index, args.query, args.status, args.watch]):
        parser.print_help()
        return

    if not _CHROMA_OK or not _ST_OK:
        print("\n⚠  Dependências de IA não instaladas.")
        print("   Execute: pip install chromadb sentence-transformers\n")

    kb = KnowledgeBase.get()

    if args.status:
        _print_status(kb)

    if args.index:
        print("\n━━━ Iniciando indexação de conhecimento ━━━\n")
        results = kb.index_all(force=args.force)
        print("\n━━━ Resultado ━━━")
        for name, r in results.items():
            if r.get("status") == "not_found":
                print(f"  ✗  {name:<20} — caminho não encontrado: {r['path']}")
            else:
                print(f"  ✓  {name:<20} "
                      f"{r['files']:>4} arquivos  "
                      f"{r['chunks']:>6} chunks novos  "
                      f"{r['skipped']:>4} já indexados")
        _print_status(kb)

    if args.query:
        print(f"\n━━━ Buscando: \"{args.query}\" ━━━\n")
        results = kb.search(args.query, n=5, project=args.project)
        if not results:
            print("  Nenhum resultado encontrado.")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['project']}/{r['file_path']} "
                  f"L{r['start_line']}-{r['end_line']} "
                  f"(relevância: {r['relevance']})")
            print(f"      {r['summary']}")
            if args.query:
                # Exibe snippet do conteúdo
                snippet = r['content'][:200].replace('\n', ' ')
                print(f"      ↳ {snippet}...")
            print()

    if args.watch:
        interval = 300  # 5 minutos
        print(f"\n━━━ Modo monitoramento (reindexação a cada {interval}s) ━━━")
        print("      Ctrl+C para parar.\n")
        while True:
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Verificando projetos...")
                kb.index_all(force=False)
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\nMonitoramento encerrado.")
                break


if __name__ == "__main__":
    main()
