#!/bin/bash
# ============================================================
#  OpenClaw Monitor Reporter — 一键安装脚本
# ============================================================
#  将本机 OpenClaw 轨迹数据定时上报到中心监控服务器。
#
#  使用方式:
#    bash ~/.openclaw/plugin-skills/openclaw-monitor/scripts/setup.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.openclaw-monitor"
CONFIG_FILE="$CONFIG_DIR/config.sh"
PYTHON="python3"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   OpenClaw Monitor Reporter Setup   ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ---- 检查 Python ----
echo "[1/4] 检查环境..."
if ! command -v $PYTHON &>/dev/null; then
    echo "  错误: 未找到 python3"
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# ---- 收集配置 ----
echo ""
echo "[2/4] 配置上报参数"
echo ""

read -p "  监控服务器地址 (e.g. http://47.251.96.81:8000): " SERVER_URL
SERVER_URL="${SERVER_URL%/}"
if [ -z "$SERVER_URL" ]; then
    echo "  错误: 服务器地址不能为空"
    exit 1
fi

# 自动生成 client_id
DEFAULT_CLIENT_ID="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo "unknown")"
read -p "  本机客户端名称 ($DEFAULT_CLIENT_ID): " CLIENT_NAME
CLIENT_NAME="${CLIENT_NAME:-$DEFAULT_CLIENT_ID}"
CLIENT_ID="$(echo "$CLIENT_NAME" | tr 'A-Z ' 'a-z-')"

read -p "  API Key (在服务器上运行 register-client 获取): " API_KEY
if [ -z "$API_KEY" ]; then
    echo "  错误: API Key 不能为空"
    echo ""
    echo "  请先在服务器上注册客户端并获取 API Key:"
    echo "    ssh <server> 'cd /opt/openclaw-log-etl && python3 -m server.manage register-client $CLIENT_ID \"$CLIENT_NAME\"'"
    exit 1
fi

# 自动发现 OpenClaw sessions 目录
DEFAULT_SESSIONS="${HOME}/.openclaw/agents/main/sessions"
FOUND_DIRS=$(find /home -path '*/.openclaw/agents/main/sessions' -type d 2>/dev/null | head -5)

if [ -n "$FOUND_DIRS" ]; then
    FOUND_COUNT=$(echo "$FOUND_DIRS" | wc -l | tr -d ' ')
    if [ "$FOUND_COUNT" -eq 1 ]; then
        DEFAULT_SESSIONS="$FOUND_DIRS"
        echo "  自动发现 sessions 目录: $DEFAULT_SESSIONS"
    else
        echo "  发现多个可能的 sessions 目录:"
        echo "$FOUND_DIRS" | while read -r DIR; do
            FILE_COUNT=$(ls "$DIR"/*.trajectory.jsonl 2>/dev/null | wc -l | tr -d ' ')
            echo "    - $DIR ($FILE_COUNT 个轨迹文件)"
        done
        FIRST_DIR=$(echo "$FOUND_DIRS" | head -1)
        DEFAULT_SESSIONS="$FIRST_DIR"
    fi
else
    if [ ! -d "$DEFAULT_SESSIONS" ]; then
        echo "  注意: 默认路径 $DEFAULT_SESSIONS 不存在"
        echo "  请确认 OpenClaw 已在此机器上运行过"
    fi
fi

read -p "  OpenClaw sessions 目录 ($DEFAULT_SESSIONS): " CUSTOM_DIR
SESSIONS_DIR="${CUSTOM_DIR:-$DEFAULT_SESSIONS}"

# ---- 保存配置 ----
echo ""
echo "[3/4] 保存配置..."
mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" << EOF
# OpenClaw Monitor Reporter 配置
export SERVER_URL="$SERVER_URL"
export CLIENT_ID="$CLIENT_ID"
export CLIENT_NAME="$CLIENT_NAME"
export API_KEY="$API_KEY"
export SESSIONS_DIR="$SESSIONS_DIR"
EOF

chmod 600 "$CONFIG_FILE"
echo "  配置已保存: $CONFIG_FILE"

# ---- 安装 cron 定时任务 ----
echo ""
echo "[4/4] 设置定时上报（每 5 分钟）..."

REPORTER="$SCRIPT_DIR/reporter.py"

# ---- 校验配置 ----
echo ""
echo "[4/5] 校验 sessions 目录..."
VALIDATE_OUTPUT=$($PYTHON "$REPORTER" --validate 2>&1)
echo "$VALIDATE_OUTPUT"

if echo "$VALIDATE_OUTPUT" | grep -q "问题:"; then
    echo "  警告: sessions 目录校验发现问题，请确认路径正确"
    echo "  你可以稍后修改配置: vim $CONFIG_FILE"
fi

# ---- 安装 cron 定时任务 ----
echo ""
echo "[5/5] 设置定时上报（每 5 分钟）..."

CRON_LINE="*/5 * * * * $PYTHON $REPORTER >> $CONFIG_DIR/cron.log 2>&1"

# 检查是否已存在 cron 任务
if crontab -l 2>/dev/null | grep -F "$REPORTER" > /dev/null; then
    echo "  定时任务已存在，跳过。"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "  定时任务已添加。"
fi

# ---- 首次运行 ----
echo ""
echo "  ══════════════════════════════════════"
echo "  安装完成！正在首次上报..."
echo ""

$PYTHON "$REPORTER"

echo ""
echo "  ══════════════════════════════════════"
echo "  全部就绪！"
echo ""
echo "  本机标识:  $CLIENT_ID ($CLIENT_NAME)"
echo "  服务器:    $SERVER_URL"
echo "  Dashboard: $SERVER_URL/api/v1/dashboard"
echo ""
echo "  后续管理:"
echo "    手动上报 : $PYTHON $REPORTER"
echo "    修改配置 : vim $CONFIG_FILE"
echo "    查看日志 : tail -f $CONFIG_DIR/cron.log"
echo "    卸载      : crontab -e (删除 openclaw-monitor 行)"
echo "                rm -rf $CONFIG_DIR"
echo ""
echo "  想在其他机器上接入，把这个目录拷贝过去再跑一次 setup.sh 即可。"
echo ""
