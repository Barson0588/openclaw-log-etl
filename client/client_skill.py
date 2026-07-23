#!/usr/bin/env python3
"""
OpenClaw Telemetry Client Skill — 后台上报模块。

以 OpenClaw 技能/插件形式运行，易于集成到任何 OpenClaw 实例中。

核心设计:
  - 后台守护线程，定时 (默认 60s) 采集本地轨迹数据并 POST 到监控服务端
  - 复用 openclaw_adapter.OpenClawAdapter，不做重复解析
  - 异常隔离: 上报失败不抛出异常，不影响 OpenClaw 主进程
  - 3 次指数退避重试 (2^0, 2^1, 2^2 秒)
  - 内存记录已上报 task_id，避免重复发送

使用方式:
    from client.client_skill import OpenClawReporter
    reporter = OpenClawReporter()
    reporter.start()   # 启动后台上报

环境变量:
    OPENCLAW_SERVER_URL     服务端地址 (默认 http://localhost:8000)
    OPENCLAW_CLIENT_ID      本机唯一标识
    OPENCLAW_API_KEY        客户端 API 密钥
    OPENCLAW_SESSIONS_DIR   轨迹文件目录 (默认 ~/.openclaw/agents/main/sessions)
    OPENCLAW_REPORT_INTERVAL  上报间隔秒数 (默认 60)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime

import httpx

# 将项目根目录加入 sys.path，确保可以 import openclaw_adapter
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from openclaw_adapter import OpenClawAdapter

logger = logging.getLogger("openclaw.reporter")

# =====================================================================
#  环境变量配置
# =====================================================================

SERVER_URL = os.getenv("OPENCLAW_SERVER_URL", "http://localhost:8000").rstrip("/")
CLIENT_ID = os.getenv("OPENCLAW_CLIENT_ID", "")
API_KEY = os.getenv("OPENCLAW_API_KEY", "")
SESSIONS_DIR = os.path.expanduser(
    os.getenv("OPENCLAW_SESSIONS_DIR", "~/.openclaw/agents/main/sessions")
)
REPORT_INTERVAL = int(os.getenv("OPENCLAW_REPORT_INTERVAL", "60"))


# =====================================================================
#  后台上报器
# =====================================================================

class OpenClawReporter:
    """后台上报器 — 定时采集轨迹数据并发送到监控服务端。

    线程安全设计:
      - _seen_task_ids 只在 _report_once 中写入，由 _run_loop 串行调用
      - _stop_event 是标准的 threading.Event，线程安全

    使用示例::

        reporter = OpenClawReporter(
            server_url="http://monitor.example.com:8000",
            client_id="mac-001",
            api_key="owc_...",
        )
        reporter.start()
        # ... OpenClaw 正常运行 ...
        reporter.stop()
    """

    def __init__(
        self,
        server_url: str | None = None,
        client_id: str | None = None,
        api_key: str | None = None,
        sessions_dir: str | None = None,
        report_interval: int | None = None,
    ):
        """初始化上报器。

        Args:
            server_url: 监控服务端 URL
            client_id: 本机客户端 ID
            api_key: API 密钥
            sessions_dir: OpenClaw 轨迹文件目录
            report_interval: 上报间隔 (秒)
        """
        self.server_url = (server_url or SERVER_URL).rstrip("/")
        self.client_id = client_id or CLIENT_ID
        self.api_key = api_key or API_KEY
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.report_interval = report_interval or REPORT_INTERVAL

        self.adapter = OpenClawAdapter(sessions_dir=self.sessions_dir)
        self._seen_task_ids: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        if not self.client_id or not self.api_key:
            logger.warning(
                "OPENCLAW_CLIENT_ID 或 OPENCLAW_API_KEY 未设置 — 上报器将静默跳过 "
                "(设置环境变量后重试)"
            )

    def start(self) -> None:
        """启动后台上报线程 (daemon)。

        daemon=True 确保 OpenClaw 主进程退出时该线程自动终止，
        不会阻止进程正常退出。
        """
        if self._thread is not None and self._thread.is_alive():
            logger.warning("上报线程已在运行")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(
            "OpenClaw 遥测上报已启动 — server=%s, client=%s, interval=%ds",
            self.server_url, self.client_id, self.report_interval,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """停止后台上报线程。

        Args:
            timeout: 等待线程退出的最大秒数
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            logger.info("OpenClaw 遥测上报已停止")

    # =================================================================
    #  内部实现
    # =================================================================

    def _run_loop(self) -> None:
        """后台主循环 — 定期采集并上报。

        所有异常都在内部捕获，确保线程不意外退出。
        _stop_event.wait() 替代 time.sleep()，可立即响应 stop() 调用。
        """
        # 首次延迟 10 秒再上报，避免挤在服务启动时
        self._stop_event.wait(10)

        while not self._stop_event.is_set():
            try:
                if self.client_id and self.api_key:
                    self._report_once()
                else:
                    logger.debug("跳过上报: 缺少认证配置")
            except Exception:
                # 关键设计: 上报异常绝不向上传播，不影响 OpenClaw 核心业务
                logger.exception("上报周期异常 — 将在下一周期重试")

            # 使用 wait 替代 sleep，可被 stop() 立即中断
            self._stop_event.wait(self.report_interval)

    def _report_once(self) -> None:
        """单次采集 + 上报流程。

        1. 调用 OpenClawAdapter.load_all() 获取全量数据
        2. 过滤出尚未上报的新记录
        3. 转换为 TelemetryRecord 格式
        4. POST 到服务端 (含重试)
        """
        try:
            df, interactions = self.adapter.load_all()
        except Exception:
            logger.exception("轨迹数据读取失败")
            return

        if df.empty:
            logger.debug("无新轨迹数据")
            return

        # 找出新记录 (未在 _seen_task_ids 中)
        new_records = []
        for _, row in df.iterrows():
            task_id = str(row["task_id"])
            if task_id not in self._seen_task_ids:
                self._seen_task_ids.add(task_id)
                new_records.append(self._row_to_payload(row))

        if not new_records:
            logger.debug("无新记录需上报 (total_seen=%d)", len(self._seen_task_ids))
            return

        logger.info("准备上报 %d 条新记录", len(new_records))

        # 分批发送: 每次最多 100 条
        batch_size = 100
        for i in range(0, len(new_records), batch_size):
            batch = new_records[i:i + batch_size]
            self._send_with_retry(batch)

    def _send_with_retry(self, records: list[dict]) -> None:
        """发送一批记录到服务端，失败时指数退避重试。

        只重试网络/服务端错误 (HTTPError)，不重试客户端错误 (4xx)。
        服务端 401/403 说明认证配置有误，重试无意义。
        """
        url = f"{self.server_url}/api/v1/telemetry"
        headers = {
            "X-Client-Id": self.client_id,
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "client_id": self.client_id,
            "records": records,
        }

        for attempt in range(3):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, json=body, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    logger.info(
                        "上报成功: received=%d, duplicates=%d (attempt=%d)",
                        data.get("received", 0), data.get("duplicates", 0), attempt + 1,
                    )
                    return
            except httpx.HTTPStatusError as e:
                # 401/403 不重试 — 认证配置错误
                if e.response.status_code in (401, 403):
                    logger.error("认证失败 (HTTP %d): 请检查 CLIENT_ID 和 API_KEY", e.response.status_code)
                    return
                logger.warning("上报失败 (attempt %d): HTTP %d — %s",
                               attempt + 1, e.response.status_code, e)
            except httpx.RequestError as e:
                logger.warning("上报失败 (attempt %d): 网络错误 — %s", attempt + 1, e)

            # 指数退避
            if attempt < 2:
                wait = 2 ** attempt
                logger.debug("等待 %ds 后重试...", wait)
                time.sleep(wait)

        logger.error("上报最终失败: %d 条记录在 3 次重试后仍未成功", len(records))

    @staticmethod
    def _row_to_payload(row) -> dict:
        """将 DataFrame 的一行转换为符合 API Schema 的 dict。

        字段映射:
          DataFrame column  →  TelemetryRecord field
          task_id           →  task_id
          timestamp         →  timestamp (ISO 8601)
          duration_ms       →  duration_ms
          tokens_used       →  tokens_used
          tool_calls_count  →  tool_calls_count
          tool_name         →  tool_name
          status            →  status
          error_type        →  error_type
          trigger           →  trigger
        """
        ts = row["timestamp"]
        if hasattr(ts, "isoformat"):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)

        return {
            "task_id": str(row["task_id"]),
            "timestamp": ts_str,
            "duration_ms": int(row["duration_ms"]),
            "tokens_used": int(row["tokens_used"]),
            "tool_calls_count": int(row.get("tool_calls_count", 0)),
            "tool_name": str(row.get("tool_name", "")),
            "status": str(row["status"]),
            "error_type": str(row.get("error_type", "")),
            "trigger": str(row.get("trigger", "unknown")),
            "raw_data_json": "",
        }


