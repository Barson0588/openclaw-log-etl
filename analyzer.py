"""
统计分析与可视化模块 (analyzer.py)
====================================
读取清洗后的 CSV，使用 pandas 进行分组聚合计算关键指标，
使用 matplotlib + seaborn 生成 4 张分析图表并保存为 PNG。

设计思路:
  - LogAnalyzer 类在构造时只记录路径，调用 .load() 才真正读 CSV
  - 一次加载后缓存在 self.df，所有分析方法复用，避免重复 I/O
  - 每个分析方法返回 (图表文件路径, 关联的统计 dict)，供报表模块使用
"""

import logging
import os

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# =====================================================================
#  matplotlib / seaborn 全局样式配置
# =====================================================================

# 注意: sns.set_style() 会重置 font.sans-serif 为默认值，
# 因此中文字体配置必须在 seaborn 样式设置之后执行。

# seaborn 白色网格风格，视觉更清爽
sns.set_style("whitegrid")
sns.set_palette("Set2")

# 中文字体 —— 通过 font_manager 直接指定系统字体文件路径
_font_candidates = [
    "/System/Library/Fonts/STHeiti Light.ttc",     # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",    # macOS
    "/System/Library/Fonts/Supplemental/Songti.ttc",  # macOS
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",  # Linux (Noto CJK)
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Light.ttc",    # Linux
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux (WenQuanYi)
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Linux
    "C:/Windows/Fonts/simhei.ttf",                 # Windows
    "C:/Windows/Fonts/msyh.ttc",                   # Windows
]
_cjk_font_prop = None
for _fp in _font_candidates:
    try:
        _prop = fm.FontProperties(fname=_fp)
        _prop.get_name()  # 强制触发字体文件加载验证
        _cjk_font_prop = _prop
        break
    except (FileNotFoundError, RuntimeError, OSError):
        continue

if _cjk_font_prop is not None:
    _font_name = _cjk_font_prop.get_name()
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [_font_name]
else:
    # 动态搜索：查找系统上任意可用的 CJK 字体
    _fallback_font = None
    for _f in fm.fontManager.ttflist:
        _fname_lower = (_f.name or "").lower()
        if any(kw in _fname_lower for kw in ["cjk", "noto", "wenquan", "hei", "song", "ming", "kai", "fang", "gothic"]):
            try:
                _fallback_font = fm.FontProperties(fname=_f.fname)
                break
            except (FileNotFoundError, RuntimeError):
                continue
    if _fallback_font is not None:
        _font_name = _fallback_font.get_name()
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [_font_name]
    else:
        plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei"]

plt.rcParams["axes.unicode_minus"] = False


