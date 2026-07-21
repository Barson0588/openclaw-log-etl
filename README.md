# OpenClaw Log ETL

OpenClaw 智能体任务日志的 ETL 管线与交互式仪表盘。

从 trajectory JSONL 文件中采集 OpenClaw agent 的运行日志，清洗统计后生成自包含的 HTML 仪表盘，支持定时调度和多渠道通知。

## 架构

```
trajectory.jsonl  →  data_pipeline  →  CSV  →  analyzer  →  report_generator  →  HTML/MD
                         ↑                           │
                   openclaw_adapter                  ├── 4 张 PNG 图表
                                                     └── 交互记录 + 统计摘要
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# Mock 数据测试
python main.py --now

# 真实 OpenClaw 数据
python main.py --now --real

# 真实数据 + 周报
python main.py --now --real --weekly

# 定时调度模式（每日凌晨 2:00）
python main.py
```

## 模块说明

| 文件 | 功能 |
|------|------|
| `main.py` | 调度主入口，串联三步流水线，支持 `--now` / `--real` / `--weekly` / `--sessions-dir` 参数 |
| `data_pipeline.py` | 数据采集（Mock / 真实 OpenClaw）、清洗（去重/格式标准化）、CSV 存储 |
| `openclaw_adapter.py` | 解析 `~/.openclaw/agents/main/sessions/*.trajectory.jsonl`，提取任务指标和交互记录 |
| `analyzer.py` | 统计分析与可视化：成功率、错误分布、工具使用、Token 消耗 + 4 张 matplotlib 图表 |
| `report_generator.py` | Markdown + 自包含 HTML 仪表盘（SVG 图表、深色模式、日期筛选、侧边栏导航） |
| `notify.py` | 多渠道通知：SMTP 邮件 + 企业微信 Webhook，通过环境变量配置 |
| `generate_mock_data.py` | 生成模拟 trajectory 数据用于开发测试 |
| `mock_data.json` | 513 条 Mock 数据（30 天跨度） |

## 仪表盘功能

- **概览页**：KPI 卡片（含日环比箭头）、SVG 趋势图、健康评级
- **失败明细**：可排序/分页的失败任务列表 + 重试风暴检测 + 详情弹窗
- **Token 分析**：Token 消耗趋势 + 直方图 + 成本估算 + 超额告警
- **错误趋势**：堆叠面积图展示各类错误日变化
- **时段热力图**：24h × 日期失败率热力图
- **交互记录**：搜索/筛选/分页查看所有 OpenClaw 对话记录（含提问内容）
- **全局功能**：日期范围筛选、深色模式、CSV 导出、移动端适配

## 通知配置

```bash
# SMTP 邮件
export NOTIFY_SMTP_HOST=smtp.qq.com
export NOTIFY_SMTP_PORT=587
export NOTIFY_SMTP_USER=your@qq.com
export NOTIFY_SMTP_PASS=your_auth_code
export NOTIFY_TO=receiver@example.com

# 企业微信 Webhook
export NOTIFY_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
```

## 远程部署

```bash
# SSH 到服务器并运行
ssh root@<host> 'cd /root/openclaw-log-etl && python3 main.py --now --real --sessions-dir /path/to/sessions'
```

## 数据格式

trajectory JSONL 文件中的关键事件类型：

| 事件 | 提取字段 |
|------|---------|
| `session.started` | timestamp, trigger, model_id |
| `context.compiled` | user_prompt（用户提问内容） |
| `model.completed` | tokens_used |
| `trace.artifacts` | tool_calls, tool_names, lastToolError |
| `session.ended` | status, error_type, duration |

## 依赖

- Python ≥ 3.9
- pandas ≥ 2.0, matplotlib ≥ 3.7, seaborn ≥ 0.12
- schedule ≥ 1.2（定时调度）
- 中文字体：macOS（STHeiti）/ Linux（Noto Sans CJK）/ Windows（SimHei）

## License

MIT