# =====================================================================
#  便捷函数 — 一行启动上报
# =====================================================================

_reporter: OpenClawReporter | None = None


def start_reporting(
    server_url: str | None = None,
    client_id: str | None = None,
    api_key: str | None = None,
) -> OpenClawReporter:
    """一行启动后台上报 (全局单例)。

    可以在 OpenClaw 启动脚本中调用::

        import client.client_skill as skill
        skill.start_reporting()

    Returns:
        OpenClawReporter 实例
    """
    global _reporter
    if _reporter is not None:
        logger.warning("上报器已运行，跳过重复启动")
        return _reporter

    _reporter = OpenClawReporter(
        server_url=server_url,
        client_id=client_id,
        api_key=api_key,
    )
    _reporter.start()
    return _reporter


def stop_reporting() -> None:
    """停止后台上报。"""
    global _reporter
    if _reporter is not None:
        _reporter.stop()
        _reporter = None


# =====================================================================
#  直接运行 — 用于测试
# =====================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"OpenClaw Telemetry Reporter")
    print(f"  Server:   {SERVER_URL}")
    print(f"  Client:   {CLIENT_ID or '(未设置)'}")
    print(f"  Sessions: {SESSIONS_DIR}")
    print(f"  Interval: {REPORT_INTERVAL}s")
    print()

    if not CLIENT_ID or not API_KEY:
        print("错误: 请设置 OPENCLAW_CLIENT_ID 和 OPENCLAW_API_KEY 环境变量")
        print("使用 server/manage.py register-client 注册客户端获取凭据")
        sys.exit(1)

    reporter = OpenClawReporter()
    reporter.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        reporter.stop()
        print("已退出")