class LogAnalyzer:
    """日志统计分析器。

    使用方式::

        analyzer = LogAnalyzer("data/cleaned_logs_2026-07-21.csv")
        analyzer.load()                             # 加载数据
        stats, chart_paths = analyzer.run_all()     # 一键执行全部分析
    """

    def __init__(self, csv_path, charts_dir="charts"):
        """
        Args:
            csv_path: 清洗后的 CSV 文件路径
            charts_dir: 图表输出目录
        """
        self.csv_path = csv_path
        self.charts_dir = charts_dir
        os.makedirs(charts_dir, exist_ok=True)
        self.df = None  # 延迟加载，避免不必要的 I/O

    # =================================================================
    #  数据加载
    # =================================================================

    def load(self):
        """加载清洗后的 CSV 数据，仅执行一次。

        使用 parse_dates 将 timestamp 列直接解析为 pandas datetime 类型，
        方便后续按日期分组。若文件不存在或为空则抛出明确错误。
        """
        logger.info("加载数据: %s", self.csv_path)

        # encoding='utf-8-sig' 兼容带 BOM 的 CSV（Excel 保存的常见格式）
        self.df = pd.read_csv(
            self.csv_path,
            parse_dates=["timestamp"],
            encoding="utf-8-sig",
        )
        logger.info("数据加载完成: %d 条记录, %d 个字段", len(self.df), len(self.df.columns))

        # 快速数据概览 log，方便核查
        logger.info(
            "数据概况 ─ 时间范围: %s ~ %s, 成功率: %.1f%%",
            self.df["timestamp"].min().strftime("%Y-%m-%d"),
            self.df["timestamp"].max().strftime("%Y-%m-%d"),
            (self.df["status"] == "success").mean() * 100,
        )
        return self

    # =================================================================
    #  图表 a: 每日任务成功率（折线图）
    # =================================================================

    def daily_success_rate(self):
        """计算每日任务成功率并绘制折线图。

        【原理讲解 — groupby + agg 分组聚合】
        pandas 的 .groupby() 类似 SQL 的 GROUP BY:
          1. df["date"] = df["timestamp"].dt.date  → 从时间戳提取日期
          2. .groupby("date")                       → 按日期分组
          3. .agg(total=..., success=...)           → 对每组做聚合计算
          4. success / total                        → 得到每日成功率

        聚合后得到每行一个日期的汇总表，再用 matplotlib 绘制折线。

        Returns:
            str: 图表保存路径
        """
        logger.info("生成图表: 每日任务成功率")

        # Step 1: 提取日期列（只保留日期部分，去掉时分秒）
        df = self.df.copy()
        df["date"] = df["timestamp"].dt.date

        # Step 2: 分组聚合 —— 每天的总任务数和成功任务数
        daily = df.groupby("date").agg(
            total=("task_id", "count"),
            success=("status", lambda s: (s == "success").sum()),
        ).reset_index()

        # Step 3: 计算成功率
        daily["success_rate"] = daily["success"] / daily["total"] * 100

        # Step 4: 绘图
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(
            daily["date"].astype(str), daily["success_rate"],
            marker="o", linewidth=2, markersize=5, color="#2a9d8f",
        )
        ax.axhline(
            y=daily["success_rate"].mean(), color="#e76f51",
            linestyle="--", linewidth=1,
            label=f'均值: {daily["success_rate"].mean():.1f}%',
        )
        ax.set_title("每日任务成功率", fontsize=14, fontweight="bold")
        ax.set_xlabel("日期", fontsize=11)
        ax.set_ylabel("成功率 (%)", fontsize=11)
        ax.set_ylim(0, 105)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()

        path = os.path.join(self.charts_dir, "daily_success_rate.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        logger.info("图表已保存: %s", path)
        return path

    # =================================================================
    #  图表 b: error_type 占比（饼图）
    # =================================================================

    def error_type_distribution(self):
        """统计各 error_type 的占比并绘制饼图。

        【原理讲解 — value_counts()】
        df["error_type"].value_counts() 相当于:
          SELECT error_type, COUNT(*) FROM df GROUP BY error_type ORDER BY COUNT(*) DESC
        它返回一个 Series，index 是 error_type 的值，values 是对应计数。

        饼图的 autopct='%1.1f%%' 参数自动在每个扇区标注百分比。

        Returns:
            str: 图表保存路径
        """
        logger.info("生成图表: 错误类型分布")

        # 只取失败任务的 error_type
        failed = self.df[self.df["status"] == "failed"]
        error_counts = failed["error_type"].value_counts()

        if len(error_counts) == 0:
            logger.info("无失败任务，跳过错误类型饼图")
            return None

        fig, ax = plt.subplots(figsize=(7, 7))
        wedges, texts, autotexts = ax.pie(
            error_counts.values,
            labels=error_counts.index,
            autopct="%1.1f%%",
            startangle=140,
            colors=sns.color_palette("Set2", len(error_counts)),
        )
        ax.set_title("失败任务 — 错误类型分布", fontsize=14, fontweight="bold")

        # 调整百分比文字颜色和大小
        for at in autotexts:
            at.set_fontsize(10)
            at.set_color("white")

        plt.tight_layout()

        path = os.path.join(self.charts_dir, "error_type_pie.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        logger.info("图表已保存: %s", path)
        return path

    # =================================================================
    #  图表 c: 工具使用频次 Top 5（柱状图）
    # =================================================================

    def top5_tool_usage(self):
        """统计 tool_name 的使用频次，取 Top 5 绘制横向柱状图。

        【原理讲解 — value_counts().head() 链式调用】
        value_counts() 默认按频次降序排列，.head(5) 取前 5 个。
        这是 pandas 常用的"一句话探索"手法，适合快速了解分类变量的分布。

        横向柱状图 (barh) 更适合展示带较长名称的分类数据，
        因为标签文字沿水平方向排列，便于阅读。

        Returns:
            str: 图表保存路径
        """
        logger.info("生成图表: 工具使用频次 Top 5")

        # 排除 "none" 和 NaN（表示没有工具调用的 session）
        tool_series = self.df["tool_name"].fillna("none").replace("", "none")
        tool_counts = tool_series[tool_series != "none"].value_counts().head(5)

        if len(tool_counts) == 0:
            logger.info("无有效工具使用数据，跳过此图表")
            return None

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.barh(
            tool_counts.index[::-1],   # 反转顺序使最高频的在最上面
            tool_counts.values[::-1],
            color=sns.color_palette("Set2", 5),
        )
        ax.set_title("工具使用频次 Top 5", fontsize=14, fontweight="bold")
        ax.set_xlabel("调用次数", fontsize=11)
        ax.set_ylabel("工具名称", fontsize=11)

        # 在柱条末端标注具体数值
        for bar, val in zip(bars, tool_counts.values[::-1]):
            ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                    str(val), va="center", fontsize=10)

        plt.tight_layout()

        path = os.path.join(self.charts_dir, "top5_tool_usage.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        logger.info("图表已保存: %s", path)
        return path

    # =================================================================
    #  图表 d: Token 消耗分布（箱线图 + 直方图并排）
    # =================================================================

    def token_distribution(self):
        """绘制 Token 消耗的箱线图和直方图（并排展示）。

        【原理讲解 — subplots 并排布局】
        plt.subplots(1, 2) 创建一行两列的画布:
          - 左侧 (ax[0]) 放箱线图，展示数据的四分位数、中位数和离群点
          - 右侧 (ax[1]) 放直方图 + KDE 密度曲线，展示数据分布形态

        箱线图解读:
          - 箱子：中间 50% 数据范围 (Q1~Q3)
          - 箱内竖线：中位数 (Q2)
          - 须线末端：1.5 倍 IQR 内的最远点
          - 须线外的点：潜在离群值

        Returns:
            str: 图表保存路径
        """
        logger.info("生成图表: Token 消耗分布")

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # 左侧: 箱线图
        ax = axes[0]
        ax.boxplot(
            self.df["tokens_used"].dropna(),
            vert=True,
            patch_artist=True,
            boxprops=dict(facecolor="#a8dadc", alpha=0.8),
            medianprops=dict(color="#e63946", linewidth=2),
        )
        ax.set_title("Token 消耗 - 箱线图", fontsize=13, fontweight="bold")
        ax.set_ylabel("Token 数量", fontsize=11)
        ax.set_xticklabels([])

        # 右侧: 直方图 + KDE
        ax = axes[1]
        sns.histplot(
            self.df["tokens_used"], bins=30,
            kde=True, color="#457b9d", alpha=0.6, ax=ax,
        )
        ax.axvline(
            x=self.df["tokens_used"].median(), color="#e63946",
            linestyle="--", linewidth=1.5,
            label=f'中位数: {self.df["tokens_used"].median():.0f}',
        )
        ax.set_title("Token 消耗 - 分布直方图", fontsize=13, fontweight="bold")
        ax.set_xlabel("Token 数量", fontsize=11)
        ax.set_ylabel("频次", fontsize=11)
        ax.legend()

        plt.tight_layout()

        path = os.path.join(self.charts_dir, "token_distribution.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        logger.info("图表已保存: %s", path)
        return path

    # =================================================================
    #  一键执行 + 统计摘要
    # =================================================================

    def run_all(self):
        """执行全部分析流程，生成 4 张图表并返回统计摘要。

        Returns:
            tuple[dict, dict, dict]:
              - stats: KPI 统计指标
              - chart_paths: 图表名 → 文件路径的映射
              - extra: 附加分析数据 (failure_details, raw_data, trigger_stats, hourly)
        """
        if self.df is None:
            self.load()

        success_mask = self.df["status"] == "success"
        failed_mask = self.df["status"] == "failed"

        # 计算 KPI 指标
        stats = {
            "total_tasks": len(self.df),
            "total_success": success_mask.sum(),
            "total_failed": failed_mask.sum(),
            "overall_success_rate": round(success_mask.mean() * 100, 2),
            "total_tokens": int(self.df["tokens_used"].sum()),
            "avg_tokens_per_task": round(self.df["tokens_used"].mean(), 1),
            "total_duration_seconds": round(self.df["duration_ms"].sum() / 1000, 1),
            "avg_duration_ms": round(self.df["duration_ms"].mean(), 1),
            "date_range_start": self.df["timestamp"].min().strftime("%Y-%m-%d"),
            "date_range_end": self.df["timestamp"].max().strftime("%Y-%m-%d"),
            "top_error_type": (
                self.df[failed_mask]["error_type"].value_counts().index[0]
                if failed_mask.sum() > 0
                and len(self.df[failed_mask]["error_type"].value_counts()) > 0
                else "N/A"
            ),
            # tool_name 可能全为空/NaN（CSV 回读时 "" 变 NaN，或无工具调用的 session）
            "top_tool": (
                self.df["tool_name"]
                .fillna("none")
                .replace("", "none")
                .pipe(lambda s: s[s != "none"])
                .value_counts()
                .index[0]
                if len(
                    self.df["tool_name"]
                    .fillna("none")
                    .replace("", "none")
                    .pipe(lambda s: s[s != "none"])
                    .value_counts()
                ) > 0
                else "N/A"
            ),
        }

        # 生成 4 张图表
        chart_paths = {
            "daily_success": self.daily_success_rate(),
            "error_type": self.error_type_distribution(),
            "top5_tool": self.top5_tool_usage(),
            "token_dist": self.token_distribution(),
        }

        logger.info("全部分析完成: %d 个 KPI, %d 张图表", len(stats), len(chart_paths))

        # 附加分析
        extra = {
            "failure_details": self._get_failure_details(),
            "raw_data": self._get_raw_data(),
            "trigger_stats": self._get_trigger_stats(),
            "hourly_pattern": self._get_hourly_pattern(),
            "error_trend": self._get_error_trend(),
            "retry_storms": self._get_retry_storms(),
            "daily_summary": self._get_daily_summary(),
        }

        return stats, chart_paths, extra

    # =================================================================
    #  附加分析方法 (供报表模块使用)
    # =================================================================

    def _get_failure_details(self):
        """获取所有失败任务的明细列表，按时间倒序。

        Returns:
            list[dict]: 每个失败任务的详细信息
        """
        failed = self.df[self.df["status"] == "failed"].copy()
        if failed.empty:
            return []

        failed = failed.sort_values("timestamp", ascending=False)
        records = []
        for _, row in failed.iterrows():
            ts = row["timestamp"]
            records.append({
                "task_id": str(row["task_id"]),
                "task_id_short": str(row["task_id"])[:20] + "...",
                "timestamp": ts.strftime("%Y-%m-%d %H:%M") if hasattr(ts, "strftime") else str(ts),
                "date": ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10],
                "hour": int(ts.hour) if hasattr(ts, "hour") else 0,
                "error_type": str(row["error_type"]) if row.get("error_type") and str(row["error_type"]) not in ("", "nan") else "unknown",
                "duration_sec": round(row["duration_ms"] / 1000, 1),
                "tokens_used": int(row["tokens_used"]),
                "tool_calls_count": int(row["tool_calls_count"]),
                "tool_name": str(row["tool_name"]) if str(row["tool_name"]) not in ("", "nan", "none") else "",
                "trigger": str(row.get("trigger", "unknown")),
            })
        return records

    def _get_raw_data(self):
        """获取全量数据的精简版，供前端交互查询。

        Returns:
            list[dict]: 每条记录的关键字段
        """
        records = []
        for _, row in self.df.iterrows():
            records.append({
                "task_id": str(row["task_id"])[:20] + "...",
                "timestamp": row["timestamp"].strftime("%Y-%m-%d %H:%M") if hasattr(row["timestamp"], "strftime") else str(row["timestamp"]),
                "date": row["timestamp"].strftime("%Y-%m-%d") if hasattr(row["timestamp"], "strftime") else str(row["timestamp"])[:10],
                "hour": int(row["timestamp"].hour) if hasattr(row["timestamp"], "hour") else 0,
                "status": str(row["status"]),
                "error_type": str(row["error_type"]) if row.get("error_type") and str(row["error_type"]) not in ("", "nan") else "",
                "duration_ms": int(row["duration_ms"]),
                "tokens_used": int(row["tokens_used"]),
                "tool_calls_count": int(row["tool_calls_count"]),
                "tool_name": str(row["tool_name"]) if str(row["tool_name"]) not in ("", "nan", "none") else "",
                "trigger": str(row.get("trigger", "unknown")),
            })
        return records

    def _get_trigger_stats(self):
        """按 trigger 类型分组的统计。"""
        if "trigger" not in self.df.columns:
            return []
        result = []
        for name, grp in self.df.groupby("trigger"):
            total = len(grp)
            success = (grp["status"] == "success").sum()
            result.append({
                "trigger": str(name),
                "total": total,
                "success": int(success),
                "failed": total - int(success),
                "success_rate": round(success / total * 100, 1),
                "avg_tokens": round(grp["tokens_used"].mean(), 0),
                "avg_duration_sec": round(grp["duration_ms"].mean() / 1000, 1),
            })
        return sorted(result, key=lambda x: -x["total"])

    def _get_hourly_pattern(self):
        """按小时统计失败分布（0-23 点）。"""
        df = self.df.copy()
        df["hour"] = df["timestamp"].dt.hour
        hourly = []
        for h in range(24):
            hour_data = df[df["hour"] == h]
            total = len(hour_data)
            failed = (hour_data["status"] == "failed").sum()
            hourly.append({
                "hour": h,
                "total": total,
                "failed": int(failed),
                "success": total - int(failed),
                "failure_rate": round(failed / total * 100, 1) if total > 0 else 0,
            })
        return hourly

    def _get_daily_summary(self):
        """获取全量逐日汇总数据，供前端 SVG 图表和 KPI 对比箭头使用。

        Returns:
            list[dict]: 每日 {date, total, success, failed, success_rate, tokens, avg_duration_sec,
                              tool_usage: {tool_name: count}, error_counts: {error_type: count}}
        """
        df = self.df.copy()
        df["date"] = df["timestamp"].dt.date

        result = []
        for d_val, grp in df.groupby("date", sort=True):
            total = len(grp)
            success = int((grp["status"] == "success").sum())
            failed = total - success

            # 工具使用计数
            tool_series = grp["tool_name"].fillna("none").replace("", "none")
            tool_series = tool_series[tool_series != "none"]
            tool_usage = {}
            for t in tool_series:
                tool_usage[t] = tool_usage.get(t, 0) + 1

            # 错误类型计数
            failed_rows = grp[grp["status"] == "failed"]
            error_counts = {}
            for et in failed_rows["error_type"]:
                et_str = str(et) if str(et) not in ("", "nan") else "unknown"
                error_counts[et_str] = error_counts.get(et_str, 0) + 1

            result.append({
                "date": d_val.strftime("%Y-%m-%d"),
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
                "tokens": int(grp["tokens_used"].sum()),
                "avg_tokens": round(grp["tokens_used"].mean(), 0),
                "avg_duration_sec": round(grp["duration_ms"].mean() / 1000, 1) if total > 0 else 0,
                "tool_usage": tool_usage,
                "error_counts": error_counts,
            })

        return result

    def _get_error_trend(self):
        """每日各错误类型的任务数量，供前端绘制堆叠面积图。

        Returns:
            list[dict]: [{"date": "2026-07-01", "error_type_A": 5, "error_type_B": 2, ...}, ...]
        """
        df = self.df.copy()
        df["date"] = df["timestamp"].dt.date

        # 获取所有唯一的日期和错误类型
        dates = sorted(df["date"].unique())
        error_types = sorted(df[df["status"] == "failed"]["error_type"].dropna().unique())

        trend = []
        for d in dates:
            day_data = df[df["date"] == d]
            row = {"date": d.strftime("%Y-%m-%d")}
            for et in error_types:
                row[et] = int((day_data["error_type"] == et).sum())
            row["success"] = int((day_data["status"] == "success").sum())
            trend.append(row)

        return trend

    def _get_retry_storms(self):
        """检测重试风暴：同一 trigger 短时间内（10分钟窗口）连续失败 >= 5 次的事件。

        扫描失败任务，按 trigger 分组后在时间轴上滑动窗口检测密集失败。

        Returns:
            list[dict]: 每个风暴事件的信息
        """
        from collections import defaultdict

        failed = self.df[self.df["status"] == "failed"].copy()
        if failed.empty:
            return []

        # 按 trigger 分组
        groups = defaultdict(list)
        for _, row in failed.iterrows():
            groups[str(row.get("trigger", "unknown"))].append(row)

        storms = []
        for trigger, rows in groups.items():
            if len(rows) < 5:
                continue
            # 按时间排序
            sorted_rows = sorted(rows, key=lambda r: r["timestamp"])
            # 滑动窗口检测
            for i in range(len(sorted_rows) - 4):
                window = sorted_rows[i:i + 5]
                t0 = window[0]["timestamp"]
                t4 = window[4]["timestamp"]
                window_minutes = (t4 - t0).total_seconds() / 60
                if window_minutes <= 10:
                    storms.append({
                        "trigger": trigger,
                        "start_time": t0.strftime("%Y-%m-%d %H:%M"),
                        "end_time": t4.strftime("%Y-%m-%d %H:%M"),
                        "window_minutes": round(window_minutes, 1),
                        "count": len(window),
                        "task_ids": [str(w["task_id"])[:20] + "..." for w in window],
                        "error_types": list(set(str(w["error_type"]) for w in window if str(w["error_type"]) not in ("", "nan"))),
                        "total_tokens": int(sum(w["tokens_used"] for w in window)),
                    })
                    # 跳过已检测到的窗口
                    break

        # 按 count 降序排列
        return sorted(storms, key=lambda s: -s["count"])

    def get_weekly_stats(self):
        """获取周报所需的聚合指标。

        将全量数据按周分组，提供本周与上周的对比数据。

        Returns:
            dict: 包含 weekly_summary, daily_averages, week_over_week 等
        """
        if self.df is None:
            self.load()

        df = self.df.copy()
        df["date"] = df["timestamp"].dt.date
        df["week"] = df["timestamp"].dt.isocalendar().week
        df["year"] = df["timestamp"].dt.isocalendar().year
        df["week_label"] = df["year"].astype(str) + "-W" + df["week"].astype(str).str.zfill(2)

        # 按周聚合
        weekly = []
        for (year, week), grp in df.groupby(["year", "week"], sort=True):
            total = len(grp)
            success = (grp["status"] == "success").sum()
            failed = total - success
            weekly.append({
                "year": int(year),
                "week": int(week),
                "label": f"{int(year)}-W{int(week):02d}",
                "total": total,
                "success": int(success),
                "failed": int(failed),
                "success_rate": round(success / total * 100, 1),
                "total_tokens": int(grp["tokens_used"].sum()),
                "avg_tokens": round(grp["tokens_used"].mean(), 0),
                "avg_duration_sec": round(grp["duration_ms"].mean() / 1000, 1),
                "top_error": (
                    grp[grp["status"] == "failed"]["error_type"].value_counts().index[0]
                    if failed > 0 else "N/A"
                ),
                "dates": f"{grp['date'].min()} ~ {grp['date'].max()}",
            })

        # 本周 vs 上周对比
        current_week = weekly[-1] if weekly else None
        prev_week = weekly[-2] if len(weekly) >= 2 else None
        wow = {}
        if current_week and prev_week:
            wow = {
                "rate_change": round(current_week["success_rate"] - prev_week["success_rate"], 1),
                "token_change_pct": (
                    round((current_week["total_tokens"] - prev_week["total_tokens"]) / max(prev_week["total_tokens"], 1) * 100, 1)
                ),
                "task_change_pct": (
                    round((current_week["total"] - prev_week["total"]) / max(prev_week["total"], 1) * 100, 1)
                ),
                "current_label": current_week["label"],
                "prev_label": prev_week["label"],
            }

        # 最近 7 天逐日汇总
        all_dates = sorted(df["date"].unique())
        recent_dates = all_dates[-7:]
        daily_summary = []
        for d in recent_dates:
            day = df[df["date"] == d]
            total = len(day)
            success = (day["status"] == "success").sum()
            daily_summary.append({
                "date": d.strftime("%Y-%m-%d"),
                "total": total,
                "success": int(success),
                "failed": total - int(success),
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
                "tokens": int(day["tokens_used"].sum()),
                "avg_duration_sec": round(day["duration_ms"].mean() / 1000, 1) if total > 0 else 0,
            })

        return {
            "weekly_summary": weekly,
            "current_week": current_week,
            "prev_week": prev_week,
            "week_over_week": wow,
            "daily_summary": daily_summary,
        }
