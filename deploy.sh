#!/bin/bash
# deploy.sh — 部署 OpenClaw ETL + 监控服务端到远程服务器
# 使用方式: ./deploy.sh root@47.251.96.81
#
# 部署内容:
#   1. FastAPI 监控服务端 (端口 8000) — 多客户端 Dashboard + API
#   2. 后台上报客户端 — 将本机 OpenClaw 轨迹上报到服务端
#   3. ETL 管线 + watcher (端口 8889) — 本地报表生成
#
set -e
HOST="${1:?请指定 SSH 主机，例如: ./deploy.sh root@47.251.96.81}"
REMOTE_DIR="/opt/openclaw-log-etl"
SERVER_PORT=8000
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 上传项目文件 ==="
ssh "$HOST" "mkdir -p $REMOTE_DIR/server $REMOTE_DIR/client $REMOTE_DIR/templates"

# 核心 ETL 模块
scp -r \
  "$PROJECT_DIR/main.py" \
  "$PROJECT_DIR/data_pipeline.py" \
  "$PROJECT_DIR/analyzer.py" \
  "$PROJECT_DIR/report_generator.py" \
  "$PROJECT_DIR/openclaw_adapter.py" \
  "$PROJECT_DIR/notify.py" \
  "$PROJECT_DIR/watcher.py" \
  "$PROJECT_DIR/requirements.txt" \
  "$HOST:$REMOTE_DIR/"

# 服务端模块
scp -r \
  "$PROJECT_DIR/server/"*.py \
  "$HOST:$REMOTE_DIR/server/"

# 客户端模块
scp -r \
  "$PROJECT_DIR/client/"*.py \
  "$HOST:$REMOTE_DIR/client/"

# 模板文件
scp -r \
  "$PROJECT_DIR/templates/"*.html \
  "$HOST:$REMOTE_DIR/templates/"

echo "=== 安装依赖 ==="
ssh "$HOST" "cd $REMOTE_DIR && pip3 install -r requirements.txt -q"

echo "=== 初始化数据库 ==="
ssh "$HOST" "cd $REMOTE_DIR && python3 -c 'from server.db import init_db; init_db()'"

echo "=== 配置 systemd 服务 ==="
# FastAPI 监控服务端
ssh "$HOST" "cat > /etc/systemd/system/openclaw-server.service << 'UNIT'
[Unit]
Description=OpenClaw Monitor Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$REMOTE_DIR
ExecStart=python3 -m uvicorn server.server:app --host 0.0.0.0 --port $SERVER_PORT
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT"

# 后台上报客户端（将本机 OpenClaw 轨迹上报到服务端）
ssh "$HOST" "cat > /etc/systemd/system/openclaw-reporter.service << 'UNIT'
[Unit]
Description=OpenClaw Telemetry Reporter
After=openclaw-server.service

[Service]
Type=simple
WorkingDirectory=$REMOTE_DIR
ExecStart=python3 -m client.client_skill
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=OPENCLAW_SERVER_URL=http://127.0.0.1:$SERVER_PORT
Environment=OPENCLAW_CLIENT_ID=server-01
Environment=OPENCLAW_API_KEY=placeholder
Environment=OPENCLAW_SESSIONS_DIR=/root/.openclaw/agents/main/sessions

[Install]
WantedBy=multi-user.target
UNIT"

echo "=== 启动服务 ==="
ssh "$HOST" "systemctl daemon-reload && systemctl enable openclaw-server && systemctl restart openclaw-server"

echo "=== 开放防火墙端口 ==="
ssh "$HOST" "
  if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --add-port=$SERVER_PORT/tcp --permanent 2>/dev/null
    firewall-cmd --reload 2>/dev/null
  elif command -v ufw &>/dev/null; then
    ufw allow $SERVER_PORT/tcp 2>/dev/null
  fi
  echo '防火墙已配置'
" || echo "(防火墙配置跳过，请手动开放端口 $SERVER_PORT)"

echo ""
echo "========================================"
echo "  部署完成！"
echo "  Dashboard: http://${HOST#*@}:$SERVER_PORT/api/v1/dashboard"
echo "  API 文档:  http://${HOST#*@}:$SERVER_PORT/docs"
echo "========================================"
echo ""
echo "后续步骤:"
echo "  1. 在服务器上注册客户端并获取 API Key:"
echo "     ssh $HOST 'cd $REMOTE_DIR && python3 -m server.manage register-client server-01 \"Linux Server\"'"
echo "  2. 将 API Key 填入 openclaw-reporter.service:"
echo "     ssh $HOST 'systemctl edit openclaw-reporter'"
echo "  3. 启动上报客户端:"
echo "     ssh $HOST 'systemctl enable --now openclaw-reporter'"
echo ""
