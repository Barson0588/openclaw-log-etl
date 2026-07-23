#!/bin/bash
# deploy.sh — 部署 OpenClaw ETL 到远程服务器
# 使用方式: ./deploy.sh root@47.251.96.81

set -e
HOST="${1:?请指定 SSH 主机，例如: ./deploy.sh root@47.251.96.81}"
REMOTE_DIR="/opt/openclaw-log-etl"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 上传项目文件 ==="
ssh "$HOST" "mkdir -p $REMOTE_DIR"
scp -r \
  "$PROJECT_DIR/main.py" \
  "$PROJECT_DIR/data_pipeline.py" \
  "$PROJECT_DIR/analyzer.py" \
  "$PROJECT_DIR/report_generator.py" \
  "$PROJECT_DIR/openclaw_adapter.py" \
  "$PROJECT_DIR/notify.py" \
  "$PROJECT_DIR/watcher.py" \
  "$PROJECT_DIR/requirements.txt" \
  "$PROJECT_DIR/templates/" \
  "$HOST:$REMOTE_DIR/"

echo "=== 安装依赖 ==="
ssh "$HOST" "cd $REMOTE_DIR && pip3 install -r requirements.txt -q"

echo "=== 检查 trajectory 数据目录 ==="
ssh "$HOST" "ls ~/.openclaw/agents/main/sessions/*.trajectory.jsonl 2>/dev/null | wc -l || echo '警告: 无 trajectory 文件'"

echo "=== 启动 watcher（后台） ==="
ssh "$HOST" "cd $REMOTE_DIR && pkill -f 'python.*watcher.py' 2>/dev/null; nohup python3 watcher.py --no-browser > watcher.log 2>&1 &"

echo "=== 开放防火墙端口 ==="
ssh "$HOST" "firewall-cmd --add-port=8889/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null; echo '端口已开放'"

echo ""
echo "部署完成！访问: http://$HOST:8889"
