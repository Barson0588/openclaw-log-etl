"""生成模拟 OpenClaw 日志数据，运行一次即可生成 mock_data.json。"""
import json
import random
from datetime import datetime, timedelta

random.seed(42)

# ---- 配置参数 ----
DAYS = 30
RECORDS_PER_DAY = (12, 22)  # 每天 12~22 条
START_DATE = "2026-06-22"

TOOL_NAMES = [
    "read_file", "write_file", "bash_exec",
    "web_search", "web_fetch", "grep_search", "agent_invoke",
]
ERROR_TYPES = ["timeout", "api_error", "rate_limit", "parse_error", "auth_error"]

records = []
task_counter = 1
start = datetime.strptime(START_DATE, "%Y-%m-%d")

for day_offset in range(DAYS):
    date = start + timedelta(days=day_offset)
    n = random.randint(*RECORDS_PER_DAY)

    for _ in range(n):
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        ts = date.replace(hour=hour, minute=minute, second=second)

        status = "success" if random.random() < 0.78 else "failed"
        error_type = None if status == "success" else random.choice(ERROR_TYPES)

        # duration_ms: 正态分布, 均值 2000ms, 范围 [200, 15000]
        duration = max(200, min(15000, int(random.gauss(2000, 2000))))

        # tool_calls_count: 1~20
        tool_calls = random.randint(1, 20)

        # tokens_used: 偏态分布, 大部分集中在 500~5000, 偶有大的
        tokens = max(100, int(random.gauss(2000, 1500)))

        record = {
            "task_id": f"task_{task_counter:04d}",
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_ms": duration,
            "tool_calls_count": tool_calls,
            "tokens_used": tokens,
            "status": status,
            "error_type": error_type,
            "tool_name": random.choice(TOOL_NAMES),
        }
        records.append(record)
        task_counter += 1

import os
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_data.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

print(f"生成完成: {len(records)} 条记录 → {output_path}")
