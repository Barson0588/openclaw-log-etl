"""
Pydantic 数据模型 — 定义客户端与服务端之间的 API 契约。

所有模型使用 Pydantic v2 风格 (model_validate / model_dump)，
同时兼容 v1 (parse_obj / dict) 以确保更广泛的 FastAPI 版本支持。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =====================================================================
#  请求模型 — 客户端 → 服务端
# =====================================================================

class TelemetryRecord(BaseModel):
    """单条遥测记录，对应一条 OpenClaw 轨迹的完整数据。

    字段设计直接对齐 openclaw_adapter._parse_trajectory() 的输出结构，
    确保客户端可以无转换直接上报。
    """
    task_id: str                          # session ID (完整 36-char UUID)
    timestamp: str                        # ISO 8601, e.g. "2026-07-23T14:30:00"
    duration_ms: int = Field(ge=0)        # 执行耗时 (毫秒)
    tokens_used: int = Field(ge=0)        # Token 总消耗
    tool_calls_count: int = Field(ge=0)   # 工具调用次数
    tool_name: str = ""                   # 主要工具名 (可为空)
    status: str                           # "success" | "failed"
    error_type: str = ""                  # 错误类型 (成功时为空)
    trigger: str = "unknown"              # 触发方式: "cron" | "user" | "unknown"
    raw_data_json: str = ""               # 完整交互数据 JSON (用于 Dashboard 详情展示)

    model_config = {"extra": "forbid"}


class TelemetryBatch(BaseModel):
    """批量遥测上报请求体。

    客户端收集一段时间内的新记录后批量发送，减少 HTTP 请求数。
    """
    client_id: str
    records: list[TelemetryRecord]

    model_config = {"extra": "forbid"}


# =====================================================================
#  响应模型 — 服务端 → 客户端 / Dashboard
# =====================================================================

class ClientInfo(BaseModel):
    """已注册客户端的基本信息。"""
    id: str
    name: str
    created_at: str
    record_count: int = 0

    model_config = {"extra": "forbid"}


class PerClientStats(BaseModel):
    """单客户端统计摘要 (用于多客户端对比)。"""
    client_id: str
    client_name: str
    total_tasks: int
    total_success: int
    total_failed: int
    overall_success_rate: float
    total_tokens: int
    avg_tokens_per_task: float = 0.0
    avg_duration_ms: float = 0.0
    top_error_type: str = "N/A"
    top_tool: str = "N/A"

    model_config = {"extra": "forbid"}


class StatsResponse(BaseModel):
    """聚合统计响应 — 字段结构与 analyzer.LogAnalyzer.run_all() 的 stats dict 完全对齐，
    保证 Dashboard 模板可以复用相同的变量名。

    额外增加 per_client 字段，用于多客户端对比视图。
    """
    client_id: Optional[str] = None
    total_tasks: int = 0
    total_success: int = 0
    total_failed: int = 0
    overall_success_rate: float = 0.0
    total_tokens: int = 0
    avg_tokens_per_task: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    p50_tokens: float = 0.0
    p95_tokens: float = 0.0
    p99_tokens: float = 0.0
    date_range_start: str = ""
    date_range_end: str = ""
    top_error_type: str = "N/A"
    top_tool: str = "N/A"
    per_client: list[PerClientStats] = []

    model_config = {"extra": "forbid"}


class TelemetryQueryResponse(BaseModel):
    """遥测记录查询响应 — 分页返回。"""
    records: list[dict]
    total: int = 0

    model_config = {"extra": "forbid"}


class IngestResponse(BaseModel):
    """批量写入响应。"""
    received: int
    duplicates: int

    model_config = {"extra": "forbid"}


class ClientsResponse(BaseModel):
    """客户端列表响应。"""
    clients: list[ClientInfo]

    model_config = {"extra": "forbid"}
