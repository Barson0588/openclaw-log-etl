---
name: openclaw-monitor
description: "OpenClaw 遥测监控上报 — 把本机轨迹数据自动推送到中心监控服务端，多机器数据汇总到统一 Dashboard。"
---

# OpenClaw Monitor Reporter

将本机 OpenClaw 任务轨迹数据自动上报到你部署的监控服务器，实现多机器数据汇总、可视化 Dashboard、多客户端对比。

## 首次安装

在终端中运行 setup 脚本：

```bash
bash ~/.openclaw/plugin-skills/openclaw-monitor/scripts/setup.sh
```

按提示输入：
1. 监控服务器地址（如 `http://47.251.96.81:8000`）
2. 本机客户端名称（如 `MacBook Pro`、`Office PC`）
3. 服务器管理员给你的 API Key（需要在服务器上用 `python3 -m server.manage register-client <id> <name>` 获取）

脚本会自动安装依赖、保存配置、创建定时上报任务。

## 工作方式

- 通过 cron 每 5 分钟运行一次 `scripts/reporter.py`
- reporter 扫描本机 `~/.openclaw/agents/main/sessions/*.trajectory.jsonl`
- 自动去重：已上报的 task_id 不会重复发送
- POST 到服务器 `/api/v1/telemetry`
- 上报失败不阻塞，下次自动重试

## 管理

```bash
# 查看上报状态和已上报记录数
cat ~/.openclaw-monitor/state.json

# 手动触发一次上报
python3 ~/.openclaw/plugin-skills/openclaw-monitor/scripts/reporter.py

# 修改配置
vim ~/.openclaw-monitor/config.sh

# 移除定时任务
crontab -e  # 删除 openclaw-monitor 那行
```

## 如果用户在服务器上注册客户端时遇到问题

帮助他们用 `python3 -m server.manage register-client <id> <name>` 注册，返回的 API Key 填入 `~/.openclaw-monitor/config.sh`。
