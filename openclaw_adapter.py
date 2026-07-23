"""
OpenClaw 数据适配器 (openclaw_adapter.py)
==========================================
从本地 OpenClaw 环境的 trajectory JSONL 文件中提取任务日志，
并转换为 data_pipeline 所需的统一 DataFrame 格式。

数据映射关系:
  真实字段 (trajectory JSONL)           → ETL 标准字段
  ─────────────────────────────────────────────────────
  session_id (文件名)                   → task_id
  session.started.ts                    → timestamp
  session.ended.ts - session.started.ts → duration_ms
  trace.artifacts.data.toolMetas        → tool_calls_count, tool_name
  model.completed.data.usage.total      → tokens_used
  session.ended.data.status             → status (success/error)
  trace.artifacts.data.lastToolError    → error_type

设计思路:
  - 一次扫描全部 trajectory 文件，构建统一 DataFrame
  - 多轮对话 session 自动聚合各轮次的 token 和 tool 调用
  - 异常文件跳过并记录 warning，不影响整体流程
"""

import json
import logging
import os
import glob
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# 默认 OpenClaw sessions 目录
DEFAULT_SESSIONS_DIR = os.path.expanduser(
    "~/.openclaw/agents/main/sessions"
)


class OpenClawAdapter:
    """OpenClaw 本地 trajectory 数据读取器。

    使用方式::

        adapter = OpenClawAdapter()
        df = adapter.load_trajectories()   # → DataFrame with ETL schema
    """

    def __init__(self, sessions_dir=None):
        """
        Args:
            sessions_dir: trajectory JSONL 所在目录，默认 ~/.openclaw/agents/main/sessions
        """
        self.sessions_dir = sessions_dir or DEFAULT_SESSIONS_DIR

    # -----------------------------------------------------------------
    #  公开方法
    # -----------------------------------------------------------------

    def load_all(self, limit=None):
        """单次扫描全部 trajectory 文件，同时产出 DataFrame 和交互记录。

        这是推荐的主入口 — 一次文件扫描即可获得两种视图，
        避免 load_trajectories() + extract_interactions() 重复读文件。

        Args:
            limit: 最多处理的文件数，None 表示全部

        Returns:
            tuple: (pd.DataFrame, list[dict])
        """
        pattern = os.path.join(self.sessions_dir, "*.trajectory.jsonl")
        files = sorted(glob.glob(pattern))

        if not files:
            raise FileNotFoundError(
                f"未找到 trajectory 文件: {self.sessions_dir}/*.trajectory.jsonl"
            )

        if limit:
            files = files[:limit]

        logger.info("扫描 %d 个 trajectory 文件...", len(files))

        records = []
        interactions = []
        skipped = 0
        for fpath in files:
            try:
                basic, interaction = self._parse_trajectory(fpath)
                if basic:
                    records.append(basic)
                    interactions.append(interaction)
            except Exception:
                skipped += 1
                logger.debug("跳过异常文件: %s", os.path.basename(fpath))

        if skipped:
            logger.warning("跳过 %d 个异常文件", skipped)

        df = pd.DataFrame(records)

        if not df.empty:
            df = df.sort_values("timestamp").reset_index(drop=True)

        interactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        logger.info(
            "加载完成: %d 条任务记录 (成功: %d, 失败: %d), %d 条交互",
            len(df),
            (df["status"] == "success").sum() if not df.empty else 0,
            (df["status"] == "failed").sum() if not df.empty else 0,
            len(interactions),
        )
        return df, interactions

    def load_trajectories(self, limit=None):
        """扫描 trajectory 文件，返回 DataFrame（兼容旧接口）。

        如需同时获取交互记录，请使用 load_all() 避免重复扫描。
        """
        df, _ = self.load_all(limit=limit)
        return df

    def extract_interactions(self, limit=None):
        """提取交互记录列表（兼容旧接口）。

        如需同时获取 DataFrame，请使用 load_all() 避免重复扫描。
        """
        _, interactions = self.load_all(limit=limit)
        return interactions

    # -----------------------------------------------------------------
    #  单文件解析（统一实现）
    # -----------------------------------------------------------------

    def _parse_trajectory(self, fpath):
        """解析单个 trajectory JSONL 文件，一趟扫描提取全部字段。

        同时产出 basic record（DataFrame 用）和 interaction record（报表用），
        避免对同一文件两次 open + 逐行解析。

        Returns:
            tuple: (basic_record, interaction_record) 或 (None, None)
        """
        session_id = os.path.basename(fpath).replace(".trajectory.jsonl", "")

        start_ts = None
        end_ts = None
        total_tokens = 0
        tool_names = []
        status = "unknown"
        error_type = ""
        trigger = "unknown"
        user_prompt = ""
        model_id = ""
        provider = ""

        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ev_type = obj.get("type", "")
                data = obj.get("data", {})

                if ev_type == "session.started":
                    ts = self._parse_ts(obj.get("ts"))
                    if ts and (start_ts is None or ts < start_ts):
                        start_ts = ts
                    if data.get("trigger"):
                        trigger = data["trigger"]
                    provider = obj.get("provider", "")
                    model_id = obj.get("modelId", "")

                elif ev_type == "session.ended":
                    ts = self._parse_ts(obj.get("ts"))
                    if ts and (end_ts is None or ts > end_ts):
                        end_ts = ts
                    if data.get("status"):
                        status = data["status"]
                    if data.get("terminalError"):
                        error_type = data["terminalError"]

                elif ev_type == "context.compiled":
                    prompt = data.get("prompt", "")
                    if prompt and not user_prompt:
                        user_prompt = prompt

                elif ev_type == "model.completed":
                    usage = data.get("usage", {})
                    total_tokens += usage.get("total", 0)

                elif ev_type == "trace.artifacts":
                    tool_metas = data.get("toolMetas") or []
                    for tm in tool_metas:
                        name = tm.get("name", "")
                        if name:
                            tool_names.append(name)
                    if data.get("lastToolError") and not error_type:
                        error_type = str(data["lastToolError"])
                    if data.get("finalStatus"):
                        status = data["finalStatus"]

        if start_ts is None:
            return None, None

        duration_ms = round((end_ts - start_ts).total_seconds() * 1000) if end_ts else 0

        # 状态标准化
        if status == "error":
            status = "failed"
        elif status not in ("success", "failed"):
            status = "failed" if error_type else "success"
        if status == "failed" and not error_type:
            error_type = "unknown"

        # 最常用工具
        tool_counter = Counter(tool_names)
        primary_tool = tool_counter.most_common(1)[0][0] if tool_counter else "none"

        ts_str = start_ts.strftime("%Y-%m-%d %H:%M:%S")

        basic = {
            "task_id": session_id,
            "timestamp": ts_str,
            "duration_ms": duration_ms,
            "tool_calls_count": len(tool_names),
            "tokens_used": total_tokens,
            "status": status,
            "error_type": error_type,
            "tool_name": primary_tool,
            "trigger": trigger,
        }

        prompt_preview = user_prompt[:80].replace("\n", " ").strip() if user_prompt else ""

        interaction = {
            "task_id": session_id,
            "task_id_short": session_id[:8] + "...",
            "timestamp": ts_str,
            "date": start_ts.strftime("%Y-%m-%d"),
            "hour": start_ts.hour,
            "trigger": trigger,
            "user_prompt": user_prompt,
            "prompt_preview": prompt_preview,
            "model_id": model_id,
            "provider": provider,
            "status": status,
            "error_type": error_type,
            "duration_ms": duration_ms,
            "tokens_used": total_tokens,
            "tool_calls_count": len(tool_names),
            "tool_name": primary_tool,
            "tool_names": list(set(tool_names)),
        }

        return basic, interaction

    @staticmethod
    def _parse_ts(ts_str):
        """将 ISO 时间字符串转为 UTC datetime。"""
        if not ts_str:
            return None
        try:
            # 处理 Z 后缀和 +00:00 格式
            ts_str = ts_str.replace("Z", "+00:00")
            return datetime.fromisoformat(ts_str).astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None
