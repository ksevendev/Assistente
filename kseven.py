#!/usr/bin/env python3
"""CLI inicial do K'Seven V3"""
import asyncio
import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer()


@app.command()
def initdb():
    """Inicializa o banco de dados (cria tabelas)"""
    from database.connection import init_db

    asyncio.run(init_db())
    print("Banco de dados inicializado.")


@app.command()
def run(host: str = "0.0.0.0", port: int = 8000):
    """Roda a API FastAPI via Uvicorn (desenvolvimento)"""
    import uvicorn

    print("K'Seven V3 — iniciando (Master: Seven — Cyan)")
    uvicorn.run("api.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    app()
