"""Modelos SQLAlchemy assíncronos para K'Seven V3.

Contém: Node, Telemetry, AuditLog, KnowledgeBase, ApiKey
"""
import datetime
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Float,
    Boolean,
    Text,
    ForeignKey,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .connection import Base

try:
    from pgvector.sqlalchemy import Vector
except Exception:
    Vector = None


class Node(Base):
    __tablename__ = "nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False, default="worker")
    address = Column(String(256), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(UUID(as_uuid=True), ForeignKey("nodes.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    cpu = Column(Float, nullable=True)
    memory = Column(Float, nullable=True)
    disk = Column(Float, nullable=True)
    network = Column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(128), nullable=True)
    action = Column(String(256), nullable=False)
    details = Column(JSON, nullable=True)
    ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, nullable=True)
    # embedding vector column (pgvector) — optional
    if Vector is not None:
        embedding = Column(Vector(1536), nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    key = Column(String(256), nullable=False, unique=True, index=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
