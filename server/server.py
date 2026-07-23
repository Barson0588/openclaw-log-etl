"""
OpenClaw Monitor Server — FastAPI 应用主入口。

提供 RESTful API 用于:
  - 接收多客户端遥测数据上报 (POST /api/v1/telemetry)
  - 查询遥测记录 (GET /api/v1/telemetry)
  - 客户端管理列表 (GET /api/v1/clients)
  - 聚合统计查询 (GET /api/v1/stats)
  - 多客户端可视化 Dashboard (GET /api/v1/dashboard)

启动方式:
    uvicorn server.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from server.auth import require_auth
from server.db import (
    DEFAULT_DB_PATH,
    get_all_clients,
    get_db,
    get_stats,
    ingest_batch,
    init_db,
    query_telemetry,
)
from server.models import (
    ClientsResponse,
    IngestResponse,
    StatsResponse,
    TelemetryBatch,
    TelemetryQueryResponse,
)

logger = logging.getLogger("server")


# =====================================================================
#  应用生命周期 — 启动时自动初始化数据库
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: 在服务启动时初始化数据库表。"""
    init_db()
    logger.info("OpenClaw Monitor Server 已启动")
    yield


app = FastAPI(
    title="OpenClaw Monitor Server",
    description="分布式 OpenClaw 智能体遥测汇总与监控服务",
    version="1.0.0",
    lifespan=lifespan,
)


# =====================================================================
#  API 路由
# =====================================================================

@app.post(
    "/api/v1/telemetry",
    status_code=201,
    response_model=IngestResponse,
    summary="上报遥测数据",
    description="客户端批量上报 OpenClaw 轨迹数据。幂等: 重复的 (client_id, task_id) 组合不会重复入库。",
)
async def api_ingest_telemetry(
    batch: TelemetryBatch,
    client_id: str = Depends(require_auth),
    db=Depends(get_db),
):
    """接收一批遥测记录，写入 SQLite。

    认证层面: require_auth 已验证 X-Client-Id + X-Api-Key 头。
    安全层面: 校验 Header 中的 client_id 与请求体中的 client_id 一致，
    防止客户端 A 的认证凭据冒用客户端 B 的身份写入数据。
    """
    if batch.client_id != client_id:
        raise HTTPException(
            status_code=403,
            detail="X-Client-Id header does not match body client_id",
        )

    records = [r.model_dump() for r in batch.records]
    received, duplicates = ingest_batch(db, client_id, records)
    return IngestResponse(received=received, duplicates=duplicates)


@app.get(
    "/api/v1/telemetry",
    response_model=TelemetryQueryResponse,
    summary="查询遥测记录",
    description="分页查询遥测数据，支持按客户端、时间范围、任务状态筛选。",
)
async def api_query_telemetry(
    client_id: Optional[str] = Query(None, description="筛选客户端 ID"),
    start: Optional[str] = Query(None, description="起始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="截止时间 (ISO 8601)"),
    status: Optional[str] = Query(None, description="任务状态: success | failed"),
    limit: int = Query(1000, le=10000, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db=Depends(get_db),
):
    """公开查询接口 — 不需要认证（Dashboard 使用）。"""
    return query_telemetry(db, client_id, start, end, status, limit, offset)


@app.get(
    "/api/v1/clients",
    response_model=ClientsResponse,
    summary="客户端列表",
    description="获取所有已注册客户端及其遥测记录数量。",
)
async def api_list_clients(db=Depends(get_db)):
    """公开接口 — Dashboard 客户端选择器使用。"""
    clients = get_all_clients(db)
    return ClientsResponse(clients=clients)


@app.get(
    "/api/v1/stats",
    response_model=StatsResponse,
    summary="聚合统计",
    description="获取聚合 KPI 指标 (成功率、分位数、Top 错误/工具等)。"
                "不指定 client_id 时返回全局统计 + 多客户端对比数据。",
)
async def api_get_stats(
    client_id: Optional[str] = Query(None, description="筛选客户端 ID"),
    start: Optional[str] = Query(None, description="起始时间"),
    end: Optional[str] = Query(None, description="截止时间"),
    db=Depends(get_db),
):
    """公开接口 — 统计查询不需要认证。"""
    return get_stats(db, client_id, start, end)


@app.get(
    "/api/v1/dashboard",
    response_class=HTMLResponse,
    summary="可视化监控仪表盘",
    description="返回多客户端监控 Dashboard (SPA 单页应用)。"
                "所有数据通过前端 fetch 调用上述 API 动态加载。",
)
async def api_serve_dashboard(db=Depends(get_db)):
    """Dashboard 页面 — 动态加载客户端数据。

    将已注册的客户端列表注入模板初始数据，避免页面加载后立即多一个请求。
    Dashboard 内的图表数据由前端 JS 通过 /api/v1/stats 和 /api/v1/telemetry 获取。
    """
    from server.dashboard_server import build_dashboard

    return build_dashboard(db)
