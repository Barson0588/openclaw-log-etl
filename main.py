"""
调度主入口 (main.py)
=====================
将 data_pipeline → analyzer → report_generator 三个模块串联，
使用 schedule 库实现每日定时自动执行。

使用方式:
    python main.py --now       # 立即执行一次完整流程
    python main.py             # 启动定时调度（默认每天凌晨 2:00）

【原理讲解 — schedule 库的调度机制】
schedule 是一个轻量级任务调度库，工作方式是"轮询 + 匹配":
  1. schedule.every().day.at("02:00").do(job_func)  — 注册任务
  2. while True: schedule.run_pending(); time.sleep(60) — 每分钟检查一次
     是否有到期任务需要执行
  3. 它不是真正的 cron，进程退出后调度就停止了
     对于生产环境建议升级为 Airflow/Prefect，或使用系统 crontab
"""

import argparse
import logging
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import schedule

from data_pipeline import DataPipeline
from analyzer import LogAnalyzer
from report_generator import ReportGenerator


def setup_logging():
    """配置日志：同时输出到文件和控制台。

    使用 UTF-8 编码确保中文日志正常显示。
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("pipeline.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _build_interactions_from_df(df):
    """从清洗后的 DataFrame 构建交互记录列表。

    用于 mock 模式 — mock 数据缺少 trigger / user_prompt / model_id，
    这里用可用字段填充，缺失字段设为合理默认值。
    """
    interactions = []
    for _, row in df.iterrows():
        ts = row.get("timestamp", "")
        ts_str = str(ts) if ts else ""
        # 解析日期和小时
        date_str = ts_str[:10] if len(ts_str) >= 10 else ""
        hour = 0
        try:
            hour = datetime.strptime(ts_str[:13], "%Y-%m-%d %H").hour
        except Exception:
            pass

        # 判断触发类型 — mock 数据中按 task_id hash 分配 cron/user
        trigger = ""
        if "trigger" in df.columns and not pd.isna(row.get("trigger")):
            trigger = str(row.get("trigger"))
        if not trigger:
            # 基于 task_id 的确定性分配，让触发类型看起来更真实
            tid = str(row.get("task_id", ""))
            trigger = "cron" if (hash(tid) % 3 != 0) else "user"

        status = str(row.get("status", "unknown"))
        error_type = row.get("error_type", "")
        if error_type is None or (isinstance(error_type, float) and np.isnan(error_type)):
            error_type = ""
        else:
            error_type = str(error_type)

        tool_name = str(row.get("tool_name", "")) if not pd.isna(row.get("tool_name", "none")) else "none"

        interactions.append({
            "task_id": str(row.get("task_id", "")),
            "task_id_short": str(row.get("task_id", ""))[:8] + "...",
            "timestamp": ts_str,
            "date": date_str,
            "hour": hour,
            "trigger": trigger,
            "user_prompt": "(Mock 数据 — 无原始提问内容)",
            "prompt_preview": "(Mock 数据)",
            "model_id": row.get("model_id", "mock-model") if "model_id" in df.columns else "mock-model",
            "provider": "mock",
            "status": status,
            "error_type": error_type,
            "duration_ms": int(row.get("duration_ms", 0)) if not pd.isna(row.get("duration_ms", 0)) else 0,
            "tokens_used": int(row.get("tokens_used", 0)) if not pd.isna(row.get("tokens_used", 0)) else 0,
            "tool_calls_count": int(row.get("tool_calls_count", 0)) if not pd.isna(row.get("tool_calls_count", 0)) else 0,
            "tool_name": tool_name,
            "tool_names": [tool_name] if tool_name and tool_name != "none" else [],
        })

    # 按时间倒序排列
    interactions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return interactions


def run_pipeline(api_url=None, mock_data_path="mock_data.json",
                 use_real_data=False, sessions_dir=None, weekly=False):
    """执行一次完整的 ETL 流程。

    三步流水线:
      1. DataPipeline  — 采集 + 清洗 + 存 CSV
      2. LogAnalyzer   — 读 CSV + 统计 + 出图
      3. ReportGenerator — 读统计 + 拼装 Markdown/HTML 报表

    Args:
        api_url: OpenClaw API 地址
        mock_data_path: mock JSON 文件路径
        use_real_data: True 时从本地 OpenClaw 环境读取真实 trajectory 数据
        sessions_dir: trajectory 文件目录，use_real_data=True 时生效
        weekly: True 时额外生成周报

    Returns:
        str: 生成的报表文件路径
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("开始执行 OpenClaw ETL 管线 (数据源: %s)",
                "真实 OpenClaw 环境" if use_real_data else "Mock 模拟数据")
    logger.info("=" * 50)

    # ---- Step 1: 数据采集与清洗 ----
    logger.info("[Step 1/3] 数据采集与清洗")
    pipeline = DataPipeline(api_url=api_url, mock_data_path=mock_data_path)

    interactions = None
    if use_real_data:
        from openclaw_adapter import OpenClawAdapter
        adapter = OpenClawAdapter(sessions_dir)
        df, interactions = adapter.load_all()
        logger.info("[Step 1/3] 交互记录: %d 条", len(interactions))
    else:
        df = pipeline.fetch_logs()

    df = pipeline.clean(df)
    csv_path = pipeline.save(df)
    logger.info("[Step 1/3] 完成 — CSV: %s", csv_path)

    # Mock 模式下从清洗数据构建交互记录
    if not use_real_data and interactions is None:
        interactions = _build_interactions_from_df(df)
        logger.info("[Step 1/3] 交互记录 (从 mock 构建): %d 条", len(interactions))

    # ---- Step 2: 统计分析与可视化 ----
    logger.info("[Step 2/3] 统计分析与可视化")
    analyzer = LogAnalyzer(csv_path)
    stats, chart_paths, extra = analyzer.run_all()
    logger.info("[Step 2/3] 完成 — 生成 %d 张图表", len(chart_paths))

    # ---- Step 3: 报表生成 ----
    logger.info("[Step 3/3] 报表生成")
    reporter = ReportGenerator()
    md_path = reporter.generate(stats, chart_paths)
    html_path = reporter.generate_html(stats, chart_paths, extra, interactions=interactions)
    logger.info("[Step 3/3] 完成 — Markdown: %s", md_path)
    logger.info("[Step 3/3] 完成 — HTML: %s", html_path)

    # ---- 周报（可选） ----
    if weekly:
        logger.info("[Step 3/3] 生成周报")
        weekly_stats = analyzer.get_weekly_stats()
        weekly_path = reporter.generate_weekly_html(
            stats, chart_paths, extra, weekly_stats
        )
        logger.info("[Step 3/3] 周报完成 — HTML: %s", weekly_path)

    # ---- Step 4: 通知推送（可选，需配置环境变量） ----
    try:
        from notify import Notifier
        notifier = Notifier()
        notifier.send(stats, html_path)
    except Exception:
        logger.debug("通知模块加载失败，跳过推送", exc_info=True)

    # ---- 汇总 ----
    logger.info("=" * 50)
    logger.info(
        "ETL 管线执行成功 — 成功率: %.1f%%, Token 总消耗: %s",
        stats["overall_success_rate"],
        f"{stats['total_tokens']:,}",
    )
    logger.info("=" * 50)

    return html_path


