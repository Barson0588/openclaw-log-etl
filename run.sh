#!/bin/bash
# ============================================================
#  OpenClaw Log ETL — 一键启动脚本
# ============================================================
#  用法:
#    ./run.sh              # 使用 mock 数据测试
#    ./run.sh --real       # 检测本地 OpenClaw 真实数据
#    ./run.sh --real --weekly   # 真实数据 + 生成周报
#    ./run.sh --real --sessions-dir /path/to/sessions  # 指定数据目录
# ============================================================

set -e
cd "$(dirname "$0")"

PYTHON="python3"
PROJECT_DIR="$(pwd)"
DASHBOARD="$PROJECT_DIR/reports/dashboard_$(date +%Y-%m-%d).html"

echo "=========================================="
echo "  OpenClaw Log ETL 管线"
echo "  项目路径: $PROJECT_DIR"
echo "=========================================="

# ---- 检测 Python ----
echo "[检查] Python 环境..."
if ! command -v $PYTHON &>/dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# ---- 检测依赖 ----
echo "[检查] 依赖包..."
MISSING=""
for pkg in pandas matplotlib seaborn schedule; do
    if ! $PYTHON -c "import $pkg" 2>/dev/null; then
        MISSING="$MISSING $pkg"
    fi
done
if [ -n "$MISSING" ]; then
    echo "  缺少依赖:$MISSING"
    echo "  正在安装..."
    pip3 install $MISSING
fi
echo "  依赖就绪"

# ---- 检测 OpenClaw 数据 ----
if [[ "$*" == *"--real"* ]]; then
    SESSIONS_DIR="${HOME}/.openclaw/agents/main/sessions"
    if [ -d "$SESSIONS_DIR" ]; then
        COUNT=$(find "$SESSIONS_DIR" -name "*.trajectory.jsonl" | wc -l | tr -d ' ')
        echo "[数据] 检测到 $COUNT 个 trajectory 文件"
    else
        echo "[数据] 未找到 $SESSIONS_DIR，请确认 OpenClaw 已安装并运行过"
    fi
fi

# ---- 运行 ETL 管线 ----
echo "=========================================="
echo "[运行] 开始 ETL 管线..."
echo "=========================================="

$PYTHON main.py --now "$@"

# ---- 打开报表 ----
if [ -f "$DASHBOARD" ]; then
    echo ""
    echo "=========================================="
    echo "  报表已生成: $DASHBOARD"
    echo "=========================================="
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "$DASHBOARD"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        xdg-open "$DASHBOARD" 2>/dev/null || echo "  请手动打开: $DASHBOARD"
    fi
fi
