"""
多客户端 Dashboard 构建器 — 复用 report_generator.py 的模板渲染模式。

与现有单机 Dashboard 的区别:
  - 数据不内嵌到 HTML 中，而是由前端 JS 通过 /api/v1/* 接口动态加载
  - 增加客户端选择器，支持多客户端对比
  - 保留相同的视觉风格 (KPI 卡片 + SVG 图表 + 暗色模式)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime

from server.db import get_all_clients

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def build_dashboard(db: sqlite3.Connection) -> str:
    """构建多客户端监控 Dashboard HTML。

    注入的数据仅限于客户端列表 (用于选择器) 和服务器时间。
    图表数据由前端 JS 通过 fetch 动态获取。
    """
    clients = get_all_clients(db)
    today = datetime.now().strftime("%Y年%m月%d日")

    # 准备注入的初始数据
    init_data = {
        "clients": clients,
        "server_time": datetime.now().isoformat(),
    }

    template_path = os.path.join(TEMPLATE_DIR, "dashboard_multi.html")

    # 如果多客户端模板存在则使用，否则 fallback 到内建模板
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    else:
        template = _FALLBACK_TEMPLATE

    return template.format(
        today=today,
        init_data_json=json.dumps(init_data, ensure_ascii=False),
    )


# =====================================================================
#  内建回退模板 — 当 templates/dashboard_multi.html 不存在时使用
#  这是一个完整可用的多客户端 Dashboard SPA
# =====================================================================

_FALLBACK_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenClaw 多客户端监控 — {today}</title>
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
  body{{
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--text);line-height:1.6;
    padding:24px;max-width:1400px;margin:0 auto;overflow-x:hidden;
    transition:background .3s,color .3s;
  }}
  .topbar{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px;}}
  .topbar h1{{font-size:1.4rem;font-weight:700;}}
  .toolbar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:20px;}}
  select, input, .btn{{
    padding:8px 14px;border-radius:8px;border:1px solid var(--border);
    background:var(--card-bg);color:var(--text);font-size:.85rem;font-family:inherit;
  }}
  select:focus, input:focus{{outline:none;border-color:var(--accent);}}
  .btn{{cursor:pointer;font-weight:600;}}
  .btn:hover{{border-color:var(--accent);}}
  .btn-primary{{background:var(--accent);color:#fff;border-color:var(--accent);}}

  /* KPI 卡片网格 */
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:24px;}}
  .kpi-card{{background:var(--card-bg);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow);}}
  .kpi-card .label{{font-size:.75rem;color:var(--muted);margin-bottom:4px;}}
  .kpi-card .value{{font-size:1.4rem;font-weight:700;}}
  .kpi-card .value.good{{color:var(--accent);}}
  .kpi-card .value.warn{{color:var(--warn);}}
  .kpi-card .value.bad{{color:var(--danger);}}

  /* 多客户端对比表 */
  .section{{margin-bottom:24px;}}
  .section h2{{font-size:1.1rem;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid var(--border);}}
  .table-wrap{{overflow-x:auto;background:var(--card-bg);border-radius:var(--radius);box-shadow:var(--shadow);}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem;}}
  th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid var(--border);}}
  th{{background:var(--bg);color:var(--muted);font-weight:600;font-size:.78rem;white-space:nowrap;}}
  tr:hover{{background:var(--bg);}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.75rem;font-weight:600;}}
  .badge.good{{background:#d4edda;color:#155724;}}
  .badge.warn{{background:#fff3cd;color:#856404;}}
  .badge.bad{{background:#f8d7da;color:#721c24;}}

  /* 图表区 */
  .chart-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px;}}
  .chart-card{{background:var(--card-bg);border-radius:var(--radius);padding:16px;box-shadow:var(--shadow);}}
  .chart-card h3{{font-size:.95rem;margin-bottom:6px;}}
  .chart-card svg{{width:100%;max-height:320px;}}
  .chart-card .desc{{font-size:.75rem;color:var(--muted);margin-bottom:8px;}}

  /* 加载状态 */
  .loading{{text-align:center;padding:40px;color:var(--muted);}}
  .error-banner{{background:var(--danger);color:#fff;padding:12px 18px;border-radius:8px;margin-bottom:16px;display:none;}}

  .footer{{text-align:center;color:var(--muted);font-size:.78rem;margin-top:32px;}}

  body.dark svg text {{ fill: #c0c0d0; }}
  body.dark svg line {{ stroke: #3a3a5a; }}
  body.dark svg rect.chart-bg {{ fill: #1a1a2e; }}

  @media(max-width:600px){{
    body{{padding:12px 10px 32px;}}
    .kpi-grid{{grid-template-columns:repeat(2,1fr);gap:8px;}}
    .chart-grid{{grid-template-columns:1fr;}}
  }}
</style>
</head>
<body>

<div class="topbar">
  <h1>OpenClaw 多客户端监控</h1>
  <button class="btn" id="themeToggle" onclick="toggleTheme()">暗色模式</button>
</div>

<div class="toolbar">
  <label style="font-size:.85rem;color:var(--muted);">客户端:</label>
  <select id="clientSelect" onchange="refreshAll()">
    <option value="">全部客户端</option>
  </select>
  <label style="font-size:.85rem;color:var(--muted);margin-left:8px;">时间:</label>
  <select id="dateRange" onchange="refreshAll()">
    <option value="7">最近 7 天</option>
    <option value="30">最近 30 天</option>
    <option value="90">最近 90 天</option>
    <option value="0">全部</option>
  </select>
  <button class="btn btn-primary" onclick="refreshAll()">刷新</button>
  <span id="refreshBadge" style="font-size:.75rem;color:var(--muted);"></span>
</div>

<div class="error-banner" id="errorBanner"></div>

<!-- KPI 卡片 -->
<div class="kpi-grid" id="kpiCards"></div>

<!-- 多客户端对比 -->
<div class="section">
  <h2>客户端对比</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>客户端</th><th>任务总数</th><th>成功</th><th>失败</th><th>成功率</th>
        <th>Token 消耗</th><th>平均耗时(ms)</th><th>最高频错误</th>
      </tr></thead>
      <tbody id="clientCompareBody"><tr><td colspan="8" class="loading">加载中...</td></tr></tbody>
    </table>
  </div>
</div>

<!-- 记录明细 -->
<div class="section">
  <h2>最近记录</h2>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>客户端</th><th>任务 ID</th><th>时间</th><th>状态</th><th>耗时(ms)</th>
        <th>Token</th><th>工具</th><th>错误类型</th>
      </tr></thead>
      <tbody id="recordsBody"><tr><td colspan="8" class="loading">加载中...</td></tr></tbody>
    </table>
  </div>
</div>

<div class="footer">
  OpenClaw Monitor Server v1.0.0 &nbsp;|&nbsp; 数据实时刷新 &nbsp;|&nbsp; {today}
</div>

<script>
// ===== 初始数据 =====
var INIT_DATA = {init_data_json};
var CLIENT_LIST = INIT_DATA.clients || [];

// ===== 全局状态 =====
var darkMode = false;

// ===== 初始化 =====
(function init() {{
  // 填充客户端选择器
  var sel = document.getElementById('clientSelect');
  CLIENT_LIST.forEach(function(c) {{
    var opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name + ' (' + c.id + ')';
    sel.appendChild(opt);
  }});

  // 恢复暗色模式
  if (localStorage.getItem('mm-dark') === '1') {{
    darkMode = true;
    document.body.classList.add('dark');
    document.getElementById('themeToggle').textContent = '亮色模式';
  }}

  refreshAll();
  // 每 60 秒自动刷新
  setInterval(refreshAll, 60000);
}})();

function toggleTheme() {{
  darkMode = !darkMode;
  document.body.classList.toggle('dark', darkMode);
  document.getElementById('themeToggle').textContent = darkMode ? '亮色模式' : '暗色模式';
  localStorage.setItem('mm-dark', darkMode ? '1' : '0');
}}

function showError(msg) {{
  var el = document.getElementById('errorBanner');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(function() {{ el.style.display = 'none'; }}, 5000);
}}

// ===== 数据加载 =====

function getQueryParams() {{
  var clientId = document.getElementById('clientSelect').value;
  var days = parseInt(document.getElementById('dateRange').value);
  var params = [];
  if (clientId) params.push('client_id=' + encodeURIComponent(clientId));
  if (days > 0) {{
    var d = new Date();
    d.setDate(d.getDate() - days);
    params.push('start=' + d.toISOString());
  }}
  return params.length ? '?' + params.join('&') : '';
}}

function refreshAll() {{
  var qs = getQueryParams();
  fetchStats(qs);
  fetchRecords(qs);
  document.getElementById('refreshBadge').textContent = '刷新于 ' + new Date().toLocaleTimeString();
}}

function fetchStats(qs) {{
  fetch('/api/v1/stats' + qs)
    .then(function(r) {{ return r.json(); }})
    .then(function(stats) {{ renderKPIs(stats); renderCompare(stats); }})
    .catch(function(e) {{ showError('统计数据加载失败: ' + e.message); }});
}}

function fetchRecords(qs) {{
  fetch('/api/v1/telemetry' + qs + (qs ? '&' : '?') + 'limit=20')
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{ renderRecords(data.records || []); }})
    .catch(function(e) {{ showError('记录加载失败: ' + e.message); }});
}}

// ===== 渲染 =====

function renderKPIs(s) {{
  if (!s.total_tasks) {{
    document.getElementById('kpiCards').innerHTML = '<div class="loading" style="grid-column:1/-1">暂无数据</div>';
    return;
  }}
  var rateTone = s.overall_success_rate >= 95 ? 'good' : (s.overall_success_rate >= 85 ? 'warn' : 'bad');
  var cards = [
    ['任务总数', s.total_tasks.toLocaleString(), ''],
    ['成功率', s.overall_success_rate + '%', rateTone],
    ['Token 总消耗', s.total_tokens.toLocaleString(), ''],
    ['平均 Token/任务', s.avg_tokens_per_task.toLocaleString(), ''],
    ['平均耗时', s.avg_duration_ms.toLocaleString() + ' ms', ''],
    ['P95 耗时', s.p95_duration_ms.toLocaleString() + ' ms', ''],
    ['最高频错误', s.top_error_type, ''],
    ['最高频工具', s.top_tool, ''],
  ];
  var html = '';
  cards.forEach(function(c) {{
    html += '<div class="kpi-card"><div class="label">' + c[0] + '</div>' +
      '<div class="value ' + (c[2] || '') + '">' + c[1] + '</div></div>';
  }});
  document.getElementById('kpiCards').innerHTML = html;
}}

function renderCompare(s) {{
  var clients = s.per_client || [];
  if (!clients.length) {{
    document.getElementById('clientCompareBody').innerHTML = '<tr><td colspan="8" style="color:var(--muted)">单客户端视图 — 选择"全部客户端"查看对比</td></tr>';
    return;
  }}
  var html = '';
  clients.forEach(function(c) {{
    var tone = c.overall_success_rate >= 95 ? 'good' : (c.overall_success_rate >= 85 ? 'warn' : 'bad');
    html += '<tr>' +
      '<td><strong>' + c.client_name + '</strong><br><span style="font-size:.72rem;color:var(--muted)">' + c.client_id + '</span></td>' +
      '<td>' + c.total_tasks + '</td>' +
      '<td>' + c.total_success + '</td>' +
      '<td>' + c.total_failed + '</td>' +
      '<td><span class="badge ' + tone + '">' + c.overall_success_rate + '%</span></td>' +
      '<td>' + c.total_tokens.toLocaleString() + '</td>' +
      '<td>' + (c.avg_duration_ms || 0).toFixed(0) + '</td>' +
      '<td>' + c.top_error_type + '</td>' +
      '</tr>';
  }});
  document.getElementById('clientCompareBody').innerHTML = html;
}}

function renderRecords(records) {{
  if (!records.length) {{
    document.getElementById('recordsBody').innerHTML = '<tr><td colspan="8" style="color:var(--muted)">无记录</td></tr>';
    return;
  }}
  var html = '';
  records.forEach(function(r) {{
    var statusBadge = r.status === 'success'
      ? '<span class="badge good">成功</span>'
      : '<span class="badge bad">失败</span>';
    var ts = r.timestamp ? r.timestamp.replace('T', ' ').substring(0, 19) : '';
    html += '<tr>' +
      '<td style="font-size:.8rem;">' + (r.client_id || '') + '</td>' +
      '<td style="font-size:.78rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + (r.task_id || '') + '">' + (r.task_id || '').substring(0, 24) + '</td>' +
      '<td>' + ts + '</td>' +
      '<td>' + statusBadge + '</td>' +
      '<td>' + (r.duration_ms || 0).toLocaleString() + '</td>' +
      '<td>' + (r.tokens_used || 0).toLocaleString() + '</td>' +
      '<td>' + (r.tool_name || '') + '</td>' +
      '<td style="color:var(--danger)">' + (r.error_type || '') + '</td>' +
      '</tr>';
  }});
  document.getElementById('recordsBody').innerHTML = html;
}}
</script>

</body>
</html>"""
