#!/usr/bin/env python3
# =============================================================================
# k7-core | manage_auth.py
# CLI para gerenciar usuários do dashboard (criar, listar, resetar senha).
#
# Uso:
#   python manage_auth.py --create-user
#   python manage_auth.py --list-users
#   python manage_auth.py --reset-password USERNAME
#   python manage_auth.py --delete-user USERNAME
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime

# Deve ser executado no mesmo diretório do projeto
sys.path.insert(0, ".")
import config
from werkzeug.security import generate_password_hash, check_password_hash


def _db():
    conn = sqlite3.connect(config.AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_tables():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role     TEXT NOT NULL DEFAULT 'master',
                created  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT NOT NULL,
                action    TEXT NOT NULL,
                detail    TEXT,
                ip        TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

def cmd_create_user(args):
    _ensure_tables()
    print("\n── Criar novo usuário ──")
    username = input("Username: ").strip()
    if not username:
        print("Username não pode ser vazio."); return
    pw1 = getpass.getpass("Senha: ")
    pw2 = getpass.getpass("Confirmar senha: ")
    if pw1 != pw2:
        print("Senhas não conferem."); return
    if len(pw1) < 6:
        print("Senha deve ter no mínimo 6 caracteres."); return
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?,?)",
                (username, generate_password_hash(pw1))
            )
        print(f"✓ Usuário '{username}' criado.")
    except sqlite3.IntegrityError:
        print(f"Usuário '{username}' já existe.")

def cmd_list_users(args):
    _ensure_tables()
    with _db() as conn:
        rows = conn.execute("SELECT id, username, role, created FROM users ORDER BY id").fetchall()
    if not rows:
        print("Nenhum usuário cadastrado.")
        return
    print(f"\n{'ID':<4} {'Username':<20} {'Role':<10} {'Criado'}")
    print("─" * 54)
    for r in rows:
        print(f"{r['id']:<4} {r['username']:<20} {r['role']:<10} {r['created']}")

def cmd_reset_password(args):
    _ensure_tables()
    username = args.username
    with _db() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        print(f"Usuário '{username}' não encontrado."); return
    pw1 = getpass.getpass(f"Nova senha para '{username}': ")
    pw2 = getpass.getpass("Confirmar: ")
    if pw1 != pw2:
        print("Senhas não conferem."); return
    if len(pw1) < 6:
        print("Senha deve ter no mínimo 6 caracteres."); return
    with _db() as conn:
        conn.execute("UPDATE users SET password=? WHERE username=?",
                     (generate_password_hash(pw1), username))
    print(f"✓ Senha de '{username}' alterada.")

def cmd_delete_user(args):
    _ensure_tables()
    username = args.username
    confirm  = input(f"Deletar '{username}'? [s/N] ").strip().lower()
    if confirm != "s":
        print("Operação cancelada."); return
    with _db() as conn:
        r = conn.execute("DELETE FROM users WHERE username=?", (username,))
    if r.rowcount:
        print(f"✓ Usuário '{username}' removido.")
    else:
        print(f"Usuário '{username}' não encontrado.")

def cmd_audit(args):
    _ensure_tables()
    with _db() as conn:
        rows = conn.execute(
            "SELECT timestamp, username, action, detail, ip FROM audit_log "
            "ORDER BY id DESC LIMIT 50"
        ).fetchall()
    if not rows:
        print("Audit log vazio."); return
    print(f"\n{'Timestamp':<20} {'User':<12} {'Action':<20} {'Detail'}")
    print("─" * 72)
    for r in rows:
        detail = (r['detail'] or '')[:30]
        print(f"{r['timestamp']:<20} {r['username']:<12} {r['action']:<20} {detail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="k7-core Auth Manager")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("create-user",  help="Cria novo usuário")
    sub.add_parser("list-users",   help="Lista usuários")
    sub.add_parser("audit",        help="Exibe audit log (últimas 50 entradas)")

    p_reset = sub.add_parser("reset-password", help="Redefine senha")
    p_reset.add_argument("username")

    p_del = sub.add_parser("delete-user", help="Remove usuário")
    p_del.add_argument("username")

    args = parser.parse_args()

    dispatch = {
        "create-user":    cmd_create_user,
        "list-users":     cmd_list_users,
        "reset-password": cmd_reset_password,
        "delete-user":    cmd_delete_user,
        "audit":          cmd_audit,
    }

    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    dispatch[args.cmd](args)
