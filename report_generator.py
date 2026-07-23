"""
报表生成模块 (report_generator.py)
===================================
将统计分析结果和可视化图表路径，动态拼装为 Markdown 和 HTML 两种格式的监控报表。

设计思路:
  - ReportGenerator 接收 stats dict 和 chart_paths dict
  - generate() 输出 Markdown，供归档和 Git 版本管理
  - generate_html() 输出自包含 HTML，图表 base64 内嵌，直接浏览器打开
  - HTML 报表按"KPI 卡片 → 图表区 → 综合评估"三段式布局
"""

import base64
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class ReportGenerator:
    """多格式监控报表生成器。

    使用方式::

        gen = ReportGenerator(output_dir="reports")
        gen.generate(stats, chart_paths)           # Markdown
        gen.generate_html(stats, chart_paths)      # HTML 仪表盘
    """

    def __init__(self, output_dir="reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # =================================================================
    #  Markdown 报表
    # =================================================================

    def generate(self, stats, chart_paths, output_path=None):
        """生成 Markdown 报表。"""
        if output_path is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = os.path.join(self.output_dir, f"report_{date_str}.md")

        sections = [
            self._build_header(),
            self._build_kpi_section(stats),
            self._build_chart_section(chart_paths),
            self._build_detail_section(stats),
            self._build_footer(),
        ]
        content = "\n\n".join(sections)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Markdown 报表已生成: %s", output_path)
        return output_path

    # =================================================================
    #  HTML 仪表盘（自包含，图表 base64 内嵌）
    # =================================================================

    def generate_html(self, stats, chart_paths, extra=None, output_path=None, interactions=None):
        """生成自包含的交互式 HTML 仪表盘。

        Args:
            stats: KPI 指标
            chart_paths: 图表路径映射
            extra: 附加数据 {failure_details, raw_data, trigger_stats, hourly_pattern}
            output_path: 输出路径
            interactions: 完整交互记录列表（含用户提问内容）
        """
        if extra is None:
            extra = {}

        if output_path is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = os.path.join(self.output_dir, f"dashboard_{date_str}.html")

        html = self._build_html_document(stats, chart_paths, extra, interactions)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("HTML 仪表盘已生成: %s", output_path)
        return output_path

    def generate_weekly_html(self, stats, chart_paths, extra=None, weekly_stats=None, output_path=None):
        """生成周报 HTML 仪表盘。

        Args:
            stats: KPI 指标
            chart_paths: 图表路径映射
            extra: 附加数据
            weekly_stats: analyzer.get_weekly_stats() 的返回值
            output_path: 输出路径
        """
        if extra is None:
            extra = {}
        if weekly_stats is None:
            weekly_stats = {}

        if output_path is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_path = os.path.join(self.output_dir, f"weekly_report_{date_str}.html")

        html = self._build_weekly_html(stats, chart_paths, extra, weekly_stats)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("周报 HTML 已生成: %s", output_path)
        return output_path

    def _build_weekly_html(self, stats, chart_paths, extra, weekly_stats):
        """构建周报 HTML 文档。"""
        import json

        def to_safe(obj):
            import numpy as np
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, dict): return {k: to_safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)): return [to_safe(v) for v in obj]
            return obj

        today = datetime.now().strftime("%Y年%m月%d日")
        chart_blocks = self._build_html_charts(chart_paths)
        daily_json = json.dumps(to_safe(weekly_stats.get("daily_summary", [])), ensure_ascii=False)
        weekly_json = json.dumps(to_safe(weekly_stats.get("weekly_summary", [])), ensure_ascii=False)
        wow_json = json.dumps(to_safe(weekly_stats.get("week_over_week", {})), ensure_ascii=False)
        current_json = json.dumps(to_safe(weekly_stats.get("current_week", {})), ensure_ascii=False)
        prev_json = json.dumps(to_safe(weekly_stats.get("prev_week", {})), ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenClaw 监控周报 — {today}</title>
<style>
  :root {{
    --bg: #f5f6fa; --card-bg: #ffffff; --text: #2d3436; --muted: #636e72;
    --accent: #2a9d8f; --danger: #e76f51; --warn: #f4a261;
    --border: #e0e4e8; --radius: 12px;
    --shadow: 0 1px 3px rgba(0,0,0,.06);
  }}
  body.dark {{
    --bg: #1a1a2e; --card-bg: #16213e; --text: #e0e0e0; --muted: #a0a0b0;
    --border: #2a2a4a; --shadow: 0 1px 3px rgba(0,0,0,.3);
  }}
  *,*::before,*::after{{margin:0;padding:0;box-sizing:border-box;}}
  strong,h1,h2,h3,h4{{color:inherit;}}
  h1,h2,h3,h4{{word-break:break-word;overflow-wrap:break-word;}}
  body{{
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--text);line-height:1.6;
    padding:24px 24px 64px;max-width:1200px;margin:0 auto;overflow-x:hidden;
    transition:background .3s,color .3s;
  }}
  .topbar{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:24px;}}
  .topbar h1{{font-size:clamp(1.1rem,3vw,1.5rem);font-weight:700;}}
  .btn{{padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--card-bg);color:var(--text);cursor:pointer;font-size:.8rem;font-family:inherit;}}
  .btn:hover{{border-color:var(--accent);}}

  /* 周环比卡片 */
  .wow-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px;}}
  .wow-card{{background:var(--card-bg);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow);}}
  .wow-card .label{{font-size:.75rem;color:var(--muted);}}
  .wow-card .value{{font-size:1.3rem;font-weight:700;margin-top:4px;}}
  .wow-card .change{{font-size:.78rem;margin-top:2px;}}
  .up{{color:var(--danger);}}.down{{color:var(--accent);}}.flat{{color:var(--muted);}}

  /* 图表/表格区 */
  .section{{margin-bottom:24px;}}
  .section h2{{font-size:1.1rem;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--border);}}
  .chart-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px;}}
  .chart-card{{background:var(--card-bg);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow);}}
  .chart-card img{{width:100%;height:auto;border-radius:6px;}}
  table{{width:100%;border-collapse:collapse;font-size:.82rem;}}
  th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--border);}}
  th{{background:var(--bg);color:var(--muted);font-weight:600;font-size:.78rem;}}
  .badge-sm{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:600;}}
  .badge-sm.good{{background:#d4edda;color:#155724;}}
  .badge-sm.warn{{background:#fff3cd;color:#856404;}}
  .badge-sm.bad{{background:#f8d7da;color:#721c24;}}

  .footer{{text-align:center;color:var(--muted);font-size:.78rem;margin-top:32px;}}
  @media(max-width:600px){{
    body{{padding:12px 10px 32px;}}
    .wow-grid{{grid-template-columns:repeat(2,1fr);gap:8px;}}
    .chart-grid{{grid-template-columns:1fr;}}
  }}

  body.dark svg text {{ fill: #c0c0d0; }}
  body.dark svg line {{ stroke: #3a3a5a; }}
</style></style>
</head>
<body>

<div class="topbar">
  <h1>OpenClaw 监控周报</h1>
  <button class="btn" id="themeToggle" onclick="toggleTheme()">暗色模式</button>
</div>

<div class="wow-grid" id="wowCards"></div>

<div class="section">
  <h2>本周逐日数据</h2>
  <div style="overflow-x:auto;">
    <table id="dailyTable"><thead><tr>
      <th>日期</th><th>总数</th><th>成功</th><th>失败</th><th>成功率</th><th>Token</th><th>平均耗时(s)</th>
    </tr></thead><tbody></tbody></table>
  </div>
</div>

<div class="section">
  <h2>历史周趋势</h2>
  <div style="overflow-x:auto;">
    <table id="weeklyTable"><thead><tr>
      <th>周次</th><th>日期范围</th><th>总数</th><th>成功率</th><th>Token</th><th>最高频错误</th>
    </tr></thead><tbody></tbody></table>
  </div>
</div>

<div class="section">
  <h2>可视化分析图表</h2>
  <div class="chart-grid">
    {chart_blocks}
  </div>
</div>

<div class="footer">周报由 OpenClaw ETL 管线自动生成 &nbsp;|&nbsp; {today}</div>

<script>
var DAILY_SUMMARY = {daily_json};
var WEEKLY_SUMMARY = {weekly_json};
var WOW = {wow_json};
var CURRENT_WEEK = {current_json};
var PREV_WEEK = {prev_json};
var darkMode = false;

function toggleTheme() {{
  darkMode = !darkMode;
  document.body.classList.toggle('dark', darkMode);
  document.getElementById('themeToggle').textContent = darkMode ? '亮色模式' : '暗色模式';
}}

function arrow(v) {{
  if (v > 0) return '<span class="up">&#9650; ' + v + '</span>';
  if (v < 0) return '<span class="down">&#9660; ' + Math.abs(v) + '</span>';
  return '<span class="flat">&#9644; 0</span>';
}}

function arrowPct(v) {{
  if (v > 0) return '<span class="up">&#9650; ' + v + '%</span>';
  if (v < 0) return '<span class="down">&#9660; ' + Math.abs(v) + '%</span>';
  return '<span class="flat">&#9644; 0%</span>';
}}

// 周环比卡片
(function() {{
  var cw = CURRENT_WEEK;
  var pw = PREV_WEEK;
  var wow = WOW;
  var hasWow = Object.keys(wow).length > 0;

  var cards = '';
  if (cw) {{
    var rateTone = cw.success_rate >= 95 ? 'good' : (cw.success_rate >= 85 ? 'warn' : 'bad');
    cards += '<div class="wow-card"><div class="label">本周成功率</div>' +
      '<div class="value" style="color:var(--' + (rateTone === 'good' ? 'accent' : rateTone === 'warn' ? 'warn' : 'danger') + ')">' + cw.success_rate + '%</div>' +
      (hasWow ? '<div class="change">' + arrow(wow.rate_change) + 'pp vs 上周</div>' : '') + '</div>';
    cards += '<div class="wow-card"><div class="label">本周任务数</div>' +
      '<div class="value">' + cw.total + '</div>' +
      (hasWow ? '<div class="change">' + arrowPct(wow.task_change_pct) + ' vs 上周</div>' : '') + '</div>';
    cards += '<div class="wow-card"><div class="label">本周 Token 消耗</div>' +
      '<div class="value">' + (cw.total_tokens || 0).toLocaleString() + '</div>' +
      (hasWow ? '<div class="change">' + arrowPct(wow.token_change_pct) + ' vs 上周</div>' : '') + '</div>';
    cards += '<div class="wow-card"><div class="label">最高频错误</div>' +
      '<div class="value" style="font-size:.95rem;">' + (cw.top_error || 'N/A') + '</div></div>';
  }}
  document.getElementById('wowCards').innerHTML = cards || '<p style="color:var(--muted)">暂无周数据</p>';
}})();

// 逐日表
(function() {{
  var html = '';
  DAILY_SUMMARY.forEach(function(d) {{
    var tone = d.success_rate >= 95 ? 'good' : (d.success_rate >= 85 ? 'warn' : 'bad');
    html += '<tr><td><strong>' + d.date + '</strong></td>' +
      '<td>' + d.total + '</td><td>' + d.success + '</td><td>' + d.failed + '</td>' +
      '<td><span class="badge-sm ' + tone + '">' + d.success_rate + '%</span></td>' +
      '<td>' + (d.tokens || 0).toLocaleString() + '</td>' +
      '<td>' + d.avg_duration_sec + '</td></tr>';
  }});
  document.querySelector('#dailyTable tbody').innerHTML = html || '<tr><td colspan="7" style="color:var(--muted)">无数据</td></tr>';
}})();

// 历史周趋势
(function() {{
  var html = '';
  var weeks = WEEKLY_SUMMARY.slice(-12);
  weeks.forEach(function(w) {{
    var tone = w.success_rate >= 95 ? 'good' : (w.success_rate >= 85 ? 'warn' : 'bad');
    html += '<tr><td><strong>' + w.label + '</strong></td>' +
      '<td>' + w.dates + '</td><td>' + w.total + '</td>' +
      '<td><span class="badge-sm ' + tone + '">' + w.success_rate + '%</span></td>' +
      '<td>' + (w.total_tokens || 0).toLocaleString() + '</td>' +
      '<td>' + w.top_error + '</td></tr>';
  }});
  document.querySelector('#weeklyTable tbody').innerHTML = html || '<tr><td colspan="6" style="color:var(--muted)">无数据</td></tr>';
}})();
</script>

</body>
</html>"""

    # =================================================================
    #  HTML 构建
    # =================================================================

    def _build_html_document(self, stats, chart_paths, extra=None, interactions=None):
        """组装交互式 HTML 仪表盘，从外部模板文件渲染。"""
        if extra is None:
            extra = {}
        if interactions is None:
            interactions = []
        import json

        def to_safe(obj):
            import numpy as np
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, dict): return {k: to_safe(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)): return [to_safe(v) for v in obj]
            return obj

        today = datetime.now().strftime("%Y年%m月%d日")

        ctx = {
            "today": today,
            "raw_data_json": json.dumps(to_safe(extra.get("raw_data", [])), ensure_ascii=False),
            "failure_details_json": json.dumps(to_safe(extra.get("failure_details", [])), ensure_ascii=False),
            "trigger_stats_json": json.dumps(to_safe(extra.get("trigger_stats", [])), ensure_ascii=False),
            "hourly_pattern_json": json.dumps(to_safe(extra.get("hourly_pattern", [])), ensure_ascii=False),
            "error_trend_json": json.dumps(to_safe(extra.get("error_trend", [])), ensure_ascii=False),
            "retry_storms_json": json.dumps(to_safe(extra.get("retry_storms", [])), ensure_ascii=False),
            "daily_summary_json": json.dumps(to_safe(extra.get("daily_summary", [])), ensure_ascii=False),
            "stats_json": json.dumps(to_safe(stats), ensure_ascii=False),
            "interactions_json": json.dumps(
                to_safe(self._truncate_interactions(interactions)), ensure_ascii=False
            ),
            "chart_paths_json": json.dumps(to_safe(chart_paths), ensure_ascii=False),
        }

        template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()

        return template.format(**ctx)


    def _status_badge(self, success_rate):
        if success_rate >= 95:
            return f'<span class="badge badge-success">运行良好 {success_rate}%</span>'
        elif success_rate >= 85:
            return f'<span class="badge badge-warn">需要关注 {success_rate}%</span>'
        else:
            return f'<span class="badge badge-danger">异常偏低 {success_rate}%</span>'

    def _build_html_kpi_cards(self, stats):
        """构建 KPI 卡片 HTML。"""
        cards = [
            ("任务总数", f'{stats["total_tasks"]}', "", "neutral"),
            ("成功率", f'{stats["overall_success_rate"]}', "%",
             "good" if stats["overall_success_rate"] >= 95 else
             "warn" if stats["overall_success_rate"] >= 85 else "bad"),
            ("Token 总消耗", f'{stats["total_tokens"]:,}', "", "neutral"),
            ("平均 Token/任务", f'{stats["avg_tokens_per_task"]}', "", "neutral"),
            ("总耗时", f'{stats["total_duration_seconds"]:,}', "秒", "neutral"),
            ("平均耗时", f'{stats["avg_duration_ms"]}', "ms/任务", "neutral"),
            ("最高频错误", stats["top_error_type"], "", "neutral"),
            ("最高频工具", stats["top_tool"], "", "neutral"),
        ]
        html_parts = []
        for label, value, unit, tone in cards:
            css_class = f"value {tone}" if tone != "neutral" else "value"
            unit_span = f'<span class="unit">{unit}</span>' if unit else ""
            html_parts.append(
                f'<div class="kpi-card">'
                f'<div class="label">{label}</div>'
                f'<div class="{css_class}">{value}{unit_span}</div>'
                f'</div>'
            )
        return "\n  ".join(html_parts)

    def _build_html_charts(self, chart_paths):
        """构建图表区 HTML，图片 base64 内嵌。"""
        label_map = [
            ("daily_success", "每日任务成功率",
             "反映系统稳定性趋势，波动过大时需关注对应日期的事故"),
            ("error_type", "错误类型占比",
             "帮助定位主要故障原因，优先解决占比最高的错误"),
            ("top5_tool", "工具使用频次 Top 5",
             "反映智能体最常用的能力，指导资源优化方向"),
            ("token_dist", "Token 消耗分布",
             "了解单次任务的资源消耗水平和离群情况"),
        ]
        blocks = []
        for key, title, desc in label_map:
            path = chart_paths.get(key)
            if path and os.path.exists(path):
                b64 = self._image_to_base64(path)
                blocks.append(
                    f'<div class="chart-card">'
                    f'<h3>{title}</h3>'
                    f'<div class="desc">{desc}</div>'
                    f'<img src="data:image/png;base64,{b64}" alt="{title}">'
                    f'</div>'
                )
            else:
                blocks.append(
                    f'<div class="chart-empty">'
                    f'<h3>{title}</h3>'
                    f'<p>{desc}</p>'
                    f'<p style="margin-top:12px">（无数据，已跳过）</p>'
                    f'</div>'
                )
        return "\n    ".join(blocks)

    def _build_html_assessment(self, stats):
        """构建评估建议 HTML。"""
        success_rate = stats["overall_success_rate"]
        daily_tokens = stats["total_tokens"] / max(stats["total_tasks"], 1)

        if success_rate >= 95:
            level = "良好"
            suggestion = "系统运行稳定，各项指标处于健康水平。"
        elif success_rate >= 85:
            level = "一般"
            suggestion = f'建议关注失败任务的原因分布，优先排查 <strong>{stats["top_error_type"]}</strong> 类型错误。'
        else:
            level = "需要关注"
            suggestion = f'成功率偏低 ({success_rate}%)，建议立即排查 <strong>{stats["top_error_type"]}</strong> 类型错误，检查消息推送通道是否正常。'

        return f"""<p style="margin-bottom:8px"><strong>系统健康评级: {level}</strong></p>
    <p>{suggestion}</p>
    <ul style="margin-top:12px; color: var(--muted);">
      <li><strong>Token 消耗</strong>: 日均约 {daily_tokens:,.0f} tokens，可据此预估 API 成本</li>
      <li><strong>耗时分析</strong>: 平均 {stats["avg_duration_ms"]}ms/任务，总耗时 {stats["total_duration_seconds"]:,} 秒</li>
      <li><strong>任务分布</strong>: {stats["total_success"]} 成功 / {stats["total_failed"]} 失败 (共 {stats["total_tasks"]} 条)</li>
    </ul>"""

    # =================================================================
    #  工具方法
    # =================================================================

    @staticmethod
    def _truncate_interactions(interactions, max_prompt=200):
        """Truncate user_prompt in interactions to reduce embedded JSON size."""
        light = []
        for it in interactions:
            it_light = dict(it)
            prompt = it_light.get("user_prompt", "")
            if isinstance(prompt, str) and len(prompt) > max_prompt:
                it_light["user_prompt"] = prompt[:max_prompt] + "..."
            light.append(it_light)
        return light

    @staticmethod
    def _image_to_base64(image_path):
        """将 PNG 图片编码为 base64 字符串。"""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except (OSError, IOError) as e:
            logger = logging.getLogger(__name__)
            logger.warning("图表文件读取失败: %s — %s", image_path, e)
            return ""

    # =================================================================
    #  Markdown 构建 (保持原有方法)
    # =================================================================

    def _build_header(self):
        today = datetime.now().strftime("%Y年%m月%d日")
        return (
            f"# OpenClaw 智能体任务日志 — 监控日报\n\n"
            f"**生成时间**: {today}  \n"
            f"**数据来源**: OpenClaw Agent Task Logs\n\n"
            f"---"
        )

    def _build_kpi_section(self, stats):
        return (
            f"## 一、关键指标概览 (KPI)\n\n"
            f"| 指标 | 数值 |\n"
            f"|------|------|\n"
            f"| 任务总数 | {stats['total_tasks']} |\n"
            f"| 成功任务数 | {stats['total_success']} |\n"
            f"| 失败任务数 | {stats['total_failed']} |\n"
            f"| **整体成功率** | **{stats['overall_success_rate']}%** |\n"
            f"| Token 总消耗 | {stats['total_tokens']:,} |\n"
            f"| 平均每任务 Token | {stats['avg_tokens_per_task']} |\n"
            f"| 总耗时 (秒) | {stats['total_duration_seconds']:,} |\n"
            f"| 平均耗时 (ms) | {stats['avg_duration_ms']} |\n"
            f"| 最高频错误类型 | {stats['top_error_type']} |\n"
            f"| 最高频工具 | {stats['top_tool']} |\n"
            f"| 数据时间范围 | {stats['date_range_start']} ~ {stats['date_range_end']} |\n"
        )

    def _build_chart_section(self, chart_paths):
        lines = ["## 二、可视化分析图表\n"]
        label_map = [
            ("daily_success", "每日任务成功率", "反映系统稳定性趋势，波动过大时需关注对应日期的事故"),
            ("error_type", "错误类型占比", "帮助定位主要故障原因，优先解决占比最高的错误"),
            ("top5_tool", "工具使用频次 Top 5", "反映智能体最常用的能力，指导资源优化方向"),
            ("token_dist", "Token 消耗分布", "了解单次任务的资源消耗水平和离群情况"),
        ]
        for key, title, desc in label_map:
            path = chart_paths.get(key)
            if path:
                rel_path = os.path.join("..", "charts", os.path.basename(path))
                lines.append(f"### {title}\n")
                lines.append(f"> {desc}\n")
                lines.append(f"![{title}]({rel_path})\n")
            else:
                lines.append(f"### {title}\n")
                lines.append(f"> {desc}\n")
                lines.append(f"*（无数据，已跳过）*\n")
        return "\n".join(lines)

    def _build_detail_section(self, stats):
        success_rate = stats["overall_success_rate"]
        if success_rate >= 95:
            assessment = "系统运行**良好**，成功率处于健康水平。"
        elif success_rate >= 85:
            assessment = "系统运行**一般**，建议关注失败任务的原因分布。"
        else:
            assessment = f"系统运行**需要关注**，成功率偏低 ({success_rate}%)，建议排查 `{stats['top_error_type']}` 类型错误。"
        return (
            f"## 三、综合评估与建议\n\n"
            f"{assessment}\n\n"
            f"- **Token 消耗**: 日均约 {stats['total_tokens'] / max(stats['total_tasks'], 1):,.0f} tokens，"
            f"可据此预估 API 成本\n"
            f"- **耗时分析**: 平均 {stats['avg_duration_ms']}ms/任务，"
            f"总耗时 {stats['total_duration_seconds']:,} 秒\n"
        )

    def _build_footer(self):
        return (
            f"---\n\n"
            f"*报表由 OpenClaw ETL 管线自动生成，每日凌晨更新。*"
        )
