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
        """组装交互式 HTML 仪表盘 — 侧边栏导航 + 子页面布局，降低信息密度。"""
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
        chart_blocks = self._build_html_charts(chart_paths)

        raw_data_json = json.dumps(to_safe(extra.get("raw_data", [])), ensure_ascii=False)
        failure_details_json = json.dumps(to_safe(extra.get("failure_details", [])), ensure_ascii=False)
        trigger_stats_json = json.dumps(to_safe(extra.get("trigger_stats", [])), ensure_ascii=False)
        hourly_pattern_json = json.dumps(to_safe(extra.get("hourly_pattern", [])), ensure_ascii=False)
        error_trend_json = json.dumps(to_safe(extra.get("error_trend", [])), ensure_ascii=False)
        retry_storms_json = json.dumps(to_safe(extra.get("retry_storms", [])), ensure_ascii=False)
        daily_summary_json = json.dumps(to_safe(extra.get("daily_summary", [])), ensure_ascii=False)
        stats_json = json.dumps(to_safe(stats), ensure_ascii=False)
        interactions_json = json.dumps(to_safe(interactions), ensure_ascii=False)
        chart_paths_json = json.dumps(to_safe(chart_paths), ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenClaw 监控日报 — {today}</title>
<style>
  :root {{
    --bg: #f5f6fa; --card-bg: #ffffff; --text: #2d3436; --muted: #636e72;
    --accent: #2a9d8f; --danger: #e76f51; --warn: #f4a261;
    --border: #e0e4e8; --radius: 10px;
    --shadow: 0 1px 3px rgba(0,0,0,.06);
    --sidebar-w: 220px;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    margin: 0; overflow-x: hidden;
    transition: background .3s, color .3s;
  }}
  body.dark {{
    --bg: #1a1a2e; --card-bg: #16213e; --text: #e0e0e0; --muted: #a0a0b0;
    --border: #2a2a4a; --shadow: 0 1px 3px rgba(0,0,0,.3);
  }}
  *,*::before,*::after{{margin:0;padding:0;box-sizing:border-box;}}
  strong,h1,h2,h3,h4{{color:inherit;}}
  h1,h2,h3,h4{{word-break:break-word;overflow-wrap:break-word;}}

  /* 侧边栏 */
  .sidebar {{
    position: fixed; top: 0; left: 0; bottom: 0; width: var(--sidebar-w);
    background: var(--card-bg); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; z-index: 100;
    overflow-y: auto; transition: transform .25s;
  }}
  .sidebar-header {{
    padding: 20px 18px 16px; border-bottom: 1px solid var(--border);
  }}
  .sidebar-header h2 {{ font-size: .95rem; font-weight: 700; word-break: break-word; overflow: hidden; text-overflow: ellipsis; }}
  .sidebar-header .sub {{ font-size: .7rem; color: var(--muted); margin-top: 2px; }}
  .sidebar-nav {{ flex: 1; padding: 10px 0; }}
  .sidebar-nav a {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    display: flex; align-items: center; gap: 10px; padding: 10px 18px;
    color: var(--text); text-decoration: none; font-size: .84rem;
    transition: background .15s; border-left: 3px solid transparent;
    cursor: pointer;
  }}
  .sidebar-nav a:hover {{ background: var(--bg); }}
  .sidebar-nav a.active {{
    background: var(--bg); border-left-color: var(--accent);
    color: var(--accent); font-weight: 600;
  }}
  .sidebar-nav a .ico {{ font-size: 1rem; width: 22px; text-align: center; flex-shrink: 0; }}
  .sidebar-nav a .badge-dot {{
    margin-left: auto; width: 8px; height: 8px; border-radius: 50%;
    background: var(--danger); flex-shrink: 0;
  }}
  .sidebar-footer {{ padding: 12px 18px; border-top: 1px solid var(--border); }}
  .sidebar-footer .btn {{
    display: block; width: 100%; padding: 7px 14px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--card-bg); color: var(--text);
    cursor: pointer; font-size: .78rem; font-family: inherit; text-align: center;
    margin-bottom: 6px; transition: background .15s;
  }}
  .sidebar-footer .btn:hover {{ border-color: var(--accent); }}

  /* 主内容区 */
  .main {{
    margin-left: var(--sidebar-w); padding: 28px 32px 64px;
    max-width: calc(1280px - var(--sidebar-w)); min-height: 100vh;
  }}
  .page {{ display: none; }}
  .page.active {{ display: block; }}

  /* 筛选条 */
  .filter-bar {{
    background: var(--card-bg); border-radius: var(--radius); padding: 12px 16px;
    box-shadow: var(--shadow); margin-bottom: 20px;
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  }}
  .filter-bar label {{ font-size: .78rem; color: var(--muted); white-space: nowrap; }}
  .filter-bar input[type="date"] {{
    padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px;
    font-size: .8rem; font-family: inherit; background: var(--card-bg); color: var(--text);
  }}
  .filter-bar .preset {{
    padding: 4px 10px; border-radius: 4px; border: 1px solid var(--border);
    background: var(--card-bg); color: var(--text); cursor: pointer;
    font-size: .75rem; font-family: inherit;
  }}
  .filter-bar .preset.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .filter-info {{ font-size: .75rem; color: var(--muted); margin-left: auto; }}

  /* 卡片 */
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
    gap: 10px; margin-bottom: 20px;
  }}
  .kpi-card {{
    background: var(--card-bg); border-radius: var(--radius);
    padding: 14px 16px; box-shadow: var(--shadow);
  }}
  .kpi-card .label {{ font-size: .73rem; color: var(--muted); margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .kpi-card .value {{ font-size: 1.15rem; font-weight: 700; line-height: 1.2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .value.good {{ color: var(--accent); }} .value.warn {{ color: var(--warn); }} .value.bad {{ color: var(--danger); }}
  .kpi-card .unit {{ font-size: .68rem; color: var(--muted); font-weight: 400; }}

  /* 可折叠区块 */
  .collapsible {{
    background: var(--card-bg); border-radius: var(--radius);
    box-shadow: var(--shadow); margin-bottom: 14px; overflow: hidden;
  }}
  .collapsible .sec-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; cursor: pointer; user-select: none;
    border-bottom: 1px solid transparent; transition: background .15s;
  }}
  .collapsible .sec-header:hover {{ background: var(--bg); }}
  .collapsible.open .sec-header {{ border-bottom-color: var(--border); }}
  .collapsible .sec-header h3 {{ font-size: .9rem; font-weight: 600; }}
  .collapsible .sec-header .arrow {{
    font-size: .7rem; color: var(--muted); transition: transform .2s;
  }}
  .collapsible.open .sec-header .arrow {{ transform: rotate(180deg); }}
  .collapsible .sec-body {{ display: none; padding: 16px 18px; }}
  .collapsible.open .sec-body {{ display: block; }}

  /* 图表区 */
  .chart-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
    gap: 14px;
  }}
  .chart-card {{
    background: var(--card-bg); border-radius: var(--radius); padding: 14px;
    box-shadow: var(--shadow);
  }}
  .chart-card h4 {{ font-size: .85rem; margin-bottom: 4px; }}
  .chart-card .desc {{ font-size: .75rem; color: var(--muted); margin-bottom: 10px; }}
  .chart-card img {{ width: 100%; height: auto; border-radius: 6px; display: block; }}
  .chart-empty {{ background: var(--card-bg); border-radius: var(--radius);
    padding: 32px 20px; text-align: center; color: var(--muted); box-shadow: var(--shadow); }}

  /* 对比卡片 */
  .compare-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
  .compare-card {{
    background: var(--card-bg); border-radius: var(--radius); padding: 14px 16px;
    box-shadow: var(--shadow); border-left: 3px solid var(--accent);
  }}
  .compare-card.cron {{ border-left-color: #457b9d; }}
  .compare-card.user {{ border-left-color: var(--warn); }}
  .compare-card h4 {{ font-size: .82rem; margin-bottom: 8px; word-break: break-word; }}
  .compare-card strong {{ color: var(--text); word-break: break-word; }}
  body.dark .compare-card strong {{ color: var(--text); }}

  /* 表格 */
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .8rem; }}
  th,td {{ padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  th {{ background: var(--bg); color: var(--muted); font-weight: 600; font-size: .75rem; position: sticky; top: 0; cursor: pointer; }}
  th:hover {{ color: var(--accent); }}
  tr:hover td {{ background: var(--bg); }}
  td {{ color: var(--text); }}
  body.dark td {{ color: var(--text); }}
  body.dark .kpi-card .value {{ color: var(--text); }}
  body.dark .value.good {{ color: var(--accent); }}
  body.dark .value.warn {{ color: var(--warn); }}
  body.dark .value.bad {{ color: var(--danger); }}
  .badge-sm {{ display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: .7rem; font-weight: 600; }}
  .badge-sm.good {{ background: #d4edda; color: #155724; }}
  .badge-sm.warn {{ background: #fff3cd; color: #856404; }}
  .badge-sm.bad  {{ background: #f8d7da; color: #721c24; }}
  body.dark .badge-sm.good {{ background: #1a3a2a; color: #5dbe7e; }}
  body.dark .badge-sm.bad  {{ background: #3a1a1a; color: #e07070; }}
  body.dark .badge-sm.warn {{ background: #2a2010; color: #d4a843; }}

  /* 分页 & 搜索 */
  .page-controls {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: .78rem; color: var(--muted); margin-top: 10px; }}
  .page-controls button {{
    padding: 4px 10px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--card-bg); color: var(--text); cursor: pointer; font-family: inherit; font-size: .75rem;
  }}
  .page-controls button:disabled {{ opacity: .4; cursor: default; }}
  .page-controls button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .search-box {{
    padding: 5px 10px; border: 1px solid var(--border); border-radius: 6px;
    font-size: .8rem; font-family: inherit; background: var(--card-bg); color: var(--text); width: 200px;
  }}

  /* 热力图 */
  .heatmap-cell {{
    width: 34px; height: 34px; border-radius: 4px; margin: 2px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: .62rem; color: #fff; cursor: default; transition: transform .15s;
  }}
  .heatmap-cell:hover {{ transform: scale(1.15); z-index: 2; }}

  /* 模态弹窗 */
  .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,.5); z-index: 9999; align-items: center; justify-content: center; }}
  .modal-overlay.show {{ display: flex; }}
  .modal {{ background: var(--card-bg); border-radius: var(--radius); padding: 22px 26px; max-width: 560px; width: 92%; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 30px rgba(0,0,0,.2); position: relative; }}
  .modal .close {{ position: absolute; top: 12px; right: 16px; background: none; border: none; font-size: 1.3rem; cursor: pointer; color: var(--muted); }}
  .modal .close:hover {{ color: var(--danger); }}
  .modal .detail-row {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--border); font-size: .8rem; flex-wrap: wrap; gap: 4px; }}
  .modal .detail-row .k {{ color: var(--muted); }} .modal .detail-row .v {{ font-family: monospace; font-size: .76rem; word-break: break-all; text-align: right; }}

  /* 告警 */
  .token-alert {{ display: inline-block; padding: 2px 7px; border-radius: 4px; background: #f8d7da; color: #721c24; font-size: .7rem; font-weight: 600; margin-left: 4px; animation: pulse 2s infinite; }}
  body.dark .token-alert {{ background: #3a1a1a; color: #e07070; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.5}} }}
  .storm-alert {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: .8rem; }}
  body.dark .storm-alert {{ background: #2a2010; border-color: #8a6d14; }}

  .footer {{ text-align: center; color: var(--muted); font-size: .75rem; margin-top: 28px; }}

  /* 移动端：侧边栏缩为顶部汉堡菜单 */
  @media (max-width: 768px) {{
    .sidebar {{ transform: translateX(-100%); }}
    .sidebar.open {{ transform: translateX(0); }}
    .main {{ margin-left: 0; padding: 16px 12px 40px; }}
    .main .mobile-menu-btn {{
      display: inline-block; padding: 6px 12px; margin-bottom: 14px;
      border: 1px solid var(--border); border-radius: 6px;
      background: var(--card-bg); color: var(--text); font-size: .85rem; cursor: pointer;
    }}
    .filter-bar {{ flex-direction: column; align-items: stretch; }}
    .filter-bar .filter-info {{ margin-left: 0; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
    .chart-grid {{ grid-template-columns: 1fr; }}
    .compare-grid {{ grid-template-columns: 1fr; }}
  }}
  @media (min-width: 769px) {{ .main .mobile-menu-btn {{ display: none; }} }}
  body.dark svg text {{ fill: #c0c0d0 !important; }}
  body.dark svg line {{ stroke: #3a3a5a !important; }}
</style>
</head>
<body>

<!-- 侧边栏 -->
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <h2>OpenClaw 监控</h2>
    <div class="sub">{today}</div>
    <div class="sub" style="margin-top:4px;font-size:.65rem;" id="refreshTime"></div>
  </div>
  <div class="sidebar-nav">
    <a class="active" data-page="overview" onclick="switchPage('overview')">
      <span class="ico">&#9679;</span> 仪表盘概览
    </a>
    <a data-page="failures" onclick="switchPage('failures')">
      <span class="ico">&#10007;</span> 失败明细
      <span class="badge-dot" id="failureBadge" style="display:none"></span>
    </a>
    <a data-page="tokens" onclick="switchPage('tokens')">
      <span class="ico">&#9733;</span> Token 分析
    </a>
    <a data-page="errors" onclick="switchPage('errors')">
      <span class="ico">&#9783;</span> 错误趋势
    </a>
    <a data-page="heatmap" onclick="switchPage('heatmap')">
      <span class="ico">&#9637;</span> 时段热力图
    </a>
    <a data-page="interactions" onclick="switchPage('interactions')">
      <span class="ico">&#9993;</span> 交互记录
    </a>
  </div>
  <div class="sidebar-footer">
    <button class="btn" onclick="toggleTheme()" id="themeToggle">暗色模式</button>
    <button class="btn" onclick="exportCSV()">导出 CSV</button>
  </div>
</nav>

<!-- 主内容区 -->
<div class="main" id="mainContent">
  <button class="mobile-menu-btn" onclick="toggleSidebar()">&#9776; 菜单</button>

  <!-- 筛选栏 -->
  <div class="filter-bar">
    <label>起始</label><input type="date" id="dateFrom">
    <label>结束</label><input type="date" id="dateTo">
    <button class="preset" data-days="7" onclick="setPreset(7)">近 7 天</button>
    <button class="preset" data-days="30" onclick="setPreset(30)">近 30 天</button>
    <button class="preset active" data-days="0" onclick="setPreset(0)">全部</button>
    <span class="filter-info" id="filterInfo"></span>
  </div>

  <!-- ====== 页面：仪表盘概览 ====== -->
  <div class="page active" id="page-overview">
    <div id="dailyCompare" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;"></div>

    <div class="kpi-grid" id="kpiGrid"></div>

    <div id="latencyCard" style="background:var(--card-bg);border-radius:10px;padding:14px 18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.04);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-weight:600;font-size:.82rem;">延迟分位分布 (P50 / P95 / P99)</span>
        <span style="font-size:.68rem;color:var(--muted);" id="latencyLabel"></span>
      </div>
      <svg id="latencyChart" viewBox="0 0 600 60" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;"></svg>
    </div>

    <div class="compare-grid" id="triggerCompare" style="margin-bottom:14px;"></div>

    <div class="collapsible open" id="sec-charts">
      <div class="sec-header" onclick="toggleSection('sec-charts')">
        <h3>可视化分析图表（随筛选联动）</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div class="chart-grid">
        <div class="chart-card"><h4>每日任务成功率</h4><div class="desc">反映系统稳定性趋势，波动过大时需关注</div><svg class="svg-chart" id="chartSuccessRate" viewBox="0 0 700 320" preserveAspectRatio="xMidYMid meet"></svg></div>
        <div class="chart-card"><h4>错误类型占比</h4><div class="desc">帮助定位主要故障原因</div><svg class="svg-chart" id="chartErrorDonut" viewBox="0 0 400 320" preserveAspectRatio="xMidYMid meet"></svg></div>
        <div class="chart-card"><h4>工具使用频次 Top 5</h4><div class="desc">反映智能体最常用的能力</div><svg class="svg-chart" id="chartToolBar" viewBox="0 0 500 280" preserveAspectRatio="xMidYMid meet"></svg></div>
        <div class="chart-card"><h4>Token 消耗分布</h4><div class="desc">了解单次任务的资源消耗水平和离群情况</div><svg class="svg-chart" id="chartTokenHist" viewBox="0 0 600 300" preserveAspectRatio="xMidYMid meet"></svg></div>
      </div></div>
    </div>

    <div class="collapsible" id="sec-trigger">
      <div class="sec-header" onclick="toggleSection('sec-trigger')">
        <h3>Trigger 类型统计</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div class="tbl-wrap"><table id="triggerTable"><thead><tr><th>Trigger</th><th>总数</th><th>成功</th><th>失败</th><th>成功率</th><th>平均 Token</th><th>平均耗时(s)</th></tr></thead><tbody></tbody></table></div></div>
    </div>

    <div class="collapsible" id="sec-storms">
      <div class="sec-header" onclick="toggleSection('sec-storms')">
        <h3>重试风暴检测</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div id="retryStormsContent"></div></div>
    </div>

    <div class="collapsible" id="sec-assessment">
      <div class="sec-header" onclick="toggleSection('sec-assessment')">
        <h3>综合评估与建议</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div id="assessment"></div></div>
    </div>
  </div>

  <!-- ====== 页面：失败明细 ====== -->
  <div class="page" id="page-failures">
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px;">
      <input type="text" class="search-box" id="failureSearch" placeholder="搜索 error_type / task_id..." oninput="renderFailures()">
      <span style="font-size:.78rem;color:var(--muted);" id="failureCount"></span>
    </div>
    <div class="tbl-wrap"><table id="failureTable"><thead><tr>
      <th data-sort="timestamp" onclick="sortFailures('timestamp')">时间 &#9650;</th>
      <th data-sort="task_id" onclick="sortFailures('task_id')">Task ID</th>
      <th data-sort="error_type" onclick="sortFailures('error_type')">错误类型</th>
      <th data-sort="duration_sec" onclick="sortFailures('duration_sec')">耗时(s)</th>
      <th data-sort="tokens_used" onclick="sortFailures('tokens_used')">Token</th>
      <th data-sort="trigger" onclick="sortFailures('trigger')">Trigger</th>
    </tr></thead><tbody></tbody></table></div>
    <div class="page-controls" id="failurePagination"></div>
  </div>

  <!-- ====== 页面：Token 分析 ====== -->
  <div class="page" id="page-tokens">
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;" id="tokenSummary"></div>
    <div class="collapsible open" id="sec-token-trend">
      <div class="sec-header" onclick="toggleSection('sec-token-trend')">
        <h3>每日 Token 消耗趋势</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body">
        <svg class="svg-chart" id="tokenTrendChart" viewBox="0 0 800 320" preserveAspectRatio="xMidYMid meet" style="width:100%;"></svg>
      </div>
    </div>
    <div class="collapsible" id="sec-token-top">
      <div class="sec-header" onclick="toggleSection('sec-token-top')">
        <h3>Token 消耗 Top 10 任务</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div class="tbl-wrap"><table id="topTokensTable"><thead><tr><th>时间</th><th>Task ID</th><th>Status</th><th>Token</th><th>耗时(s)</th><th>工具调用</th></tr></thead><tbody></tbody></table></div></div>
    </div>
  </div>

  <!-- ====== 页面：错误趋势 ====== -->
  <div class="page" id="page-errors">
    <div class="collapsible open" id="sec-error-chart">
      <div class="sec-header" onclick="toggleSection('sec-error-chart')">
        <h3>每日错误类型分布（堆叠面积图）</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body">
        <svg class="svg-chart" id="errorTrendChart" viewBox="0 0 800 360" preserveAspectRatio="xMidYMid meet" style="width:100%;"></svg>
      </div>
    </div>
    <div class="collapsible" id="sec-error-summary">
      <div class="sec-header" onclick="toggleSection('sec-error-summary')">
        <h3>各错误类型汇总</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div class="tbl-wrap"><table id="errorSummaryTable"><thead><tr><th>错误类型</th><th>总次数</th><th>占比</th></tr></thead><tbody></tbody></table></div></div>
    </div>
  </div>

  <!-- ====== 页面：时段热力图 ====== -->
  <div class="page" id="page-heatmap">
    <div class="collapsible open" id="sec-heatmap-chart">
      <div class="sec-header" onclick="toggleSection('sec-heatmap-chart')">
        <h3>24 小时 × 日期 — 任务失败率热力图</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div id="heatmapChart"></div></div>
    </div>
    <div class="collapsible" id="sec-hourly-summary">
      <div class="sec-header" onclick="toggleSection('sec-hourly-summary')">
        <h3>各时段汇总统计</h3><span class="arrow">&#9660;</span>
      </div>
      <div class="sec-body"><div class="tbl-wrap"><table id="hourlySummaryTable"><thead><tr><th>时段</th><th>总任务</th><th>成功</th><th>失败</th><th>失败率</th></tr></thead><tbody></tbody></table></div></div>
    </div>
  </div>

  <!-- 交互记录页 -->
  <div class="page" id="page-interactions">
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px;">
      <input type="text" id="interactSearch" placeholder="搜索提问内容..." oninput="renderInteractions()"
             style="flex:1;min-width:200px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:.82rem;">
      <select id="interactStatus" onchange="renderInteractions()"
              style="padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:.82rem;">
        <option value="all">全部状态</option>
        <option value="success">成功</option>
        <option value="failed">失败</option>
      </select>
      <select id="interactTrigger" onchange="renderInteractions()"
              style="padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:.82rem;">
        <option value="all">全部触发</option>
        <option value="cron">Cron</option>
        <option value="user">User</option>
      </select>
      <span style="color:var(--muted);font-size:.78rem;" id="interactInfo"></span>
    </div>
    <div class="tbl-wrap"><table id="interactTable"><thead><tr>
      <th style="width:140px;">时间</th>
      <th style="width:55px;">触发</th>
      <th>提问内容</th>
      <th style="width:65px;">状态</th>
      <th style="width:75px;">耗时</th>
      <th style="width:70px;">Tokens</th>
    </tr></thead><tbody></tbody></table></div>
    <div style="display:flex;justify-content:center;gap:6px;margin-top:12px;" id="interactPages"></div>
  </div>

  <div class="footer">报表由 OpenClaw ETL 管线自动生成 &nbsp;|&nbsp; {today}</div>
</div>

<!-- 会话详情弹窗 -->
<div class="modal-overlay" id="detailModal">
  <div class="modal">
    <button class="close" onclick="closeModal()">&times;</button>
    <h3 id="modalTitle" style="font-size:.95rem;margin-bottom:12px;padding-right:24px;word-break:break-all;">任务详情</h3>
    <div id="modalContent"></div>
  </div>
</div>

<!-- 提问内容弹窗 -->
<div class="modal-overlay" id="promptModal">
  <div class="modal" style="max-width:650px;">
    <button class="close" onclick="closePromptModal()">&times;</button>
    <h3 id="promptModalTitle" style="font-size:.95rem;margin-bottom:12px;">提问内容</h3>
    <div id="promptContent" style="max-height:60vh;overflow-y:auto;white-space:pre-wrap;font-size:.82rem;line-height:1.7;color:var(--text);word-break:break-word;"></div>
  </div>
</div>

<script>
var RAW_DATA = {raw_data_json};
var FAILURE_DETAILS = {failure_details_json};
var TRIGGER_STATS = {trigger_stats_json};
var HOURLY_PATTERN = {hourly_pattern_json};
var ERROR_TREND = {error_trend_json};
var RETRY_STORMS = {retry_storms_json};
var DAILY_SUMMARY = {daily_summary_json};
var CHART_IMAGES = {chart_paths_json};
var GLOBAL_STATS = {stats_json};
var INTERACTIONS = {interactions_json};
var TOKEN_COST_PER_1M = 4;
var TOKEN_ALERT_PER_TASK = 50000;
var TOKEN_ALERT_DAILY = 500000;

var dateFrom = null, dateTo = null, currentPage = 'overview';
var failureSortKey = 'timestamp', failureSortAsc = false, failurePage = 0, PAGE_SIZE = 20;
var darkMode = false;

// ===== 工具函数 =====
function parseDate(s) {{
  if (!s) return null;
  var p = s.split('-');
  if (p.length >= 3) return new Date(+p[0], +p[1] - 1, +p[2]);
  var d = new Date(s); return isNaN(d.getTime()) ? null : d;
}}
function fmtDate(d) {{ return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }}
function inRange(r) {{
  if (!dateFrom && !dateTo) return true;
  var d = parseDate(r.date || r.timestamp);
  if (!d) return true;
  if (dateFrom && d < dateFrom) return false;
  if (dateTo && d > dateTo) return false;
  return true;
}}
function filteredData() {{ return RAW_DATA.filter(inRange); }}
function filteredFailures() {{ return FAILURE_DETAILS.filter(inRange); }}

// ===== 侧边栏 & 页面切换 =====
function switchPage(name) {{
  currentPage = name;
  document.querySelectorAll('.sidebar-nav a').forEach(function(a) {{ a.classList.toggle('active', a.dataset.page === name); }});
  document.querySelectorAll('.page').forEach(function(p) {{ p.classList.toggle('active', p.id === 'page-' + name); }});
  renderCurrentPage();
  // 移动端自动关闭侧边栏
  if (window.innerWidth <= 768) document.getElementById('sidebar').classList.remove('open');
}}
function toggleSidebar() {{ document.getElementById('sidebar').classList.toggle('open'); }}
// 点击主内容区关闭侧边栏
document.addEventListener('click', function(e) {{
  var sb = document.getElementById('sidebar');
  var mc = document.getElementById('mainContent');
  if (sb.classList.contains('open') && !sb.contains(e.target) && mc.contains(e.target)) {{
    sb.classList.remove('open');
  }}
}});
function toggleSection(id) {{ document.getElementById(id).classList.toggle('open'); }}

// ===== 筛选 =====
function applyFilter() {{
  var fe = document.getElementById('dateFrom'), te = document.getElementById('dateTo');
  dateFrom = fe.value ? new Date(fe.value + 'T00:00:00') : null;
  dateTo = te.value ? new Date(te.value + 'T23:59:59') : null;
  document.querySelectorAll('.preset').forEach(function(b) {{ b.classList.remove('active'); }});
  var fdata = filteredData();
  document.getElementById('filterInfo').textContent = '筛选: ' + fdata.length + ' / ' + RAW_DATA.length + ' 条';
  // 显示/隐藏失败标记
  var failedCount = filteredFailures().length;
  var badge = document.getElementById('failureBadge');
  badge.style.display = failedCount > 0 ? 'inline-block' : 'none';
  renderCurrentPage();
}}
function setPreset(days) {{
  var fe = document.getElementById('dateFrom'), te = document.getElementById('dateTo');
  if (days === 0) {{ fe.value = ''; te.value = ''; }}
  else {{
    var end = new Date(), start = new Date();
    start.setDate(start.getDate() - days + 1);
    te.value = fmtDate(end); fe.value = fmtDate(start);
  }}
  document.querySelectorAll('.preset').forEach(function(b) {{ b.classList.toggle('active', parseInt(b.dataset.days) === days); }});
  applyFilter();
}}

function renderCurrentPage() {{
  switch (currentPage) {{
    case 'overview': renderOverview(); break;
    case 'failures': renderFailures(); break;
    case 'tokens': renderTokens(); break;
    case 'errors': renderErrorTrend(); break;
    case 'heatmap': renderHeatmap(); break;
    case 'interactions': renderInteractions(); break;
  }}
}}

// ===== 概览页 =====
function renderOverview() {{
  var fdata = filteredData();
  var total = fdata.length, success = fdata.filter(function(r){{return r.status==='success'}}).length;
  var failed = total - success, rate = total > 0 ? Math.round(success/total*10000)/100 : 0;
  var totalTokens = fdata.reduce(function(s,r){{return s+(r.tokens_used||0)}},0);
  var avgTokens = total > 0 ? Math.round(totalTokens/total) : 0;
  var totalDur = fdata.reduce(function(s,r){{return s+(r.duration_ms||0)}},0);
  var avgDur = total > 0 ? Math.round(totalDur/total) : 0;

  // ===== 日环比摘要条 =====
  (function() {{
    var byDate = {{}};
    fdata.forEach(function(r) {{
      var d = r.date || (r.timestamp || '').slice(0, 10);
      if (!byDate[d]) byDate[d] = {{total:0, success:0, tokens:0, dur:0}};
      byDate[d].total++;
      if (r.status === 'success') byDate[d].success++;
      byDate[d].tokens += (r.tokens_used || 0);
      byDate[d].dur += (r.duration_ms || 0);
    }});
    var dates = Object.keys(byDate).sort();
    if (dates.length >= 2) {{
      var today = byDate[dates[dates.length - 1]];
      var yesterday = byDate[dates[dates.length - 2]];
      var td = dates[dates.length - 1].slice(5);
      var yd = dates[dates.length - 2].slice(5);

      function delta(cur, prev) {{
        if (!prev || prev === 0) return {{pct: 0, dir: 'flat'}};
        return {{pct: Math.round((cur - prev) / prev * 1000) / 10, dir: cur > prev ? 'up' : 'down'}};
      }}

      var items = [
        {{label: '任务量', cur: today.total, prev: yesterday.total, fmt: function(v){{return v+'条'}}, better: 'neutral'}},
        {{label: '成功率', cur: today.total>0?Math.round(today.success/today.total*1000)/10:0,
         prev: yesterday.total>0?Math.round(yesterday.success/yesterday.total*1000)/10:0, fmt: function(v){{return v+'%'}}, better: 'up'}},
        {{label: 'Token', cur: today.tokens, prev: yesterday.tokens, fmt: function(v){{return v>1000?Math.round(v/1000)+'K':v}}, better: 'neutral'}},
        {{label: '平均耗时', cur: today.total>0?Math.round(today.dur/today.total):0,
         prev: yesterday.total>0?Math.round(yesterday.dur/yesterday.total):0, fmt: function(v){{return v>=1000?Math.round(v/1000)+'s':v+'ms'}}, better: 'down'}},
      ];

      var ch = '';
      items.forEach(function(m) {{
        var d = delta(m.cur, m.prev);
        var absPct = Math.abs(d.pct);
        var arrow = d.dir === 'up' ? '&#9650;' : (d.dir === 'down' ? '&#9660;' : '&#9644;');
        var tc;
        if (absPct <= 5 || m.better === 'neutral') tc = 'var(--muted)';
        else if (m.better === 'up') tc = d.dir === 'up' ? '#2a9d8f' : '#e76f51';
        else if (m.better === 'down') tc = d.dir === 'down' ? '#2a9d8f' : '#e76f51';
        ch += '<div style="background:var(--card-bg);border-radius:8px;padding:8px 14px;box-shadow:0 1px 2px rgba(0,0,0,.04);flex:1;min-width:120px;">';
        ch += '<div style="font-size:.68rem;color:var(--muted);margin-bottom:2px;">' + m.label + ' (' + yd + '→' + td + ')</div>';
        ch += '<div style="font-size:1rem;font-weight:700;">' + m.fmt(m.cur) + ' <span style="font-size:.7rem;color:' + tc + ';">' + arrow + ' ' + absPct + '%</span></div>';
        ch += '</div>';
      }});
      document.getElementById('dailyCompare').innerHTML = ch;
      document.getElementById('dailyCompare').style.display = 'flex';
    }} else {{
      document.getElementById('dailyCompare').style.display = 'none';
    }}
  }})();

  var errCounts = {{}};
  fdata.forEach(function(r){{ if(r.status==='failed'&&r.error_type){{ var k=r.error_type; errCounts[k]=(errCounts[k]||0)+1; }} }});
  var topErr='N/A', topMax=0;
  Object.keys(errCounts).forEach(function(k){{ if(errCounts[k]>topMax){{topErr=k;topMax=errCounts[k];}} }});

  var toolCounts = {{}};
  fdata.forEach(function(r){{ if(r.tool_name){{ var k=r.tool_name; toolCounts[k]=(toolCounts[k]||0)+1; }} }});
  var topTool='N/A', topMax2=0;
  Object.keys(toolCounts).forEach(function(k){{ if(toolCounts[k]>topMax2){{topTool=k;topMax2=toolCounts[k];}} }});

  // KPI 对比箭头: 比较筛选期与前一个等长周期
  var cmpData = DAILY_SUMMARY || [];
  var cmpRate = null, cmpTokens = null, cmpTotal = null, cmpDur = null;
  if (dateFrom && dateTo && cmpData.length > 0) {{
    var rangeDays = Math.round((dateTo - dateFrom) / 86400000) + 1;
    var prevEnd = new Date(dateFrom.getTime() - 86400000);
    var prevStart = new Date(prevEnd.getTime() - (rangeDays - 1) * 86400000);
    var prevData = cmpData.filter(function(d) {{
      var p = parseDate(d.date); return p && p >= prevStart && p <= prevEnd;
    }});
    if (prevData.length > 0) {{
      var pTotal = prevData.reduce(function(s,d){{return s+d.total;}},0);
      var pSuccess = prevData.reduce(function(s,d){{return s+d.success;}},0);
      var pTokens = prevData.reduce(function(s,d){{return s+d.tokens;}},0);
      var pDur = prevData.reduce(function(s,d){{return s+(d.avg_duration_sec||0)*1000*d.total;}},0);
      cmpRate = Math.round(pSuccess/pTotal*10000)/100;
      cmpTokens = pTokens;
      cmpTotal = pTotal;
      cmpDur = pTotal > 0 ? Math.round(pDur/pTotal) : null;
    }}
  }} else if (cmpData.length >= 2) {{
    var last = cmpData[cmpData.length - 1];
    var prev = cmpData[cmpData.length - 2];
    cmpRate = prev.success_rate;
    cmpTokens = prev.tokens;
    cmpTotal = prev.total;
    cmpDur = prev.avg_duration_sec ? Math.round(prev.avg_duration_sec * 1000) : null;
  }}
  function arrow2(cur, prev, unit, invert) {{
    if (prev == null || prev === 0) return '';
    var diff = cur - prev;
    var pct = Math.round(Math.abs(diff) / prev * 1000) / 10;
    if (Math.abs(pct) < 0.5) return ' <span style="font-size:.65rem;color:var(--muted);">&#9644;</span>';
    var up = invert ? (diff < 0) : (diff > 0);
    var color = up ? 'var(--accent)' : 'var(--danger)';
    var arrow = up ? '&#9650;' : '&#9660;';
    return ' <span style="font-size:.65rem;color:'+color+';">'+arrow+' '+pct+'%</span>';
  }}

  var tone = rate>=95?'good':(rate>=85?'warn':'bad');
  var cards = [
    ['任务总数',String(total),'', 'neutral', cmpTotal ? arrow2(total, cmpTotal, '', false) : ''],
    ['成功率',String(rate),'%', tone, cmpRate ? arrow2(rate, cmpRate, '', false) : ''],
    ['Token 总消耗',totalTokens.toLocaleString(),'', 'neutral', cmpTokens ? arrow2(totalTokens, cmpTokens, '', false) : ''],
    ['平均 Token',String(avgTokens),'', 'neutral', ''],
    ['总耗时',Math.round(totalDur/1000).toLocaleString(),'秒', 'neutral', cmpDur ? arrow2(avgDur, cmpDur, 'ms', true) : ''],
    ['平均耗时',String(avgDur),'ms', 'neutral', cmpDur ? arrow2(avgDur, cmpDur, 'ms', true) : ''],
    ['最高频错误',topErr,'', 'neutral', ''],
    ['最高频工具',topTool,'', 'neutral', ''],
  ];

  var h='';
  cards.forEach(function(c){{
    var cls = c[3]!=='neutral'?'value '+c[3]:'value';
    h += '<div class="kpi-card"><div class="label">'+c[0]+'</div><div class="'+cls+'">'+c[1]+'<span class="unit">'+c[2]+'</span>'+(c[4]||'')+'</div></div>';
  }});
  document.getElementById('kpiGrid').innerHTML = h;

  // Token 告警
  var maxSingle = fdata.length>0?Math.max.apply(null,fdata.map(function(r){{return r.tokens_used||0}})):0;
  if (maxSingle>TOKEN_ALERT_PER_TASK||totalTokens>TOKEN_ALERT_DAILY) {{
    var ah='';
    if(maxSingle>TOKEN_ALERT_PER_TASK) ah+='<span class="token-alert">单任务超阈值 '+maxSingle.toLocaleString()+' > '+TOKEN_ALERT_PER_TASK.toLocaleString()+'</span> ';
    if(totalTokens>TOKEN_ALERT_DAILY) ah+='<span class="token-alert">日总超阈值 '+totalTokens.toLocaleString()+' > '+TOKEN_ALERT_DAILY.toLocaleString()+'</span>';
    document.getElementById('kpiGrid').insertAdjacentHTML('beforeend','<div class="kpi-card" style="grid-column:1/-1"><div class="label">Token 成本告警</div><div style="font-size:.8rem;">'+ah+'</div></div>');
  }}

  // Cron vs User 对比
  var cron=fdata.filter(function(r){{return r.trigger==='cron'}}), user=fdata.filter(function(r){{return r.trigger==='user'}});
  var other=fdata.filter(function(r){{return r.trigger!=='cron'&&r.trigger!=='user'}});
  function cc(label,cls,arr){{
    if(arr.length===0)return'';
    var s=arr.filter(function(r){{return r.status==='success'}}).length;
    var rt=Math.round(s/arr.length*1000)/10;
    var tk=arr.reduce(function(s,r){{return s+(r.tokens_used||0)}},0);
    var ad=arr.length>0?Math.round(arr.reduce(function(s,r){{return s+(r.duration_ms||0)}},0)/arr.length):0;
    var t2=rt>=95?'good':(rt>=85?'warn':'bad');
    return'<div class="compare-card '+cls+'"><h4>'+label+' ('+arr.length+' 条)</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.78rem;"><div><span class="value '+t2+'">'+rt+'%</span><br><span style="color:var(--muted)">成功率</span></div><div><strong>'+Math.round(ad)+'</strong>ms<br><span style="color:var(--muted)">平均耗时</span></div><div><strong>'+tk.toLocaleString()+'</strong><br><span style="color:var(--muted)">Token</span></div><div><strong>'+s+'/'+arr.length+'</strong><br><span style="color:var(--muted)">成功/总数</span></div></div></div>';
  }}
  document.getElementById('triggerCompare').innerHTML=cc('Cron 定时','cron',cron)+cc('User 手动','user',user)+cc('其他','',other);

  // 延迟分位图
  var durs = fdata.map(function(r){{return r.duration_ms||0}}).filter(function(v){{return v>0}}).sort(function(a,b){{return a-b}});
  if (durs.length > 0) {{
    var p50 = durs[Math.floor(durs.length * 0.50)];
    var p95 = durs[Math.floor(durs.length * 0.95)];
    var p99 = durs[Math.floor(durs.length * 0.99)];
    var pmax = Math.max(p99, 1);
    var bars = [
      {{v: p50, pct: '50', color: '#2a9d8f', label: 'P50'}},
      {{v: p95, pct: '95', color: '#f4a261', label: 'P95'}},
      {{v: p99, pct: '99', color: '#e76f51', label: 'P99'}},
    ];
    var svg = document.getElementById('latencyChart');
    var h = '';
    bars.forEach(function(b, i) {{
      var w = Math.max(b.v / pmax * 580, 2);
      var y = 8 + i * 18;
      var fmtV = b.v >= 60000 ? Math.round(b.v/60000)+'分' : Math.round(b.v/1000)+'秒';
      h += '<text x="0" y="' + (y + 9) + '" fill="var(--text)" font-size="10">' + b.label + '</text>';
      h += '<rect x="36" y="' + y + '" width="' + w + '" height="12" rx="2" fill="' + b.color + '" opacity="0.75"/>';
      h += '<text x="' + (w + 40) + '" y="' + (y + 10) + '" fill="' + b.color + '" font-size="9" font-weight="600">' + fmtV + '</text>';
    }});
    svg.innerHTML = h;
    document.getElementById('latencyLabel').textContent = durs.length + ' 个任务 | 最快 ' + (durs[0]>=1000?Math.round(durs[0]/1000)+'s':durs[0]+'ms') + ' | 最慢 ' + (p99>=60000?Math.round(p99/60000)+'分':Math.round(p99/1000)+'秒');
    document.getElementById('latencyCard').style.display = '';
  }} else {{
    document.getElementById('latencyCard').style.display = 'none';
  }}

  // Trigger 表
  var thtml='';
  TRIGGER_STATS.forEach(function(t){{
    var r2=t.success_rate, t2=r2>=95?'good':(r2>=85?'warn':'bad');
    thtml+='<tr><td><strong>'+t.trigger+'</strong></td><td>'+t.total+'</td><td>'+t.success+'</td><td>'+t.failed+'</td><td class="value '+t2+'">'+r2+'%</td><td>'+t.avg_tokens.toLocaleString()+'</td><td>'+t.avg_duration_sec+'</td></tr>';
  }});
  document.querySelector('#triggerTable tbody').innerHTML=thtml||'<tr><td colspan="7" style="color:var(--muted)">无数据</td></tr>';

  // 重试风暴
  var fstorms=RETRY_STORMS.filter(function(s){{
    if(!dateFrom&&!dateTo)return true;
    var sd=parseDate(s.start_time); if(!sd)return true;
    if(dateFrom&&sd<dateFrom)return false;
    if(dateTo&&sd>dateTo)return false;
    return true;
  }});
  var sc=document.getElementById('sec-storms');
  if(fstorms.length>0){{
    sc.style.display='block';
    var sh='';
    fstorms.forEach(function(s){{
      sh+='<div class="storm-alert"><div style="font-weight:600;margin-bottom:2px;">'+s.trigger+' — '+s.count+' 次连续失败 (窗口: '+s.window_minutes+' 分钟)</div><div>时间: '+s.start_time+' ~ '+s.end_time+'</div><div>错误: '+(s.error_types||[]).join(', ')+' | Token: '+s.total_tokens.toLocaleString()+'</div></div>';
    }});
    document.getElementById('retryStormsContent').innerHTML=sh;
  }} else {{ sc.style.display='none'; }}

  // 评估
  var level,sug;
  if(rate>=95){{level='良好';sug='系统运行稳定。';}}
  else if(rate>=85){{level='一般';sug='建议关注失败任务，优先排查 <strong>'+topErr+'</strong>。';}}
  else{{level='需要关注';sug='成功率偏低('+rate+'%)，建议排查 <strong>'+topErr+'</strong>。';}}
  var dailyTokens=total>0?Math.round(totalTokens/total):0;
  document.getElementById('assessment').innerHTML='<p style="margin-bottom:6px"><strong>健康评级: '+level+'</strong></p><p>'+sug+'</p><ul style="margin-top:8px;color:var(--muted);font-size:.82rem;"><li>Token 消耗: 日均 '+dailyTokens.toLocaleString()+'，预估成本 $'+(totalTokens/1000000*4).toFixed(2)+'</li><li>耗时: 平均 '+avgDur+'ms，总耗时 '+Math.round(totalDur/1000).toLocaleString()+' 秒</li><li>分布: '+success+' 成功 / '+failed+' 失败 (共 '+total+' 条)</li></ul>';
  drawCharts();
}}

// ===== 失败明细 =====
function sortFailures(key) {{
  if(failureSortKey===key){{failureSortAsc=!failureSortAsc;}}else{{failureSortKey=key;failureSortAsc=true;}}
  failurePage=0; renderFailures();
}}
function renderFailures() {{
  var data=filteredFailures();
  var search=(document.getElementById('failureSearch').value||'').toLowerCase();
  if(search){{data=data.filter(function(r){{return(r.error_type||'').toLowerCase().indexOf(search)>=0||(r.task_id||'').toLowerCase().indexOf(search)>=0||(r.trigger||'').toLowerCase().indexOf(search)>=0;}});}}
  data.sort(function(a,b){{var va=a[failureSortKey],vb=b[failureSortKey];if(va==null)va='';if(vb==null)vb='';if(typeof va==='number')return failureSortAsc?va-vb:vb-va;va=String(va);vb=String(vb);return failureSortAsc?va.localeCompare(vb):vb.localeCompare(va);}});
  document.getElementById('failureCount').textContent='共 '+data.length+' 条失败记录';
  var tp=Math.ceil(data.length/PAGE_SIZE);
  if(failurePage>=tp)failurePage=Math.max(0,tp-1);
  var start=failurePage*PAGE_SIZE, page=data.slice(start,start+PAGE_SIZE);
  var h='';
  page.forEach(function(r,i){{h+='<tr style="cursor:pointer;" onclick="openModal('+(start+i)+')" title="点击查看详情"><td>'+(r.timestamp||'')+'</td><td style="font-family:monospace;font-size:.75rem;">'+(r.task_id_short||r.task_id||'')+'</td><td><span class="badge-sm bad">'+(r.error_type||'unknown')+'</span></td><td>'+(r.duration_sec!=null?r.duration_sec:'')+'</td><td>'+(r.tokens_used!=null?r.tokens_used.toLocaleString():'')+'</td><td>'+(r.trigger||'')+'</td></tr>';}});
  document.querySelector('#failureTable tbody').innerHTML=h||'<tr><td colspan="6" style="color:var(--muted)">无匹配记录</td></tr>';
  var ph='<span>第 '+(data.length>0?failurePage+1:0)+'/'+Math.max(1,tp)+' 页</span>';
  ph+='<button onclick="failurePage=0;renderFailures()" '+(failurePage===0?'disabled':'')+'>首页</button>';
  ph+='<button onclick="failurePage=Math.max(0,failurePage-1);renderFailures()" '+(failurePage===0?'disabled':'')+'>上一页</button>';
  for(var i=Math.max(0,failurePage-2);i<Math.min(tp,failurePage+3);i++){{ph+='<button class="'+(i===failurePage?'active':'')+'" onclick="failurePage='+i+';renderFailures()">'+(i+1)+'</button>';}}
  ph+='<button onclick="failurePage=Math.min(tp-1,failurePage+1);renderFailures()" '+(failurePage>=tp-1?'disabled':'')+'>下一页</button>';
  ph+='<button onclick="failurePage='+Math.max(0,tp-1)+';renderFailures()" '+(failurePage>=tp-1?'disabled':'')+'>末页</button>';
  document.getElementById('failurePagination').innerHTML=ph;
}}

// ===== 弹窗 =====
function openModal(idx) {{
  var allF=filteredFailures();
  var search=(document.getElementById('failureSearch').value||'').toLowerCase();
  if(search){{allF=allF.filter(function(r){{return(r.error_type||'').toLowerCase().indexOf(search)>=0||(r.task_id||'').toLowerCase().indexOf(search)>=0;}});}}
  var r=allF[idx]; if(!r)return;
  document.getElementById('modalTitle').textContent='任务详情 — '+(r.task_id_short||r.task_id);
  document.getElementById('modalContent').innerHTML=
    '<div class="detail-row"><span class="k">Task ID</span><span class="v">'+(r.task_id||'')+'</span></div>'+
    '<div class="detail-row"><span class="k">时间</span><span class="v">'+(r.timestamp||'')+'</span></div>'+
    '<div class="detail-row"><span class="k">错误类型</span><span class="v" style="color:var(--danger)">'+(r.error_type||'unknown')+'</span></div>'+
    '<div class="detail-row"><span class="k">耗时(s)</span><span class="v">'+(r.duration_sec!=null?r.duration_sec:'N/A')+'</span></div>'+
    '<div class="detail-row"><span class="k">Token</span><span class="v">'+(r.tokens_used!=null?r.tokens_used.toLocaleString():'N/A')+'</span></div>'+
    '<div class="detail-row"><span class="k">工具调用</span><span class="v">'+(r.tool_calls_count!=null?r.tool_calls_count:'N/A')+'</span></div>'+
    '<div class="detail-row"><span class="k">主要工具</span><span class="v">'+(r.tool_name||'N/A')+'</span></div>'+
    '<div class="detail-row"><span class="k">Trigger</span><span class="v">'+(r.trigger||'unknown')+'</span></div>';
  document.getElementById('detailModal').classList.add('show');
}}
function closeModal() {{ document.getElementById('detailModal').classList.remove('show'); }}

// ===== Token 分析 =====
function renderTokens() {{
  var fdata=filteredData();
  var totalTokens=fdata.reduce(function(s,r){{return s+(r.tokens_used||0)}},0);
  var avgT=fdata.length>0?Math.round(totalTokens/fdata.length):0;
  var maxT=fdata.length>0?Math.max.apply(null,fdata.map(function(r){{return r.tokens_used||0}})):0;
  var sorted=fdata.map(function(r){{return r.tokens_used||0}}).sort(function(a,b){{return a-b}});
  var med=0; if(sorted.length>0){{var mid=Math.floor(sorted.length/2);med=sorted.length%2===0?Math.round((sorted[mid-1]+sorted[mid])/2):sorted[mid];}}
  document.getElementById('tokenSummary').innerHTML=
    '<div style="background:var(--card-bg);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);min-width:130px;"><div style="font-size:.73rem;color:var(--muted);">总消耗</div><div style="font-size:1.05rem;font-weight:700;">'+totalTokens.toLocaleString()+'</div></div>'+
    '<div style="background:var(--card-bg);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);min-width:130px;"><div style="font-size:.73rem;color:var(--muted);">均值</div><div style="font-size:1.05rem;font-weight:700;">'+avgT.toLocaleString()+'</div></div>'+
    '<div style="background:var(--card-bg);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);min-width:130px;"><div style="font-size:.73rem;color:var(--muted);">中位数</div><div style="font-size:1.05rem;font-weight:700;">'+med.toLocaleString()+'</div></div>'+
    '<div style="background:var(--card-bg);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);min-width:130px;"><div style="font-size:.73rem;color:var(--muted);">峰值</div><div style="font-size:1.05rem;font-weight:700;">'+maxT.toLocaleString()+'</div></div>'+
    '<div style="background:var(--card-bg);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow);min-width:130px;"><div style="font-size:.73rem;color:var(--muted);">预估成本</div><div style="font-size:1.05rem;font-weight:700;">$'+(totalTokens/1000000*4).toFixed(2)+'</div></div>';

  var dailyMap={{}};
  fdata.forEach(function(r){{var d=r.date||(r.timestamp||'').slice(0,10);if(!d)return;if(!dailyMap[d])dailyMap[d]={{tokens:0,count:0}};dailyMap[d].tokens+=r.tokens_used||0;dailyMap[d].count+=1;}});
  drawTokenTrend(Object.keys(dailyMap).sort(), dailyMap);

  var top10=fdata.slice().sort(function(a,b){{return(b.tokens_used||0)-(a.tokens_used||0)}}).slice(0,10);
  var th='';
  top10.forEach(function(r){{var cls=r.status==='success'?'badge-sm good':'badge-sm bad';th+='<tr><td>'+(r.timestamp||'')+'</td><td style="font-family:monospace;font-size:.75rem;">'+(r.task_id||'')+'</td><td><span class="'+cls+'">'+r.status+'</span></td><td>'+(r.tokens_used!=null?r.tokens_used.toLocaleString():'')+'</td><td>'+(r.duration_ms!=null?Math.round(r.duration_ms/1000):'')+'</td><td>'+(r.tool_calls_count||0)+'</td></tr>';}});
  document.querySelector('#topTokensTable tbody').innerHTML=th||'<tr><td colspan="6" style="color:var(--muted)">无数据</td></tr>';
}}
function drawTokenTrend(days,dm){{
  var svg=document.getElementById('tokenTrendChart'); if(days.length===0){{svg.innerHTML='<text x="400" y="160" text-anchor="middle" fill="var(--muted)" font-size="14">无数据</text>';return;}}
  var W=800,H=320,padL=60,padR=30,padT=20,padB=60, pw=W-padL-padR, ph=H-padT-padB;
  var vals=days.map(function(d){{return dm[d].tokens;}}), maxV=Math.max.apply(null,vals)||1;
  var barW=Math.max(4,Math.min(30,pw/days.length-2));
  var h='';
  for(var i=0;i<=4;i++){{var y=padT+(ph*i/4),v=Math.round(maxV*(1-i/4));h+='<line x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'" stroke="var(--border)" stroke-width="1"/><text x="'+(padL-8)+'" y="'+(y+4)+'" text-anchor="end" fill="var(--muted)" font-size="10">'+v.toLocaleString()+'</text>';}}
  days.forEach(function(d,idx){{var v=dm[d].tokens,bh=Math.max(1,(v/maxV)*ph),x=padL+idx*(pw/days.length)+(pw/days.length-barW)/2,y=padT+ph-bh,hue=170-(v/maxV)*30;h+='<rect x="'+x+'" y="'+y+'" width="'+barW+'" height="'+bh+'" rx="2" fill="hsl('+hue+',60%,50%)" opacity="0.85"><title>'+d+': '+v.toLocaleString()+' tokens</title></rect>';if(days.length<=30||idx%Math.ceil(days.length/20)===0)h+='<text x="'+(x+barW/2)+'" y="'+(H-padB+30)+'" text-anchor="middle" fill="var(--muted)" font-size="9" transform="rotate(-30,'+(x+barW/2)+','+(H-padB+30)+')">'+d.slice(5)+'</text>';}});
  svg.innerHTML=h;
}}

// ===== 错误趋势 =====
function renderErrorTrend() {{
  var trend=ERROR_TREND;
  if(dateFrom||dateTo){{trend=trend.filter(function(d){{var p=parseDate(d.date);if(!p)return true;if(dateFrom&&p<dateFrom)return false;if(dateTo&&p>dateTo)return false;return true;}});}}
  var eTypes=[]; if(trend.length>0){{var first=trend[0];Object.keys(first).forEach(function(k){{if(k!=='date'&&k!=='success')eTypes.push(k);}});}}
  var sum={{}}; eTypes.forEach(function(et){{sum[et]=0;}});
  trend.forEach(function(d){{eTypes.forEach(function(et){{sum[et]+=(d[et]||0);}});}});
  var totalE=0; Object.values(sum).forEach(function(v){{totalE+=v;}});
  var sArr=eTypes.map(function(et){{return{{name:et,count:sum[et]}};}}).sort(function(a,b){{return b.count-a.count;}});
  var sh=''; sArr.forEach(function(s){{var pct=totalE>0?Math.round(s.count/totalE*1000)/10:0;sh+='<tr><td><strong>'+s.name+'</strong></td><td>'+s.count+'</td><td>'+pct+'%</td></tr>';}});
  document.querySelector('#errorSummaryTable tbody').innerHTML=sh||'<tr><td colspan="3" style="color:var(--muted)">无数据</td></tr>';
  var svg=document.getElementById('errorTrendChart');
  if(trend.length===0||eTypes.length===0){{svg.innerHTML='<text x="400" y="180" text-anchor="middle" fill="var(--muted)" font-size="14">无错误数据</text>';return;}}
  var W=800,H=360,padL=60,padR=30,padT=20,padB=50, pw=W-padL-padR, ph=H-padT-padB;
  var colors=['#e76f51','#f4a261','#2a9d8f','#457b9d','#a8dadc','#e63946','#6d597a','#b56576','#eaac8b','#355070'];
  var dates=trend.map(function(d){{return d.date;}});
  var stacks=[], maxStack=0;
  eTypes.forEach(function(et,ei){{
    var top=new Array(trend.length).fill(0), bot=new Array(trend.length).fill(0);
    for(var i=0;i<=ei;i++){{var et2=eTypes[i];for(var j=0;j<trend.length;j++)top[j]+=(trend[j][et2]||0);}}
    for(var i2=0;i2<ei;i2++){{var et3=eTypes[i2];for(var j2=0;j2<trend.length;j2++)bot[j2]+=(trend[j2][et3]||0);}}
    stacks.push({{name:et,top:top,bot:bot,color:colors[ei%colors.length]}});
    maxStack=Math.max(maxStack,Math.max.apply(null,top));
  }});
  if(maxStack===0)maxStack=1;
  var h='';
  for(var i=0;i<=4;i++){{var y=padT+(ph*i/4),v=Math.round(maxStack*(1-i/4));h+='<line x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'" stroke="var(--border)" stroke-width="1"/><text x="'+(padL-8)+'" y="'+(y+4)+'" text-anchor="end" fill="var(--muted)" font-size="10">'+v+'</text>';}}
  var stepX=pw/Math.max(1,dates.length-1);
  for(var si=stacks.length-1;si>=0;si--){{
    var st=stacks[si], ptsTop='', ptsBot='';
    for(var j=0;j<dates.length;j++){{var cx=padL+j*stepX,cyTop=padT+ph-(st.top[j]/maxStack)*ph,cyBot=padT+ph-(st.bot[j]/maxStack)*ph;ptsTop+=cx+','+cyTop+' ';ptsBot=cx+','+cyBot+' '+ptsBot;}}
    h+='<polygon points="'+ptsTop+ptsBot+'" fill="'+st.color+'" opacity="0.7" stroke="'+st.color+'" stroke-width="1"><title>'+st.name+'</title></polygon>';
  }}
  var ls=Math.max(1,Math.floor(dates.length/20));
  for(var j=0;j<dates.length;j++){{if(j%ls===0){{var cx=padL+j*stepX;h+='<text x="'+cx+'" y="'+(H-padB+28)+'" text-anchor="middle" fill="var(--muted)" font-size="9" transform="rotate(-30,'+cx+','+(H-padB+28)+')">'+dates[j].slice(5)+'</text>';}}}}
  for(var si=0;si<stacks.length;si++){{var ly=padT+si*18;h+='<rect x="'+(W-padR-150)+'" y="'+ly+'" width="12" height="12" rx="2" fill="'+stacks[si].color+'" opacity="0.7"/><text x="'+(W-padR-134)+'" y="'+(ly+10)+'" fill="var(--muted)" font-size="10">'+stacks[si].name+'</text>';}}
  svg.innerHTML=h;
}}

// ===== 热力图 =====
function renderHeatmap() {{
  var fdata=filteredData();
  var map={{}}, allDates=new Set();
  fdata.forEach(function(r){{var d=r.date||(r.timestamp||'').slice(0,10),h=r.hour;if(!d||h==null)return;allDates.add(d);var k=d+'|'+h;if(!map[k])map[k]={{total:0,failed:0}};map[k].total+=1;if(r.status==='failed')map[k].failed+=1;}});
  var dates=Array.from(allDates).sort(); if(dates.length>60)dates=dates.slice(-60);
  if(dates.length===0){{document.getElementById('heatmapChart').innerHTML='<p style="color:var(--muted);text-align:center;padding:20px;">无数据</p>';renderHourlySummary();return;}}
  var h='<div style="overflow-x:auto;"><div style="display:flex;gap:0;font-size:.68rem;color:var(--muted);margin-bottom:4px;min-width:'+(dates.length*40)+'px;"><div style="width:50px;flex-shrink:0;"></div>';
  dates.forEach(function(d){{h+='<div style="width:34px;text-align:center;margin:0 2px;overflow:hidden;">'+d.slice(5)+'</div>';}});h+='</div>';
  for(var hr=0;hr<24;hr++){{
    h+='<div style="display:flex;gap:0;align-items:center;margin-bottom:2px;"><div style="width:50px;flex-shrink:0;font-size:.68rem;color:var(--muted);text-align:right;padding-right:6px;">'+String(hr).padStart(2,'0')+':00</div>';
    dates.forEach(function(d){{var key=d+'|'+hr,cell=map[key];
      if(!cell||cell.total===0)h+='<div class="heatmap-cell" style="background:#eee;color:#999;" title="'+d+' '+hr+':00 — 无任务">-</div>';
      else{{var rate=cell.failed/cell.total,hue=rate>0.5?0:(rate>0.2?25:120),sat=Math.round(rate*100),light=85-Math.round(rate*45);h+='<div class="heatmap-cell" style="background:hsl('+hue+','+sat+'%,'+light+'%);" title="'+d+' '+hr+':00 — 失败率 '+Math.round(rate*100)+'% ('+cell.failed+'/'+cell.total+')">'+Math.round(rate*100)+'</div>';}}
    }});h+='</div>';
  }}
  h+='</div><div style="display:flex;gap:6px;align-items:center;margin-top:8px;font-size:.7rem;color:var(--muted);"><span>低</span><span style="width:14px;height:14px;border-radius:3px;background:hsl(120,60%,80%);"></span><span style="width:14px;height:14px;border-radius:3px;background:hsl(25,50%,65%);"></span><span style="width:14px;height:14px;border-radius:3px;background:hsl(0,80%,50%);"></span><span>高</span></div>';
  document.getElementById('heatmapChart').innerHTML=h; renderHourlySummary();
}}
function renderHourlySummary() {{
  var fdata=filteredData(), hourly=[];
  for(var h=0;h<24;h++){{var hd=fdata.filter(function(r){{return r.hour===h;}}),t=hd.length,f=hd.filter(function(r){{return r.status==='failed';}}).length;hourly.push({{hour:h,total:t,failed:f,success:t-f,rate:t>0?Math.round(f/t*1000)/10:0}});}}
  var maxF=Math.max.apply(null,hourly.map(function(h){{return h.rate;}}))||1, hh='';
  hourly.forEach(function(hr){{var hue=120-(hr.rate/maxF)*120,bg=hr.total>0?'hsla('+hue+',60%,70%,0.3)':'transparent';hh+='<tr style="background:'+bg+'"><td><strong>'+String(hr.hour).padStart(2,'0')+':00</strong></td><td>'+hr.total+'</td><td>'+hr.success+'</td><td>'+hr.failed+'</td><td>'+hr.rate+'%</td></tr>';}});
  document.querySelector('#hourlySummaryTable tbody').innerHTML=hh;
}}

// ===== 暗色模式 =====
function toggleTheme(){{darkMode=!darkMode;document.body.classList.toggle('dark',darkMode);document.getElementById('themeToggle').textContent=darkMode?'亮色模式':'暗色模式';}}

// ===== SVG 图表绘制 =====
function drawCharts() {{
  drawSuccessRateChart();
  drawErrorDonut();
  drawToolBarChart();
  drawTokenHistogram();
}}

function drawSuccessRateChart() {{
  var svg = document.getElementById('chartSuccessRate');
  var data = DAILY_SUMMARY || [];
  // 按日期筛选
  if (dateFrom || dateTo) {{
    data = data.filter(function(d) {{
      var p = parseDate(d.date); if (!p) return true;
      if (dateFrom && p < dateFrom) return false;
      if (dateTo && p > dateTo) return false;
      return true;
    }});
  }}
  if (data.length === 0) {{
    svg.innerHTML = '<text x="350" y="160" text-anchor="middle" fill="var(--muted)" font-size="14">无数据</text>';
    return;
  }}
  var W = 700, H = 320, padL = 55, padR = 20, padT = 20, padB = 55;
  var pw = W - padL - padR, ph = H - padT - padB;
  var rates = data.map(function(d) {{ return d.success_rate; }});
  var maxR = 105, minR = Math.max(0, Math.min.apply(null, rates) - 10);
  var h = '';

  // Y轴网格
  for (var i = 0; i <= 4; i++) {{
    var y = padT + (ph * i / 4);
    var v = Math.round(maxR - (maxR - minR) * i / 4);
    h += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '" stroke="var(--border)" stroke-width="1" stroke-dasharray="4,4"/>';
    h += '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" text-anchor="end" fill="var(--muted)" font-size="10">' + v + '%</text>';
  }}

  // 均值线
  var avg = Math.round(rates.reduce(function(a,b){{return a+b;}},0) / rates.length * 10) / 10;
  var avgY = padT + ph - ((avg - minR) / (maxR - minR)) * ph;
  h += '<line x1="' + padL + '" y1="' + avgY + '" x2="' + (W - padR) + '" y2="' + avgY + '" stroke="var(--danger)" stroke-width="1.5" stroke-dasharray="6,3"/>';
  h += '<text x="' + (W - padR - 4) + '" y="' + (avgY - 6) + '" text-anchor="end" fill="var(--danger)" font-size="10">均值 ' + avg + '%</text>';

  // 折线 + 面积
  var stepX = pw / Math.max(1, data.length - 1);
  var areaPts = '', linePts = '';
  data.forEach(function(d, i) {{
    var cx = padL + i * stepX;
    var cy = padT + ph - ((d.success_rate - minR) / (maxR - minR)) * ph;
    areaPts += cx + ',' + cy + ' ';
    linePts += cx + ',' + cy + ' ';
    // 数据点
    var color = d.success_rate >= 95 ? 'var(--accent)' : (d.success_rate >= 85 ? 'var(--warn)' : 'var(--danger)');
    h += '<circle cx="' + cx + '" cy="' + cy + '" r="3" fill="' + color + '"><title>' + d.date + ': ' + d.success_rate + '%</title></circle>';
    // X轴标签
    if (data.length <= 30 || i % Math.ceil(data.length / 15) === 0) {{
      h += '<text x="' + cx + '" y="' + (H - padB + 28) + '" text-anchor="middle" fill="var(--muted)" font-size="9" transform="rotate(-30,' + cx + ',' + (H - padB + 28) + ')">' + d.date.slice(5) + '</text>';
    }}
  }});
  // 填充区域
  var bottomY = padT + ph;
  var areaFull = areaPts + (padL + (data.length - 1) * stepX) + ',' + bottomY + ' ' + padL + ',' + bottomY;
  h += '<polygon points="' + areaFull + '" fill="var(--accent)" opacity="0.08"/>';
  // 折线
  h += '<polyline points="' + linePts + '" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>';

  // 95% 参考线
  var y95 = padT + ph - ((95 - minR) / (maxR - minR)) * ph;
  if (y95 > padT && y95 < padT + ph) {{
    h += '<line x1="' + padL + '" y1="' + y95 + '" x2="' + (W - padR) + '" y2="' + y95 + '" stroke="#ccc" stroke-width="1" stroke-dasharray="2,4"/>';
    h += '<text x="' + (padL + 4) + '" y="' + (y95 - 4) + '" fill="#aaa" font-size="9">95%</text>';
  }}

  svg.innerHTML = h;
}}

function drawErrorDonut() {{
  var svg = document.getElementById('chartErrorDonut');
  var fdata = filteredData().filter(function(r) {{ return r.status === 'failed' && r.error_type; }});
  if (fdata.length === 0) {{
    svg.innerHTML = '<text x="200" y="160" text-anchor="middle" fill="var(--muted)" font-size="14">无失败数据</text>';
    return;
  }}
  var counts = {{}};
  fdata.forEach(function(r) {{ var k = r.error_type || 'unknown'; counts[k] = (counts[k] || 0) + 1; }});
  var entries = Object.keys(counts).map(function(k) {{ return {{ name: k, count: counts[k] }}; }}).sort(function(a, b) {{ return b.count - a.count; }});
  var colors = ['#e76f51', '#f4a261', '#2a9d8f', '#457b9d', '#a8dadc', '#6d597a', '#b56576', '#355070'];
  var cx = 175, cy = 165, r = 110, ir = 55;
  var total = entries.reduce(function(s, e) {{ return s + e.count; }}, 0);
  var h = '';
  var angle = -Math.PI / 2;

  entries.forEach(function(e, i) {{
    var slice = (e.count / total) * Math.PI * 2;
    var x1 = cx + r * Math.cos(angle);
    var y1 = cy + r * Math.sin(angle);
    var x2 = cx + r * Math.cos(angle + slice);
    var y2 = cy + r * Math.sin(angle + slice);
    var large = slice > Math.PI ? 1 : 0;
    var color = colors[i % colors.length];
    var d = 'M' + cx + ',' + cy + ' L' + x1 + ',' + y1 + ' A' + r + ',' + r + ' 0 ' + large + ',1 ' + x2 + ',' + y2 + ' Z';
    h += '<path d="' + d + '" fill="' + color + '" opacity="0.85" stroke="var(--card-bg)" stroke-width="2"><title>' + e.name + ': ' + e.count + ' (' + Math.round(e.count/total*100) + '%)</title></path>';
    // 标签
    var midA = angle + slice / 2;
    var lx = cx + (r + 25) * Math.cos(midA);
    var ly = cy + (r + 25) * Math.sin(midA);
    if (e.count / total > 0.05) {{
      h += '<text x="' + lx + '" y="' + (ly + 4) + '" text-anchor="' + (midA > Math.PI/2 && midA < 3*Math.PI/2 ? 'end' : 'start') + '" fill="var(--text)" font-size="10">' + e.name + '</text>';
    }}
    angle += slice;
  }});
  // 中心文字
  h += '<text x="' + cx + '" y="' + (cy - 6) + '" text-anchor="middle" fill="var(--text)" font-size="13" font-weight="700">' + total + '</text>';
  h += '<text x="' + cx + '" y="' + (cy + 12) + '" text-anchor="middle" fill="var(--muted)" font-size="10">失败总数</text>';

  // 图例
  var lx2 = 330, ly2 = 30;
  entries.forEach(function(e, i) {{
    var y = ly2 + i * 22;
    h += '<rect x="' + lx2 + '" y="' + y + '" width="12" height="12" rx="2" fill="' + colors[i % colors.length] + '" opacity="0.85"/>';
    h += '<text x="' + (lx2 + 18) + '" y="' + (y + 10) + '" fill="var(--muted)" font-size="10">' + e.name + ' (' + Math.round(e.count/total*100) + '%)</text>';
    if (i > 8) return;
  }});

  svg.innerHTML = h;
  svg.setAttribute('viewBox', '0 0 500 320');
}}

function drawToolBarChart() {{
  var svg = document.getElementById('chartToolBar');
  var fdata = filteredData();
  var counts = {{}};
  fdata.forEach(function(r) {{
    var t = r.tool_name;
    if (!t) return;
    counts[t] = (counts[t] || 0) + 1;
  }});
  var entries = Object.keys(counts).map(function(k) {{ return {{ name: k, count: counts[k] }}; }}).sort(function(a, b) {{ return b.count - a.count; }}).slice(0, 8);
  if (entries.length === 0) {{
    svg.innerHTML = '<text x="250" y="140" text-anchor="middle" fill="var(--muted)" font-size="14">无工具调用数据</text>';
    return;
  }}
  var W = 500, H = 280, padL = 130, padR = 60, padT = 10, padB = 10;
  var pw = W - padL - padR;
  var barH = Math.min(28, (H - padT - padB) / entries.length - 6);
  var maxV = entries[0].count;
  var h = '';
  entries.forEach(function(e, i) {{
    var y = padT + i * (barH + 6);
    var w = (e.count / maxV) * pw;
    h += '<text x="' + (padL - 8) + '" y="' + (y + barH / 2 + 4) + '" text-anchor="end" fill="var(--text)" font-size="11">' + e.name + '</text>';
    h += '<rect x="' + padL + '" y="' + y + '" width="' + w + '" height="' + barH + '" rx="4" fill="var(--accent)" opacity="' + (0.5 + 0.5 * (e.count / maxV)) + '"/>';
    h += '<text x="' + (padL + w + 6) + '" y="' + (y + barH / 2 + 4) + '" fill="var(--muted)" font-size="10">' + e.count + '</text>';
  }});
  svg.innerHTML = h;
}}

function drawTokenHistogram() {{
  var svg = document.getElementById('chartTokenHist');
  var fdata = filteredData().map(function(r) {{ return r.tokens_used || 0; }});
  if (fdata.length === 0) {{
    svg.innerHTML = '<text x="300" y="150" text-anchor="middle" fill="var(--muted)" font-size="14">无数据</text>';
    return;
  }}
  // 分箱
  var maxT = Math.max.apply(null, fdata);
  var binCount = Math.min(25, Math.max(8, Math.ceil(fdata.length / 15)));
  var binW = Math.ceil(maxT / binCount);
  if (binW < 1) binW = 1;
  var bins = [];
  for (var i = 0; i < binCount; i++) bins.push(0);
  fdata.forEach(function(v) {{
    var idx = Math.min(binCount - 1, Math.floor(v / binW));
    bins[idx]++;
  }});

  // 中位数等统计值
  var sorted = fdata.slice().sort(function(a, b) {{ return a - b; }});
  var med = sorted[Math.floor(sorted.length / 2)];
  var q1 = sorted[Math.floor(sorted.length / 4)];
  var q3 = sorted[Math.floor(3 * sorted.length / 4)];
  var avg = Math.round(fdata.reduce(function(a, b) {{ return a + b; }}, 0) / fdata.length);

  var W = 600, H = 300, padL = 55, padR = 20, padT = 20, padB = 45;
  var pw = W - padL - padR, ph = H - padT - padB;
  var maxBin = Math.max.apply(null, bins);
  var barW = Math.max(6, pw / binCount - 2);
  var h = '';

  // Y轴
  for (var i = 0; i <= 4; i++) {{
    var y = padT + (ph * i / 4);
    var v = Math.round(maxBin * (1 - i / 4));
    h += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '" stroke="var(--border)" stroke-width="1"/>';
    h += '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" text-anchor="end" fill="var(--muted)" font-size="10">' + v + '</text>';
  }}

  // 柱状图
  bins.forEach(function(b, i) {{
    var barH = Math.max(1, (b / maxBin) * ph);
    var x = padL + i * (pw / binCount) + 1;
    var y = padT + ph - barH;
    var hue = 200 - (i / binCount) * 60;
    h += '<rect x="' + x + '" y="' + y + '" width="' + barW + '" height="' + barH + '" rx="1" fill="hsl(' + hue + ',50%,55%)" opacity="0.8"><title>' + (i * binW) + '-' + ((i + 1) * binW) + ': ' + b + ' 任务</title></rect>';
    // X轴标签
    if (i % Math.ceil(binCount / 12) === 0) {{
      h += '<text x="' + (x + barW / 2) + '" y="' + (H - padB + 16) + '" text-anchor="middle" fill="var(--muted)" font-size="8">' + (i * binW).toLocaleString() + '</text>';
    }}
  }});

  // 标记线
  [{{v: med, label: '中位数', color: 'var(--danger)'}},
   {{v: avg, label: '均值', color: 'var(--warn)'}}].forEach(function(m) {{
    var mx = padL + (m.v / (binCount * binW)) * pw;
    if (mx >= padL && mx <= W - padR) {{
      h += '<line x1="' + mx + '" y1="' + padT + '" x2="' + mx + '" y2="' + (padT + ph) + '" stroke="' + m.color + '" stroke-width="1.5" stroke-dasharray="4,3"/>';
      h += '<text x="' + mx + '" y="' + (padT - 4) + '" text-anchor="middle" fill="' + m.color + '" font-size="10">' + m.label + ' ' + m.v.toLocaleString() + '</text>';
    }}
  }});

  svg.innerHTML = h;
}}

// ===== 刷新时间 =====
(function() {{
  var now = new Date();
  var ts = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0') + ' ' + String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0') + ':' + String(now.getSeconds()).padStart(2,'0');
  var el = document.getElementById('refreshTime');
  if (el) el.textContent = '刷新时间: ' + ts;
}})();

// ===== CSV =====
// ===== 交互记录 =====
var interactPage = 0, interactPageSize = 50;

function filteredInteractions() {{
  if (!INTERACTIONS || !INTERACTIONS.length) return [];
  var list = INTERACTIONS;
  // 日期筛选
  if (dateFrom || dateTo) {{
    list = list.filter(function(r) {{
      var d = r.date || (r.timestamp || '').slice(0, 10);
      return (!dateFrom || d >= fmtDate(dateFrom)) && (!dateTo || d <= fmtDate(dateTo));
    }});
  }}
  // 状态筛选
  var st = document.getElementById('interactStatus');
  if (st && st.value !== 'all') list = list.filter(function(r) {{ return r.status === st.value; }});
  // 触发筛选
  var tg = document.getElementById('interactTrigger');
  if (tg && tg.value !== 'all') list = list.filter(function(r) {{ return r.trigger === tg.value; }});
  // 搜索
  var q = (document.getElementById('interactSearch') || {{}}).value || '';
  if (q.trim()) {{
    var lowerQ = q.trim().toLowerCase();
    list = list.filter(function(r) {{ return (r.user_prompt || '').toLowerCase().indexOf(lowerQ) >= 0; }});
  }}
  return list;
}}

function renderInteractions() {{
  var fdata = filteredInteractions();
  var total = fdata.length;
  document.getElementById('interactInfo').textContent = '共 ' + total + ' 条记录';

  var start = interactPage * interactPageSize;
  var pageData = fdata.slice(start, start + interactPageSize);

  var tbody = document.querySelector('#interactTable tbody');
  var h = '';
  pageData.forEach(function(r, i) {{
    var statusClass = r.status === 'success' ? 'badge-ok' : 'badge-fail';
    var statusLabel = r.status === 'success' ? '成功' : '失败';
    var triggerLabel = r.trigger === 'cron' ? 'Cron' : (r.trigger === 'user' ? 'User' : r.trigger || '');
    var duration = r.duration_ms >= 60000 ? Math.round(r.duration_ms / 60000) + '分' : Math.round(r.duration_ms / 1000) + '秒';
    var tokens = r.tokens_used > 1000 ? Math.round(r.tokens_used / 1000) + 'K' : String(r.tokens_used);
    var promptPreview = (r.prompt_preview || r.user_prompt || '').slice(0, 80);
    if ((r.user_prompt || '').length > 80) promptPreview += '...';
    h += '<tr style="cursor:pointer;" onclick="showPromptModal(' + (start + i) + ')" title="点击查看完整提问">';
    h += '<td style="font-size:.78rem;">' + (r.timestamp || '') + '</td>';
    h += '<td><span style="font-size:.72rem;padding:2px 6px;border-radius:3px;background:' + (r.trigger==='cron'?'#e8f5e9':'#e3f2fd') + ';color:' + (r.trigger==='cron'?'#2e7d32':'#1565c0') + ';">' + triggerLabel + '</span></td>';
    h += '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.8rem;">' + promptPreview + '</td>';
    h += '<td><span class="' + statusClass + '" style="font-size:.72rem;padding:2px 8px;">' + statusLabel + '</span></td>';
    h += '<td style="font-size:.78rem;">' + duration + '</td>';
    h += '<td style="font-size:.78rem;">' + tokens + '</td>';
    h += '</tr>';
  }});
  if (pageData.length === 0) {{
    h = '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:32px;">暂无匹配的交互记录</td></tr>';
  }}
  tbody.innerHTML = h;

  // 分页
  var totalPages = Math.ceil(total / interactPageSize);
  var ph = '';
  if (totalPages > 1) {{
    for (var p = 0; p < totalPages; p++) {{
      ph += '<button class="btn" style="' + (p === interactPage ? 'background:var(--accent);color:#fff;' : '') + 'min-width:32px;padding:4px 8px;font-size:.75rem;" onclick="interactPage=' + p + ';renderInteractions();">' + (p + 1) + '</button>';
    }}
  }}
  document.getElementById('interactPages').innerHTML = ph;
}}

function showPromptModal(idx) {{
  var fdata = filteredInteractions();
  var r = fdata[idx];
  if (!r) return;
  document.getElementById('promptModalTitle').textContent = r.timestamp + ' | ' + (r.trigger || '') + ' | ' + (r.status === 'success' ? '成功' : '失败');
  document.getElementById('promptContent').textContent = r.user_prompt || '(无提问内容)';
  document.getElementById('promptModal').classList.add('show');
}}
function closePromptModal() {{ document.getElementById('promptModal').classList.remove('show'); }}

// ===== CSV =====
function exportCSV(){{
  var fdata=filteredData();if(fdata.length===0){{alert('无数据');return;}}
  var headers=['task_id','timestamp','date','hour','status','error_type','duration_ms','tokens_used','tool_calls_count','tool_name','trigger'];
  var lines=[headers.join(',')];
  fdata.forEach(function(r){{var row=headers.map(function(h){{var v=r[h];if(v==null)return'';var s=String(v);if(s.indexOf(',')>=0||s.indexOf('"')>=0)s='"'+s.replace(/"/g,'""')+'"';return s;}});lines.push(row.join(','));}});
  var blob=new Blob(['\\uFEFF'+lines.join('\\n')],{{type:'text/csv;charset=utf-8'}});
  var url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='openclaw_export.csv';a.click();URL.revokeObjectURL(url);
}}

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded',function(){{
  document.getElementById('dateFrom').addEventListener('change',applyFilter);
  document.getElementById('dateTo').addEventListener('change',applyFilter);
  document.getElementById('detailModal').addEventListener('click',function(e){{if(e.target===this)closeModal();}});
  document.getElementById('promptModal').addEventListener('click',function(e){{if(e.target===this)closePromptModal();}});
  if(RAW_DATA.length>0){{
    var dates=RAW_DATA.map(function(r){{return r.date||(r.timestamp||'').slice(0,10);}}).filter(Boolean).sort();
    if(dates.length>0){{document.getElementById('dateFrom').min=dates[0];document.getElementById('dateFrom').max=dates[dates.length-1];document.getElementById('dateTo').min=dates[0];document.getElementById('dateTo').max=dates[dates.length-1];}}
  }}
  renderOverview();
  document.getElementById('filterInfo').textContent='筛选: '+RAW_DATA.length+' / '+RAW_DATA.length+' 条';
  var fc=filteredFailures().length;
  document.getElementById('failureBadge').style.display=fc>0?'inline-block':'none';
}});
</script>
</body>
</html>"""


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
    def _image_to_base64(image_path):
        """将 PNG 图片编码为 base64 字符串。"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

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
