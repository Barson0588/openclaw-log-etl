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
    #  公开方法: 加载全部 trajectory → DataFrame
    # -----------------------------------------------------------------

    def load_trajectories(self, limit=None):
        """扫描全部 trajectory JSONL 文件，提取任务级指标。

        Args:
            limit: 最多处理的文件数，None 表示全部

        Returns:
            pd.DataFrame，包含 ETL 标准字段:
              task_id, timestamp, duration_ms, tool_calls_count,
              tokens_used, status, error_type, tool_name, trigger
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
        skipped = 0
        for fpath in files:
            try:
                record = self._parse_one(fpath)
                if record:
                    records.append(record)
            except Exception:
                skipped += 1
                logger.debug("跳过异常文件: %s", os.path.basename(fpath))

        if skipped:
            logger.warning("跳过 %d 个异常文件", skipped)

        df = pd.DataFrame(records)

        # 如果没有记录，返回空 DataFrame 但保留 schema
        if df.empty:
            logger.warning("未能从任何 trajectory 文件中提取有效记录")
            return df

        # 按 timestamp 排序
        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(
            "加载完成: %d 条任务记录 (成功: %d, 失败: %d)",
            len(df),
            (df["status"] == "success").sum(),
            (df["status"] == "failed").sum(),
        )
        return df

    # -----------------------------------------------------------------
    #  交互记录提取（含用户提问内容）
    # -----------------------------------------------------------------

    def extract_interactions(self, limit=None):
        """提取完整交互记录，包含用户提问内容。

        相比 load_trajectories()，此方法额外提取:
          - user_prompt: 用户通过 OpenClaw 发送的提问内容
          - model_id / provider: 使用的模型信息
          - tool_names: 调用的完整工具名列表

        Args:
            limit: 最多处理的文件数

        Returns:
            list[dict]: 交互记录列表
        """
        pattern = os.path.join(self.sessions_dir, "*.trajectory.jsonl")
        files = sorted(glob.glob(pattern))

        if not files:
            raise FileNotFoundError(
                f"未找到 trajectory 文件: {self.sessions_dir}/*.trajectory.jsonl"
            )

        if limit:
            files = files[:limit]

        logger.info("提取交互记录: 扫描 %d 个 trajectory 文件...", len(files))

        interactions = []
        skipped = 0
        for fpath in files:
            try:
                record = self._parse_interaction(fpath)
                if record:
                    interactions.append(record)
            except Exception:
                skipped += 1

        if skipped:
            logger.warning("跳过 %d 个异常文件", skipped)

        # 按时间倒序排列
        interactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        logger.info(
            "交互记录提取完成: %d 条 (成功: %d, 失败: %d)",
            len(interactions),
            sum(1 for r in interactions if r["status"] == "success"),
            sum(1 for r in interactions if r["status"] == "failed"),
        )
        return interactions

    def _parse_interaction(self, fpath):
        """解析单个 trajectory 文件为交互记录。

        提取用户 prompt、模型信息、完整工具列表等详细字段。
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

        if start_ts is None:
            return None

        if end_ts:
            duration_ms = (end_ts - start_ts).total_seconds() * 1000
        else:
            duration_ms = 0

        if status == "error":
            status = "failed"
        elif status not in ("success", "failed"):
            status = "failed" if error_type else "success"

        if status == "failed" and not error_type:
            error_type = "unknown"

        from collections import Counter
        tool_counter = Counter(tool_names)
        primary_tool = tool_counter.most_common(1)[0][0] if tool_counter else "none"

        # 截取用户 prompt 摘要（前 80 字符）
        prompt_preview = user_prompt[:80].replace("\n", " ").strip() if user_prompt else ""

        return {
            "task_id": session_id,
            "task_id_short": session_id[:8] + "...",
            "timestamp": start_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "date": start_ts.strftime("%Y-%m-%d"),
            "hour": start_ts.hour,
            "trigger": trigger,
            "user_prompt": user_prompt,
            "prompt_preview": prompt_preview,
            "model_id": model_id,
            "provider": provider,
            "status": status,
            "error_type": error_type,
            "duration_ms": round(duration_ms),
            "tokens_used": total_tokens,
            "tool_calls_count": len(tool_names),
            "tool_name": primary_tool,
            "tool_names": list(set(tool_names)),
        }

    # -----------------------------------------------------------------
    #  单文件解析
    # -----------------------------------------------------------------

    def _parse_one(self, fpath):
        """解析单个 trajectory JSONL 文件，提取一条任务记录。

        trajectory 文件可能包含多轮对话（多个 model 调用），
        此方法会聚合同一 session 内的所有轮次数据。

        Args:
            fpath: trajectory JSONL 文件路径

        Returns:
            dict or None: 标准化的任务记录
        """
        session_id = os.path.basename(fpath).replace(".trajectory.jsonl", "")

        # 累积变量
        start_ts = None
        end_ts = None
        total_tokens = 0
        tool_names = []
        status = "unknown"
        error_type = ""
        trigger = "unknown"

        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ev_type = obj.get("type", "")
                data = obj.get("data", {})

                if ev_type == "session.started":
                    # 取最早的开始时间
                    ts = self._parse_ts(obj.get("ts"))
                    if ts and (start_ts is None or ts < start_ts):
                        start_ts = ts
                    if data.get("trigger"):
                        trigger = data["trigger"]

                elif ev_type == "session.ended":
                    # 取最晚的结束时间
                    ts = self._parse_ts(obj.get("ts"))
                    if ts and (end_ts is None or ts > end_ts):
                        end_ts = ts
                    if data.get("status"):
                        status = data["status"]
                    if data.get("terminalError"):
                        error_type = data["terminalError"]

                elif ev_type == "model.completed":
                    # 累加各轮次的 token
                    usage = data.get("usage", {})
                    total_tokens += usage.get("total", 0)

                elif ev_type == "trace.artifacts":
                    # 提取 tool 使用信息
                    tool_metas = data.get("toolMetas") or []
                    for tm in tool_metas:
                        name = tm.get("name", "")
                        if name:
                            tool_names.append(name)
                    # lastToolError 作为补充错误信息
                    if data.get("lastToolError") and not error_type:
                        error_type = str(data["lastToolError"])
                    if data.get("finalStatus"):
                        status = data["finalStatus"]

        # 如果没有时间戳，跳过
        if start_ts is None:
            return None

        # 计算 duration_ms
        if end_ts:
            duration_ms = (end_ts - start_ts).total_seconds() * 1000
        else:
            duration_ms = 0

        # status 标准化为 success / failed
        if status == "error":
            status = "failed"
        elif status not in ("success", "failed"):
            status = "failed" if error_type else "success"

        # error_type 为空且 status=failed 时补充
        if status == "failed" and not error_type:
            error_type = "unknown"

        # tool_name: 取最常用的工具名，无工具时用 "none" 避免 CSV 空值问题
        from collections import Counter
        tool_counter = Counter(tool_names)
        primary_tool = tool_counter.most_common(1)[0][0] if tool_counter else "none"

        return {
            "task_id": session_id,
            "timestamp": start_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": round(duration_ms),
            "tool_calls_count": len(tool_names),
            "tokens_used": total_tokens,
            "status": status,
            "error_type": error_type,
            "tool_name": primary_tool,
            "trigger": trigger,
        }

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