def main():
    """主函数：解析命令行参数，启动立即执行或定时调度。"""
    setup_logging()
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="OpenClaw 智能体任务日志 ETL 管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python main.py --now                    立即执行（Mock 数据）
    python main.py --now --real             立即执行（真实 OpenClaw 数据）
    python main.py --now --real --weekly    立即执行 + 生成周报
    python main.py                          启动定时调度（每日 02:00）
        """,
    )
    parser.add_argument(
        "--now", action="store_true",
        help="立即执行一次完整 ETL 流程",
    )
    parser.add_argument(
        "--real", action="store_true",
        help="使用本地 OpenClaw 环境的真实 trajectory 数据（而非 mock）",
    )
    parser.add_argument(
        "--sessions-dir", type=str, default=None,
        help="trajectory 文件目录 (默认 ~/.openclaw/agents/main/sessions)",
    )
    parser.add_argument(
        "--api-url", type=str, default=None,
        help="OpenClaw API 地址（不指定则使用 mock 数据）",
    )
    parser.add_argument(
        "--weekly", action="store_true",
        help="额外生成周报 (周环比 + 历史周趋势)",
    )
    args = parser.parse_args()

    if args.now:
        # 立即执行模式
        try:
            run_pipeline(
                api_url=args.api_url,
                use_real_data=args.real,
                sessions_dir=args.sessions_dir,
                weekly=args.weekly,
            )
        except Exception:
            logger.exception("ETL 管线执行失败")
            sys.exit(1)
    else:
        # 定时调度模式
        # 注册每日凌晨 2:00 的任务
        schedule.every().day.at("02:00").do(
            run_pipeline, api_url=args.api_url
        )

        logger.info("调度已启动: 每日凌晨 02:00 执行 ETL 管线")
        logger.info("按 Ctrl+C 退出")

        # 主循环：每分钟检查一次是否有待执行任务
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("调度已手动停止")


if __name__ == "__main__":
    main()
