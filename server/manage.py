#!/usr/bin/env python3
"""
客户端管理 CLI — 注册新客户端并生成 API Key。

使用方式:
    python -m server.manage register-client <client_id> <name>
    python -m server.manage list-clients
    python -m server.manage revoke-client <client_id>
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.auth import generate_api_key, hash_api_key
from server.db import DEFAULT_DB_PATH, init_db


def cmd_register(args):
    """注册新客户端，打印 API Key（仅此一次显示，请妥善保管）。"""
    conn = init_db(args.db)
    api_key = generate_api_key()
    hashed = hash_api_key(api_key)

    ok = True
    try:
        conn.execute(
            "INSERT INTO clients (id, name, api_key_hash) VALUES (?, ?, ?)",
            (args.client_id, args.name, hashed),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"错误: 客户端 '{args.client_id}' 已存在", file=sys.stderr)
        ok = False

    conn.close()

    if ok:
        print(f"客户端注册成功!")
        print(f"  Client ID : {args.client_id}")
        print(f"  Name      : {args.name}")
        print(f"  API Key   : {api_key}")
        print()
        print("请妥善保管 API Key — 它不会再次显示。")
        print()
        print("客户端环境变量配置:")
        print(f'  export OPENCLAW_SERVER_URL="http://<server>:8000"')
        print(f'  export OPENCLAW_CLIENT_ID="{args.client_id}"')
        print(f'  export OPENCLAW_API_KEY="{api_key}"')


def cmd_list(args):
    """列出所有已注册的客户端。"""
    conn = init_db(args.db)
    rows = conn.execute(
        "SELECT id, name, created_at FROM clients ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("(无已注册客户端)")
        return

    print(f"{'Client ID':<25} {'Name':<20} {'Created At'}")
    print("-" * 65)
    for r in rows:
        print(f"{r['id']:<25} {r['name']:<20} {r['created_at']}")


def cmd_revoke(args):
    """撤销客户端（删除客户端及其所有遥测记录）。"""
    conn = init_db(args.db)
    # 先检查是否存在
    row = conn.execute("SELECT id, name FROM clients WHERE id = ?", (args.client_id,)).fetchone()
    if not row:
        print(f"错误: 客户端 '{args.client_id}' 不存在", file=sys.stderr)
        conn.close()
        return

    conn.execute("DELETE FROM clients WHERE id = ?", (args.client_id,))
    conn.commit()
    conn.close()
    print(f"已撤销客户端: {row['id']} ({row['name']})")
    print("关联的遥测记录已自动级联删除。")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Monitor 客户端管理")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help=f"SQLite 数据库路径 (默认: {DEFAULT_DB_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_reg = sub.add_parser("register-client", help="注册新客户端")
    p_reg.add_argument("client_id", help="客户端唯一标识 (e.g. laptop-mac-01)")
    p_reg.add_argument("name", help="可读名称 (e.g. 'MacBook Pro')")
    p_reg.set_defaults(func=cmd_register)

    p_list = sub.add_parser("list-clients", help="列出所有客户端")
    p_list.set_defaults(func=cmd_list)

    p_rev = sub.add_parser("revoke-client", help="撤销客户端")
    p_rev.add_argument("client_id", help="要撤销的客户端 ID")
    p_rev.set_defaults(func=cmd_revoke)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
