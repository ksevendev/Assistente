"""Pacote `config` - carregamento de configurações e constantes"""

from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
NODE_ROLE = os.getenv("NODE_ROLE", "worker")

__all__ = ["DATABASE_URL", "NODE_ROLE"]
