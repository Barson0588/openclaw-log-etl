#!/usr/bin/env python3
"""
OpenClaw Monitor Reporter — cron 触发的数据上报脚本。

工作流程:
  1. 读取 ~/.openclaw-monitor/config.sh 获取服务器地址和认证凭据
  2. 扫描本机 OpenClaw trajectory 文件
  3. 过滤已上报的 task_id（记录在 ~/.openclaw-monitor/seen.txt）
  4. POST 新记录到监控服务端
  5. 更新 seen.txt

设计要点:
  - 无外部依赖（仅用标准库），确保 cron 环境下可运行
  - 上报失败不退出，下次 cron 触发时自动重试
  - 幂等上报：服务端 UNIQUE(client_id, task_id) 兜底
  - trajectory JSONL 解析逻辑与 openclaw_adapter._parse_trajectory 对齐
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("openclaw.reporter")
CONFIG_DIR = os.path.expanduser("~/.openclaw-monitor")
SEEN_FILE = os.path.join(CONFIG_DIR, "seen.txt")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")


def load_config():
    """从 shell 格式的配置文件读取设置。"""
    config = {}
    config_path = os.path.join(CONFIG_DIR, "config.sh")
    if not os.path.exists(config_path):
        logger.error("配置文件不存在: %s，请先运行 setup.sh", config_path)
        return None
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            # 解析 export KEY="VALUE" 或 KEY="VALUE"
            line = line.replace("export ", "", 1)
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            config[key] = val
    return config


def load_seen():
    """读取已上报的 task_id 集合。"""
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE) as f:
        return set(line.strip() for line in f if line.strip())


def save_seen(seen: set):
    """写入已上报的 task_id 集合。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        for tid in sorted(seen):
            f.write(tid + "\n")


