"""
数据库层 — SQLite 持久化与查询。

设计要点:
  - UNIQUE(client_id, task_id) 保证幂等: 同一客户端重复上报同一任务会被静默忽略
  - 所有查询使用参数化 SQL，防止注入
  - stats 聚合查询的输出结构与 analyzer.run_all() 完全对齐
  - 每个请求独立获取连接并关闭，避免长连接堆积
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "openclaw_monitor.db")


def init_db(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """初始化数据库 — 创建表与索引（幂等，可重复调用）。

    在 FastAPI 的 lifespan / startup 事件中调用一次。
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            api_key_hash  TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS telemetry_records (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id        TEXT    NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            task_id          TEXT    NOT NULL,
            timestamp        TEXT    NOT NULL,
            duration_ms      INTEGER NOT NULL CHECK(duration_ms >= 0),
            tokens_used      INTEGER NOT NULL CHECK(tokens_used >= 0),
            tool_calls_count INTEGER NOT NULL DEFAULT 0 CHECK(tool_calls_count >= 0),
            tool_name        TEXT    NOT NULL DEFAULT '',
            status           TEXT    NOT NULL CHECK(status IN ('success', 'failed')),
            error_type       TEXT    NOT NULL DEFAULT '',
            trigger          TEXT    NOT NULL DEFAULT 'unknown',
            raw_data_json    TEXT    NOT NULL DEFAULT '',
            received_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_telemetry_client_id
            ON telemetry_records(client_id);
        CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp
            ON telemetry_records(timestamp);
        CREATE INDEX IF NOT EXISTS idx_telemetry_status
            ON telemetry_records(status);

        -- 幂等性保证: 同一客户端的同一条 task 不会重复入库
        CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_dedup
            ON telemetry_records(client_id, task_id);
    """)

    conn.commit()
    logger.info("数据库初始化完成: %s", db_path)
    return conn


def get_db(db_path: str = DEFAULT_DB_PATH):
    """FastAPI 依赖注入 — 每个请求独立获取连接，请求结束后关闭。

    使用 check_same_thread=False 是必要的:
      FastAPI 的同步路由通过 run_in_threadpool 在独立线程中执行，
      但依赖 (Depends) 在主线程中创建连接对象。
      关闭线程检查后，连接可在任意线程使用 — 由于每个请求创建独立连接，
      不存在并发冲突问题。

    使用方式::

        @app.get("/api/...")
        def handler(db=Depends(get_db)):
            ...
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


# =====================================================================
#  客户端管理
# =====================================================================

def register_client(
    db: sqlite3.Connection | sqlite3.dbapi2.Connection,
    client_id: str,
    name: str,
    api_key_hash: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """注册新客户端。

    Returns:
        True 表示新注册成功，False 表示 client_id 已存在。
    """
    try:
        db.execute(
            "INSERT INTO clients (id, name, api_key_hash) VALUES (?, ?, ?)",
            (client_id, name, api_key_hash),
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        # client_id 已存在
        return False


def get_client_api_key_hash(
    db: sqlite3.Connection, client_id: str
) -> Optional[str]:
    """获取客户端的 API key 哈希值，用于认证验证。"""
    row = db.execute(
        "SELECT api_key_hash FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    return row["api_key_hash"] if row else None


def get_all_clients(db: sqlite3.Connection) -> list[dict]:
    """获取所有已注册客户端及其记录数量。"""
    rows = db.execute("""
        SELECT c.id, c.name, c.created_at,
               COUNT(t.id) AS record_count
        FROM clients c
        LEFT JOIN telemetry_records t ON c.id = t.client_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


# =====================================================================
#  遥测数据写入
# =====================================================================

def ingest_batch(
    db: sqlite3.Connection,
    client_id: str,
    records: list[dict],
) -> tuple[int, int]:
    """批量写入遥测记录（幂等: 重复的 client_id + task_id 组合会被忽略）。

    Args:
        db: 数据库连接
        client_id: 客户端 ID (同时校验 X-Client-Id 头)
        records: TelemetryRecord.dict() 列表

    Returns:
        (新写入数量, 重复数量)
    """
    duplicates = 0
    for r in records:
        try:
            db.execute(
                """
                INSERT INTO telemetry_records
                    (client_id, task_id, timestamp, duration_ms, tokens_used,
                     tool_calls_count, tool_name, status, error_type, trigger,
                     raw_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    r["task_id"],
                    r["timestamp"],
                    r["duration_ms"],
                    r["tokens_used"],
                    r["tool_calls_count"],
                    r.get("tool_name", ""),
                    r["status"],
                    r.get("error_type", ""),
                    r.get("trigger", "unknown"),
                    r.get("raw_data_json", ""),
                ),
            )
        except sqlite3.IntegrityError:
            duplicates += 1

    db.commit()
    received = len(records) - duplicates
    logger.info("写入完成: client=%s, received=%d, duplicates=%d",
                client_id, received, duplicates)
    return received, duplicates


# =====================================================================
#  遥测数据查询
# =====================================================================

def query_telemetry(
    db: sqlite3.Connection,
    client_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> dict:
    """分页查询遥测记录，支持多维筛选。

    Args:
        client_id: 客户端 ID (None 表示所有客户端)
        start: 起始时间 (ISO 8601, 闭区间)
        end: 截止时间 (ISO 8601, 闭区间)
        status: 任务状态 ("success" | "failed", None 表示全部)
        limit: 每页条数 (最大 10000)
        offset: 偏移量
    """
    limit = min(limit, 10000)

    conditions = []
    params: list = []

    if client_id:
        conditions.append("client_id = ?")
        params.append(client_id)
    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 总数
    count_row = db.execute(
        f"SELECT COUNT(*) AS cnt FROM telemetry_records {where}", params
    ).fetchone()
    total = count_row["cnt"] if count_row else 0

    # 分页查询
    rows = db.execute(
        f"SELECT * FROM telemetry_records {where} "
        "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return {"records": [dict(r) for r in rows], "total": total}


# =====================================================================
#  聚合统计 — 输出结构与 analyzer.LogAnalyzer.run_all() 完全对齐
# =====================================================================

def get_stats(
    db: sqlite3.Connection,
    client_id: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> dict:
    """计算聚合统计指标。

    输出的 stats dict 与 analyzer.run_all() 的 stats 字段完全一致，
    保证 Dashboard 模板可用相同变量名渲染。额外增加 per_client 字段。

    Args:
        client_id: 筛选单个客户端 (None = 全局)
        start: 时间范围起点
        end: 时间范围终点
    """
    conditions = []
    params: list = []

    if client_id:
        conditions.append("client_id = ?")
        params.append(client_id)
    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)

    # 使用 WHERE 1=1 作为基条件，后续统一用 AND 追加，避免空 WHERE 语法错误
    base_where = "WHERE 1=1" + ("".join(f" AND {c}" for c in conditions) if conditions else "")

    # 基础计数
    row = db.execute(
        f"""
        SELECT
            COUNT(*)                          AS total_tasks,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS total_success,
            SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) AS total_failed,
            COALESCE(SUM(tokens_used), 0)     AS total_tokens,
            COALESCE(AVG(tokens_used), 0)     AS avg_tokens_per_task,
            COALESCE(SUM(duration_ms), 0)     AS total_duration_ms,
            COALESCE(AVG(duration_ms), 0)     AS avg_duration_ms,
            MIN(timestamp)                    AS date_range_start,
            MAX(timestamp)                    AS date_range_end
        FROM telemetry_records {base_where}
        """,
        params,
    ).fetchone()

    if not row or row["total_tasks"] == 0:
        return {
            "client_id": client_id,
            "total_tasks": 0, "total_success": 0, "total_failed": 0,
            "overall_success_rate": 0.0, "total_tokens": 0,
            "avg_tokens_per_task": 0.0, "total_duration_seconds": 0.0,
            "avg_duration_ms": 0.0,
            "p50_duration_ms": 0.0, "p95_duration_ms": 0.0, "p99_duration_ms": 0.0,
            "p50_tokens": 0.0, "p95_tokens": 0.0, "p99_tokens": 0.0,
            "date_range_start": "", "date_range_end": "",
            "top_error_type": "N/A", "top_tool": "N/A",
            "per_client": [],
        }

    total = row["total_tasks"]
    success_rate = round(row["total_success"] / total * 100, 2) if total > 0 else 0.0

    # 分位数计算 (用 SQLite 的 NTILE 或子查询近似)
    # 使用 OFFSET 方式计算近似分位数
    p_bounds = _compute_percentiles(db, "duration_ms", base_where, params)
    t_bounds = _compute_percentiles(db, "tokens_used", base_where, params)

    # 最高频错误类型
    error_row = db.execute(
        f"""
        SELECT error_type, COUNT(*) AS cnt
        FROM telemetry_records {base_where} AND status = 'failed' AND error_type != ''
        GROUP BY error_type ORDER BY cnt DESC LIMIT 1
        """,
        params,
    ).fetchone()
    top_error = error_row["error_type"] if error_row else "N/A"

    # 最高频工具
    tool_row = db.execute(
        f"""
        SELECT tool_name, COUNT(*) AS cnt
        FROM telemetry_records {base_where} AND tool_name != '' AND tool_name != 'none'
        GROUP BY tool_name ORDER BY cnt DESC LIMIT 1
        """,
        params,
    ).fetchone()
    top_tool = tool_row["tool_name"] if tool_row else "N/A"

    # 多客户端对比: 如果没有指定 client_id，返回全局 + 每个客户端的统计
    per_client = []
    if not client_id:
        per_client = _get_per_client_stats(db, start, end)

    return {
        "client_id": client_id,
        "total_tasks": total,
        "total_success": int(row["total_success"]),
        "total_failed": int(row["total_failed"]),
        "overall_success_rate": success_rate,
        "total_tokens": int(row["total_tokens"]),
        "avg_tokens_per_task": round(row["avg_tokens_per_task"], 1),
        "total_duration_seconds": round(row["total_duration_ms"] / 1000, 1),
        "avg_duration_ms": round(row["avg_duration_ms"], 1),
        "p50_duration_ms": p_bounds.get(50, 0),
        "p95_duration_ms": p_bounds.get(95, 0),
        "p99_duration_ms": p_bounds.get(99, 0),
        "p50_tokens": t_bounds.get(50, 0),
        "p95_tokens": t_bounds.get(95, 0),
        "p99_tokens": t_bounds.get(99, 0),
        "date_range_start": (row["date_range_start"] or "")[:10],
        "date_range_end": (row["date_range_end"] or "")[:10],
        "top_error_type": top_error,
        "top_tool": top_tool,
        "per_client": per_client,
    }


def _compute_percentiles(
    db: sqlite3.Connection,
    column: str,
    where: str,
    params: list,
) -> dict[int, float]:
    """使用 OFFSET 近似计算指定列的 P50/P95/P99 分位数。"""
    total_row = db.execute(
        f"SELECT COUNT(*) AS cnt FROM telemetry_records {where}", params
    ).fetchone()
    n = total_row["cnt"] if total_row else 0
    if n == 0:
        return {}

    result = {}
    for pct in [50, 95, 99]:
        offset = int(n * pct / 100)
        if offset >= n:
            offset = n - 1
        row = db.execute(
            f"SELECT {column} FROM telemetry_records {where} "
            f"ORDER BY {column} ASC LIMIT 1 OFFSET ?",
            params + [offset],
        ).fetchone()
        if row:
            result[pct] = round(float(row[column]), 1)
    return result


def _get_per_client_stats(
    db: sqlite3.Connection,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[dict]:
    """获取所有客户端的各自统计，用于多客户端对比视图。

    每个客户端的统计粒度与全局 stats 一致，但精简为 Dashboard 对比表所需字段。
    """
    conditions = []
    params: list = []
    if start:
        conditions.append("t.timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("t.timestamp <= ?")
        params.append(end)
    base_where = "WHERE 1=1" + ("".join(f" AND {c}" for c in conditions) if conditions else "")

    rows = db.execute(
        f"""
        SELECT
            c.id       AS client_id,
            c.name     AS client_name,
            COUNT(*)   AS total,
            SUM(CASE WHEN t.status='success' THEN 1 ELSE 0 END) AS success,
            SUM(CASE WHEN t.status='failed'  THEN 1 ELSE 0 END) AS failed,
            COALESCE(SUM(t.tokens_used), 0) AS total_tokens,
            COALESCE(AVG(t.tokens_used), 0) AS avg_tokens,
            COALESCE(AVG(t.duration_ms), 0) AS avg_duration
        FROM telemetry_records t
        JOIN clients c ON t.client_id = c.id
        {base_where}
        GROUP BY t.client_id
        ORDER BY total DESC
        """,
        params,
    ).fetchall()

    result = []
    for r in rows:
        total = r["total"]
        # 每个客户端的 top error
        err_row = db.execute(
            """
            SELECT error_type, COUNT(*) AS cnt
            FROM telemetry_records
            WHERE client_id = ? AND status = 'failed' AND error_type != ''
            GROUP BY error_type ORDER BY cnt DESC LIMIT 1
            """,
            (r["client_id"],),
        ).fetchone()
        # 每个客户端的 top tool
        tool_row = db.execute(
            """
            SELECT tool_name, COUNT(*) AS cnt
            FROM telemetry_records
            WHERE client_id = ? AND tool_name != '' AND tool_name != 'none'
            GROUP BY tool_name ORDER BY cnt DESC LIMIT 1
            """,
            (r["client_id"],),
        ).fetchone()

        result.append({
            "client_id": r["client_id"],
            "client_name": r["client_name"],
            "total_tasks": total,
            "total_success": r["success"],
            "total_failed": r["failed"],
            "overall_success_rate": round(r["success"] / total * 100, 1) if total else 0,
            "total_tokens": int(r["total_tokens"]),
            "avg_tokens_per_task": round(r["avg_tokens"], 1),
            "avg_duration_ms": round(r["avg_duration"], 1),
            "top_error_type": err_row["error_type"] if err_row else "N/A",
            "top_tool": tool_row["tool_name"] if tool_row else "N/A",
        })

    return result
