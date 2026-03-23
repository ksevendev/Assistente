"""Conexão assíncrona com PostgreSQL usando SQLAlchemy async.

Observações:
- Lê `DATABASE_URL` do arquivo .env via python-dotenv.
- Usa `asyncpg` como driver async para SQLAlchemy.
- Fornece retry exponencial na inicialização.
"""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://kseven:kseven@localhost:5432/kseven_db",
)

logger = logging.getLogger("kseven.database")


Base = declarative_base()


def _create_engine() -> AsyncEngine:
    return create_async_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


engine = _create_engine()
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _try_connect(max_retries: int = 5, base_delay: float = 1.0):
    attempt = 0
    delay = base_delay
    while True:
        try:
            async with engine.begin() as conn:
                # Apenas um teste simples de conexão
                await conn.run_sync(lambda sync_conn: None)
            logger.info("Conectado ao banco de dados com sucesso.")
            return
        except Exception as e:
            attempt += 1
            logger.warning("Falha na conexão ao banco (attempt %s): %s", attempt, e)
            if attempt >= max_retries:
                logger.exception("Número máximo de tentativas atingido.")
                raise
            await asyncio.sleep(delay)
            delay *= 2


async def init_db(max_retries: int = 5):
    """Inicializa a conexão e cria as tabelas declaradas em `Base`.

    Usa retry exponencial para suportar Workers com conexão instável.
    """
    await _try_connect(max_retries=max_retries)
    # Cria tabelas (se houver modelos ligados ao Base)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
