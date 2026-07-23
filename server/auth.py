"""
认证模块 — API Key 的创建、哈希、验证。

使用 bcrypt 进行单向哈希存储，客户端持有明文 key，服务端只存哈希。
即使数据库泄露，攻击者也无法还原原始 API Key。

认证流程:
  1. 管理员通过 manage.py 注册客户端，获得明文 API Key
  2. 客户端在请求头中携带 X-Client-Id + X-Api-Key
  3. require_auth 依赖从 DB 取出哈希值，bcrypt.checkpw 验证
"""

from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, Header, HTTPException

from server.db import DEFAULT_DB_PATH, get_client_api_key_hash


def generate_api_key() -> str:
    """生成安全的随机 API Key (40 字符, hex)。

    格式: owc_<32 hex chars> = 总共 36 字符
    owc = OpenClaw 前缀，方便日志中识别。
    """
    return "owc_" + secrets.token_hex(16)


def hash_api_key(plain_key: str) -> str:
    """使用 bcrypt 对 API Key 进行单向哈希。

    bcrypt 自动包含随机盐值，每次相同输入产生不同输出。
    """
    return bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """验证明文 Key 是否与存储的 bcrypt 哈希匹配。"""
    return bcrypt.checkpw(plain_key.encode(), hashed_key.encode())


def require_auth(
    x_client_id: str = Header(..., alias="X-Client-Id",
                               description="客户端唯一标识"),
    x_api_key: str = Header(..., alias="X-Api-Key",
                             description="客户端 API 密钥"),
    db_path: str = DEFAULT_DB_PATH,
):
    """FastAPI 依赖 — 验证客户端身份。

    在所有需要认证的路由上使用::

        @app.post("/api/v1/telemetry")
        async def ingest(batch: TelemetryBatch, cid=Depends(require_auth)):
            ...

    认证失败直接抛出 401，不执行后续路由逻辑。
    这是防御第一线: 未认证请求根本不会进入业务代码。

    注意: require_auth 不是 async generator, 所以不能直接用 Depends(get_db)。
    改为在函数内部独立获取连接。
    """
    import sqlite3

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        hashed = get_client_api_key_hash(conn, x_client_id)
        if not hashed or not verify_api_key(x_api_key, hashed):
            raise HTTPException(
                status_code=401,
                detail="Invalid client_id or api_key",
            )
    finally:
        conn.close()

    # 返回已验证的 client_id，确保与请求体中的 client_id 一致
    return x_client_id
