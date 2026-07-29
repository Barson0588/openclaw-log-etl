# Client Onboarding Reliability — Design

## Problem

server-01 接入时，setup.sh 默认 `SESSIONS_DIR` 设为 `/root/.openclaw/...`，但 OpenClaw
实际以 `admin` 用户运行，轨迹文件在 `/home/admin/.openclaw/...`。reporter 每 5 分钟
扫描空目录始终返回 `scanned=0`，无任何错误提示。整个故障在接入端完全静默。

## Root Causes

1. **路径发现**：setup.sh 不检查实际 sessions 目录位置，盲目默认 `$HOME/.openclaw/...`
2. **配置校验**：保存配置后不做目录存在性/可读性验证
3. **故障感知**：reporter 日志不区分"目录为空"和"目录不存在"

## Design

三处改动，只涉及 `setup.sh` 和 `reporter.py`：

### 1. setup.sh: 自动发现 sessions 目录

```bash
# 扫描系统上所有可能的 OpenClaw sessions 路径
FOUND_DIRS=$(find /home -path '*/.openclaw/agents/main/sessions' -type d 2>/dev/null)
# 找到一个 → 自动填入；多个 → 列出让用户选；找不到 → 提示手动输入
# 保存前验证：目录存在 + 可读 + 有 *.trajectory.jsonl 文件
```

### 2. setup.sh: 写入配置后冒烟测试

调用 `python3 reporter.py --validate` 做只读诊断，结果直接反馈给用户：
- 通过：`Sessions directory OK, found N trajectory files`
- 失败：`ERROR: <path> does not exist / is empty / not readable`

### 3. reporter.py: 增加 --validate 模式 + 诊断日志

- `--validate` 标志：扫描目录、解析首条记录、输出诊断报告，**不上报**
- `run_once()` 改进日志：
  - 目录不存在 → `logger.error("Sessions directory not found: %s", path)`
  - 目录为空 → `logger.warning("No trajectory files found in %s", path)`
  - 正常扫描 → 保持现有 INFO

## Scope

- 改动文件：`scripts/setup.sh` (~20 行), `scripts/reporter.py` (~30 行)
- 无新依赖，无新文件
- 兼容已有配置，不影响现有上报逻辑
