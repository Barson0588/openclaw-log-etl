"""
多客户端 Dashboard 构建器 — 复用 report_generator.py 的模板渲染模式。

与现有单机 Dashboard 的区别:
  - 数据不内嵌到 HTML 中，而是由前端 JS 通过 /api/v1/* 接口动态加载
  - 增加客户端选择器，支持多客户端对比
  - 保留相同的视觉风格 (KPI 卡片 + SVG 图表 + 暗色模式)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime

from server.db import get_all_clients

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def build_dashboard(db: sqlite3.Connection) -> str:
    """构建多客户端监控 Dashboard HTML。

    注入的数据仅限于客户端列表 (用于选择器) 和服务器时间。
    图表数据由前端 JS 通过 fetch 动态获取。
    """
    clients = get_all_clients(db)
    today = datetime.now().strftime("%Y年%m月%d日")

    # 准备注入的初始数据
    init_data = {
        "clients": clients,
        "server_time": datetime.now().isoformat(),
    }

    template_path = os.path.join(TEMPLATE_DIR, "dashboard_multi.html")

    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"模板文件不存在: {template_path}"
            " — 请确保 templates/dashboard_multi.html 存在"
        )

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    return template.format(
        today=today,
        init_data_json=json.dumps(init_data, ensure_ascii=False),
    )