def save_state(stats: dict):
    """保存上报状态。"""
    with open(STATE_FILE, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Trajectory 解析（对齐 openclaw_adapter._parse_trajectory）
# ---------------------------------------------------------------------------

def find_sessions(sessions_dir: str):
    """扫描 trajectory 文件列表（按文件名排序）。"""
    path = Path(sessions_dir)
    if not path.exists():
        return []
    return sorted(path.glob("*.trajectory.jsonl"))


def parse_trajectory(fpath: Path):
    """解析单个 trajectory JSONL 文件。

    Returns:
        (basic_record, interaction_record) 或 (None, None)
    """
    session_id = fpath.name.replace(".trajectory.jsonl", "")
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
    conversation = []
    _seen_texts = set()

    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_type = obj.get("type", "")
            data = obj.get("data", {})

            if ev_type == "session.started":
                ts = _parse_ts(obj.get("ts"))
                if ts and (start_ts is None or ts < start_ts):
                    start_ts = ts
                if data.get("trigger"):
                    trigger = data["trigger"]
                provider = obj.get("provider", "")
                model_id = obj.get("modelId", "")

            elif ev_type == "session.ended":
                ts = _parse_ts(obj.get("ts"))
                if ts and (end_ts is None or ts > end_ts):
                    end_ts = ts
                if data.get("status"):
                    status = data["status"]
                if data.get("terminalError"):
                    error_type = data["terminalError"]

            elif ev_type == "context.compiled":
                prompt = data.get("prompt", "")
                if prompt and not user_prompt:
                    parts = prompt.split("\n```\n")
                    user_prompt = parts[-1].strip() if len(parts) >= 3 else prompt

            elif ev_type == "model.completed":
                messages = data.get("messagesSnapshot") or []
                for msg in messages:
                    usage = msg.get("usage", {})
                    total_tokens += usage.get("totalTokens", 0)
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text = " ".join(
                            c.get("text", "")
                            for c in content
                            if c.get("type") == "text"
                        )
                    else:
                        text = str(content) if content else ""
                    if text and text not in _seen_texts:
                        _seen_texts.add(text)
                        if role == "user":
                            parts = text.split("\n```\n")
                            text = parts[-1].strip() if len(parts) >= 3 else text
                        conversation.append({"role": role, "text": text})

            elif ev_type == "trace.artifacts":
                tool_metas = data.get("toolMetas") or []
                for tm in tool_metas:
                    name = tm.get("toolName", "")
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

    tool_counter = Counter(tool_names)
    primary_tool = tool_counter.most_common(1)[0][0] if tool_counter else "none"

    ts_str = start_ts.strftime("%Y-%m-%dT%H:%M:%S")

    basic = {
        "task_id": session_id,
        "timestamp": ts_str,
        "duration_ms": duration_ms,
        "tokens_used": total_tokens,
        "tool_calls_count": len(tool_names),
        "tool_name": primary_tool,
        "status": status,
        "error_type": error_type,
        "trigger": trigger,
    }

    raw_json = json.dumps({
        "user_prompt": user_prompt,
        "model_id": model_id,
        "provider": provider,
        "tool_names": list(set(tool_names)),
        "conversation": conversation,
    }, ensure_ascii=False)

    basic["raw_data_json"] = raw_json

    return basic, None


def _parse_ts(ts_str):
    """解析 ISO 时间字符串为 UTC datetime。"""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 上报逻辑
# ---------------------------------------------------------------------------

def validate_config(config: dict) -> dict:
    """只读诊断：检查 sessions 目录和文件健康状况，不上报数据。"""
    sessions_dir = os.path.expanduser(
        config.get("SESSIONS_DIR", "~/.openclaw/agents/main/sessions")
    )
    report = {
        "sessions_dir": sessions_dir,
        "dir_exists": False,
        "dir_readable": False,
        "file_count": 0,
        "sample_parse_ok": False,
        "errors": [],
    }

    path = Path(sessions_dir)
    if not path.exists():
        report["errors"].append(f"目录不存在: {sessions_dir}")
        return report
    report["dir_exists"] = True

    if not os.access(sessions_dir, os.R_OK):
        report["errors"].append(f"目录不可读: {sessions_dir}")
        return report
    report["dir_readable"] = True

    jsonl_files = sorted(path.glob("*.trajectory.jsonl"))
    report["file_count"] = len(jsonl_files)

    if jsonl_files:
        try:
            basic, _ = parse_trajectory(jsonl_files[0])
            if basic:
                report["sample_parse_ok"] = True
        except Exception as e:
            report["errors"].append(f"解析首条记录失败: {e}")
    else:
        report["errors"].append(f"目录中没有 .trajectory.jsonl 文件")

    return report


def print_validate_report(report: dict) -> None:
    """友好地打印 validate 报告。"""
    print(f"\n  Sessions 目录: {report['sessions_dir']}")
    print(f"  目录存在:   {'OK' if report['dir_exists'] else 'FAIL'}")
    print(f"  目录可读:   {'OK' if report['dir_readable'] else 'FAIL'}")
    print(f"  轨迹文件数: {report['file_count']}")
    if report.get("sample_parse_ok"):
        print(f"  解析测试:   OK (首条记录可正常解析)")
    if report["errors"]:
        print(f"\n  问题:")
        for e in report["errors"]:
            print(f"    - {e}")
    else:
        print(f"\n  状态: 一切正常，可以开始上报。")
    print()


def run_once(config: dict) -> dict:
    """单次扫描 + 上报，返回统计信息。"""
    server_url = config.get("SERVER_URL", "").rstrip("/")
    client_id = config.get("CLIENT_ID", "")
    api_key = config.get("API_KEY", "")
    sessions_dir = os.path.expanduser(
        config.get("SESSIONS_DIR", "~/.openclaw/agents/main/sessions")
    )

    if not server_url or not client_id or not api_key:
        return {"error": "配置不完整", "sent": 0, "total_scanned": 0}

    # 检查 sessions 目录
    path = Path(sessions_dir)
    if not path.exists():
        logger.error("Sessions 目录不存在: %s", sessions_dir)
        return {"error": f"目录不存在: {sessions_dir}", "sent": 0, "total_scanned": 0}
    if not os.access(sessions_dir, os.R_OK):
        logger.error("Sessions 目录不可读: %s", sessions_dir)
        return {"error": f"目录不可读: {sessions_dir}", "sent": 0, "total_scanned": 0}

    # 加载已上报集合
    seen = load_seen()

    # 扫描 trajectory 文件
    files = find_sessions(sessions_dir)
    new_records = []

    for fpath in files:
        task_id = fpath.name.replace(".trajectory.jsonl", "")
        if task_id in seen:
            continue
        try:
            basic, _ = parse_trajectory(fpath)
            if basic:
                new_records.append(basic)
                seen.add(task_id)
        except Exception:
            logger.warning("解析失败: %s", fpath.name, exc_info=True)

    if not files:
        logger.warning("目录中没有 trajectory 文件: %s", sessions_dir)
        return {"sent": 0, "total_scanned": 0, "seen_count": len(seen)}

    if not new_records:
        return {"sent": 0, "total_scanned": len(files), "seen_count": len(seen)}

    # 分批发送（每批 100 条）
    url = f"{server_url}/api/v1/telemetry"
    batch_size = 100
    total_sent = 0

    for i in range(0, len(new_records), batch_size):
        batch = new_records[i:i + batch_size]
        body = json.dumps({
            "client_id": client_id,
            "records": batch,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("X-Client-Id", client_id)
        req.add_header("X-Api-Key", api_key)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                total_sent += result.get("received", 0)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                logger.error("认证失败 (HTTP %d)，请检查 API_KEY", e.code)
                break
            logger.warning("上报失败 (HTTP %d): %s", e.code, e.reason)
        except Exception as e:
            logger.warning("上报失败: %s", e)

    # 保存已上报集合
    save_seen(seen)

    return {
        "sent": total_sent,
        "total_scanned": len(files),
        "seen_count": len(seen),
        "timestamp": datetime.now().isoformat(),
    }


def main():
    validate_mode = "--validate" in sys.argv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config()
    if not config:
        sys.exit(1)

    if validate_mode:
        report = validate_config(config)
        print_validate_report(report)
        if report["errors"]:
            sys.exit(1)
        return

    result = run_once(config)

    if result.get("error"):
        logger.error("运行失败: %s", result["error"])
        sys.exit(1)

    logger.info(
        "上报完成: sent=%d, scanned=%d files, seen=%d total",
        result.get("sent", 0),
        result.get("total_scanned", 0),
        result.get("seen_count", 0),
    )

    save_state(result)


if __name__ == "__main__":
    main()
