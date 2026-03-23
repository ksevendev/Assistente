"""Pacote `database` agrupa conexões e modelos"""

from . import connection

# Importa modelos para garantir que `Base.metadata` os conheça
try:
	from . import models  # noqa: F401
except Exception:
	models = None

__all__ = ["connection", "models"]
