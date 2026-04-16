#!/usr/bin/env python3

import sqlite3
import csv
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path.home() / ".local/share/opencode/opencode.db"
OUTPUT_DIR = Path.home() / "Documents/Opencode project/Opencode Token Cost"
STATE_FILE = OUTPUT_DIR / ".state.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    return sqlite3.connect(DB_PATH)


def query_daily_usage(conn, date):
    cursor = conn.cursor()
    start_time = f"{date}T00:00:00"
    next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    end_time = f"{next_day}T00:00:00"

    query = """
    SELECT
        LOWER(TRIM(json_extract(data, '$.modelID'))) as model_id,
        json_extract(data, '$.providerID') as provider_id,
        SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)) as input_tokens,
        SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)) as output_tokens,
        SUM(CAST(json_extract(data, '$.tokens.reasoning') AS INTEGER)) as reasoning_tokens,
        SUM(CAST(json_extract(data, '$.tokens.cache.read') AS INTEGER)) as cache_read,
        SUM(CAST(json_extract(data, '$.tokens.cache.write') AS INTEGER)) as cache_write,
        SUM(CAST(json_extract(data, '$.tokens.total') AS REAL)) as total_tokens,
        SUM(CAST(json_extract(data, '$.cost') AS REAL)) as cost,
        COUNT(*) as message_count
    FROM message
    WHERE json_extract(data, '$.tokens.total') IS NOT NULL
        AND datetime(time_created/1000, 'unixepoch') >= ?
        AND datetime(time_created/1000, 'unixepoch') < ?
    GROUP BY model_id, provider_id
    ORDER BY total_tokens DESC
    """
    cursor.execute(query, (start_time, end_time))
    return cursor.fetchall()


def query_date_range_usage(conn, start_date, end_date):
    cursor = conn.cursor()
    start_time = f"{start_date}T00:00:00"
    next_day = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    end_time = f"{next_day}T00:00:00"

    query = """
    SELECT
        date(datetime(time_created/1000, 'unixepoch')) as usage_date,
        LOWER(TRIM(json_extract(data, '$.modelID'))) as model_id,
        json_extract(data, '$.providerID') as provider_id,
        SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)) as input_tokens,
        SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)) as output_tokens,
        SUM(CAST(json_extract(data, '$.tokens.reasoning') AS INTEGER)) as reasoning_tokens,
        SUM(CAST(json_extract(data, '$.tokens.cache.read') AS INTEGER)) as cache_read,
        SUM(CAST(json_extract(data, '$.tokens.cache.write') AS INTEGER)) as cache_write,
        SUM(CAST(json_extract(data, '$.tokens.total') AS REAL)) as total_tokens,
        SUM(CAST(json_extract(data, '$.cost') AS REAL)) as cost,
        COUNT(*) as message_count
    FROM message
    WHERE json_extract(data, '$.tokens.total') IS NOT NULL
        AND datetime(time_created/1000, 'unixepoch') >= ?
        AND datetime(time_created/1000, 'unixepoch') < ?
    GROUP BY usage_date, model_id, provider_id
    ORDER BY usage_date DESC, total_tokens DESC
    """
    cursor.execute(query, (start_time, end_time))
    return cursor.fetchall()


def query_cumulative_usage(conn, days=30):
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = query_date_range_usage(conn, start_date, end_date)
    return rows, start_date, end_date


def export_daily_csv(date_str, rows):
    filename = OUTPUT_DIR / f"daily_{date_str}.csv"
    if not rows:
        rows = [("", "", 0, 0, 0, 0, 0, 0, 0, 0)]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "date",
                "model",
                "provider",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "cache_read",
                "cache_write",
                "total_tokens",
                "cost",
                "message_count",
            ]
        )
        for row in rows:
            writer.writerow([date_str] + list(row))

    print(f"Daily report saved: {filename}")
    return filename


def export_cumulative_csv(start_date, end_date, rows):
    filename = OUTPUT_DIR / f"cumulative_{start_date}_to_{end_date}.csv"
    model_totals = {}
    grand_total_tokens = 0
    grand_total_cost = 0
    grand_total_messages = 0

    for row in rows:
        (
            date,
            model,
            provider,
            input_t,
            output_t,
            reasoning,
            cache_r,
            cache_w,
            total,
            cost,
            msg_count,
        ) = row
        key = (model, provider)
        if key not in model_totals:
            model_totals[key] = {
                "input": 0,
                "output": 0,
                "reasoning": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total": 0,
                "cost": 0,
                "messages": 0,
            }
        model_totals[key]["input"] += input_t or 0
        model_totals[key]["output"] += output_t or 0
        model_totals[key]["reasoning"] += reasoning or 0
        model_totals[key]["cache_read"] += cache_r or 0
        model_totals[key]["cache_write"] += cache_w or 0
        model_totals[key]["total"] += total or 0
        model_totals[key]["cost"] += cost or 0
        model_totals[key]["messages"] += msg_count or 0

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "model",
                "provider",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "cache_read",
                "cache_write",
                "total_tokens",
                "total_cost",
                "message_count",
                "占比(%)",
            ]
        )

        sorted_models = sorted(
            model_totals.items(), key=lambda x: x[1]["total"], reverse=True
        )

        for (model, provider), totals in sorted_models:
            if totals["total"] > 0:
                grand_total_tokens += totals["total"]
                grand_total_cost += totals["cost"]
                grand_total_messages += totals["messages"]
                percentage = (
                    (totals["total"] / grand_total_tokens * 100)
                    if grand_total_tokens > 0
                    else 0
                )
                writer.writerow(
                    [
                        model,
                        provider,
                        totals["input"],
                        totals["output"],
                        totals["reasoning"],
                        totals["cache_read"],
                        totals["cache_write"],
                        totals["total"],
                        round(totals["cost"], 6),
                        totals["messages"],
                        f"{percentage:.2f}%",
                    ]
                )

        writer.writerow([])
        writer.writerow(
            [
                "TOTAL",
                "",
                "",
                "",
                "",
                "",
                "",
                grand_total_tokens,
                round(grand_total_cost, 6),
                grand_total_messages,
                "100%",
            ]
        )

    print(f"Cumulative report saved: {filename}")
    return filename, grand_total_tokens, grand_total_cost, grand_total_messages


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_cumulative_date": None,
        "cumulative_start_date": None,
        "total_tokens": 0,
        "total_cost": 0,
        "total_messages": 0,
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def should_generate_cumulative(state, current_date):
    if state["cumulative_start_date"] is None:
        return False
    start = datetime.strptime(state["cumulative_start_date"], "%Y-%m-%d")
    current = datetime.strptime(current_date, "%Y-%m-%d")
    days_diff = (current - start).days
    return days_diff >= 30 and (
        days_diff % 30 == 0
        or state["last_cumulative_date"] != state["cumulative_start_date"]
    )


def generate_html_dashboard(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            date(datetime(time_created/1000, 'unixepoch')) as usage_date,
            LOWER(TRIM(json_extract(data, '$.modelID'))) as model_id,
            json_extract(data, '$.providerID') as provider_id,
            SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)) as input_tokens,
            SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)) as output_tokens,
            SUM(CAST(json_extract(data, '$.tokens.reasoning') AS INTEGER)) as reasoning_tokens,
            SUM(CAST(json_extract(data, '$.tokens.cache.read') AS INTEGER)) as cache_read,
            SUM(CAST(json_extract(data, '$.tokens.cache.write') AS INTEGER)) as cache_write,
            SUM(CAST(json_extract(data, '$.tokens.total') AS REAL)) as total_tokens,
            SUM(CAST(json_extract(data, '$.cost') AS REAL)) as cost,
            COUNT(*) as message_count
        FROM message
        WHERE json_extract(data, '$.tokens.total') IS NOT NULL
        GROUP BY usage_date, model_id, provider_id
        ORDER BY usage_date ASC, total_tokens DESC
    """)
    rows = cursor.fetchall()

    daily_totals = {}
    model_totals = {}
    provider_costs = {}
    provider_totals = {}
    dates = []
    data_js = []

    for row in rows:
        (
            date,
            model,
            provider,
            input_t,
            output_t,
            reasoning,
            cache_r,
            cache_w,
            total,
            cost,
            msg_count,
        ) = row
        if date not in dates:
            dates.append(date)
        daily_totals[date] = daily_totals.get(date, 0) + total
        model_totals[model] = model_totals.get(model, 0) + total
        provider_costs[provider] = provider_costs.get(provider, 0) + cost
        if provider not in provider_totals:
            provider_totals[provider] = {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total": 0,
                "cost": 0,
                "messages": 0,
            }
        provider_totals[provider]["input"] += input_t or 0
        provider_totals[provider]["output"] += output_t or 0
        provider_totals[provider]["cache_read"] += cache_r or 0
        provider_totals[provider]["cache_write"] += cache_w or 0
        provider_totals[provider]["total"] += total or 0
        provider_totals[provider]["cost"] += cost or 0
        provider_totals[provider]["messages"] += msg_count or 0
        data_js.append(
            {
                "date": date,
                "model": model,
                "provider": provider,
                "input": input_t or 0,
                "output": output_t or 0,
                "reasoning": reasoning or 0,
                "cache_read": cache_r or 0,
                "cache_write": cache_w or 0,
                "total": total or 0,
                "cost": cost or 0,
                "msg_count": msg_count,
            }
        )

    total_tokens = sum(daily_totals.values())
    total_cost = sum(provider_costs.values())
    total_messages = sum(r["msg_count"] for r in data_js)
    active_days = len(daily_totals)

    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenCode Token 使用报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-green: #22c55e;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, var(--bg-secondary), var(--bg-card));
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .header h1 {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-blue), #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .header p {{ color: var(--text-secondary); font-size: 0.9rem; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .stat-card .label {{ font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px; text-transform: uppercase; }}
        .stat-card .value {{ font-size: 1.8rem; font-weight: 700; }}
        .stat-card .sub {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 4px; }}
        .charts-container {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .chart-card {{ background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid rgba(255,255,255,0.05); }}
        .chart-card.full-width {{ grid-column: 1 / -1; }}
        .chart-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
        .chart-title::before {{ content: ''; width: 4px; height: 20px; background: var(--accent-blue); border-radius: 2px; }}
        .chart-wrapper {{ position: relative; height: 300px; }}
        .chart-wrapper.large {{ height: 400px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        th {{ background: var(--bg-card); font-weight: 600; font-size: 0.85rem; color: var(--text-secondary); text-transform: uppercase; }}
        tr:hover {{ background: rgba(255,255,255,0.02); }}
        td {{ font-size: 0.9rem; }}
        .model-badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; background: var(--accent-blue); }}
        .cost-positive {{ color: var(--accent-green); }}
        .footer {{ text-align: center; padding: 20px; color: var(--text-secondary); font-size: 0.85rem; }}
        @media (max-width: 768px) {{ .charts-container {{ grid-template-columns: 1fr; }} .stat-card .value {{ font-size: 1.4rem; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 OpenCode Token 使用报告</h1>
        <p>数据来源: ~/.local/share/opencode/opencode.db | 更新于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>

    <div class="stats-grid">
        <div class="stat-card"><div class="label">总 Token 消耗</div><div class="value">{(total_tokens / 1000000):.1f}M</div><div class="sub">{min(dates) if dates else "-"} ~ {max(dates) if dates else "-"}</div></div>
        <div class="stat-card"><div class="label">总成本</div><div class="value cost-positive">${total_cost:.2f}</div><div class="sub">第三方 API 费用</div></div>
        <div class="stat-card"><div class="label">总消息数</div><div class="value">{total_messages:,}</div><div class="sub">活跃天数: {active_days}</div></div>
        <div class="stat-card"><div class="label">日均 Token</div><div class="value">{(total_tokens / active_days / 1000000):.1f}M</div><div class="sub">按活跃天计算</div></div>
    </div>

    <div class="charts-container">
        <div class="chart-card full-width">
            <div class="chart-title">每日 Token 消耗趋势</div>
            <div class="chart-wrapper large"><canvas id="dailyTrendChart"></canvas></div>
        </div>
        <div class="chart-card"><div class="chart-title">模型 Token 占比</div><div class="chart-wrapper"><canvas id="modelPieChart"></canvas></div></div>
        <div class="chart-card"><div class="chart-title">Provider 成本分布</div><div class="chart-wrapper"><canvas id="costPieChart"></canvas></div></div>
        <div class="chart-card full-width">
            <div class="chart-title">Provider Token vs 费用 对比</div>
            <div class="chart-wrapper"><canvas id="providerCompareChart"></canvas></div>
        </div>
        <div class="chart-card full-width">
            <div class="chart-title">堆叠每日消耗（按模型）</div>
            <div class="chart-wrapper large"><canvas id="modelStackedChart"></canvas></div>
        </div>
        <div class="chart-card full-width">
            <div class="chart-title">详细数据表格</div>
            <div style="max-height: 400px; overflow-y: auto;">
                <table id="detailTable"><thead><tr><th>日期</th><th>模型</th><th>Provider</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Total</th><th>Cost</th></tr></thead><tbody></tbody></table>
            </div>
        </div>
    </div>

    <div class="footer"><p>OpenCode Token Tracker | 数据每5分钟自动刷新</p></div>

    <script>
    const rawData = {json.dumps(data_js)};
    const chartColors = ['#3b82f6','#22c55e','#a855f7','#f97316','#ec4899','#06b6d4','#eab308','#ef4444','#8b5cf6','#14b8a6'];
    const dailyTotals = {{}};
    const modelTotals = {{}};
    rawData.forEach(row => {{
        dailyTotals[row.date] = (dailyTotals[row.date] || 0) + row.total;
        modelTotals[row.model] = (modelTotals[row.model] || 0) + row.total;
    }});
    const dates = Object.keys(dailyTotals).sort();
    const modelLabels = Object.keys(modelTotals).sort((a,b) => modelTotals[b]-modelTotals[a]);
    const totalTokens = {total_tokens};

    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';

    new Chart(document.getElementById('dailyTrendChart'), {{
        type: 'line',
        data: {{
            labels: dates,
            datasets: [{{
                label: '每日 Token',
                data: dates.map(d => dailyTotals[d]),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59,130,246,0.1)',
                fill: true, tension: 0.4, pointRadius: 4
            }}]
        }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => (ctx.raw/1000000).toFixed(2)+'M' }} }} }}, scales: {{ y: {{ ticks: {{ callback: v => (v/1000000).toFixed(0)+'M' }}, grid: {{ color: 'rgba(255,255,255,0.05)' }} }}, x: {{ grid: {{ display: false }} }} }} }}
    }});

    new Chart(document.getElementById('modelPieChart'), {{
        type: 'doughnut',
        data: {{ labels: modelLabels, datasets: [{{ data: modelLabels.map(m => modelTotals[m]), backgroundColor: chartColors, borderWidth: 0 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right', labels: {{ boxWidth: 12, padding: 8, font: {{ size: 11 }} }} }}, tooltip: {{ callbacks: {{ label: ctx => ctx.label+': '+(ctx.raw/1000000).toFixed(1)+'M ('+((ctx.raw/totalTokens)*100).toFixed(1)+'%)' }} }} }} }}
    }});

    const providerCosts = {{}};
    rawData.forEach(row => {{ providerCosts[row.provider] = (providerCosts[row.provider] || 0) + row.cost; }});
    const providerLabels = Object.keys(providerCosts);
    new Chart(document.getElementById('costPieChart'), {{
        type: 'doughnut',
        data: {{ labels: providerLabels, datasets: [{{ data: providerLabels.map(p => providerCosts[p]), backgroundColor: ['#f97316','#22c55e','#a855f7','#ec4899','#06b6d4'], borderWidth: 0 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right', labels: {{ boxWidth: 12, padding: 8, font: {{ size: 11 }} }} }}, tooltip: {{ callbacks: {{ label: ctx => ctx.label+': $'+ctx.raw.toFixed(2) }} }} }} }}
    }});

    const providerTotals = {json.dumps(provider_totals)};
    const pvLabels = Object.keys(providerTotals);
    new Chart(document.getElementById('providerCompareChart'), {{
        type: 'bar',
        data: {{
            labels: pvLabels,
            datasets: [{{
                label: 'Token (M)',
                data: pvLabels.map(p => (providerTotals[p].total / 1000000).toFixed(2)),
                backgroundColor: 'rgba(59,130,246,0.8)',
                yAxisID: 'y'
            }}, {{
                label: '费用 ($)',
                data: pvLabels.map(p => providerTotals[p].cost.toFixed(2)),
                backgroundColor: 'rgba(249,115,22,0.8)',
                yAxisID: 'y1'
            }}]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            plugins: {{
                legend: {{ position: 'top', labels: {{ boxWidth: 12, padding: 8 }},
                tooltip: {{
                    callbacks: {{
                        label: function(ctx) {{
                            if (ctx.dataset.label === 'Token (M)') return ctx.dataset.label + ': ' + ctx.raw + 'M';
                            return ctx.dataset.label + ': $' + ctx.raw;
                        }}
                    }}
                }}
            }},
            scales: {{
                y: {{ type: 'linear', position: 'left', title: {{ display: true, text: 'Token (M)' }}, grid: {{ color: 'rgba(255,255,255,0.05)' }} }},
                y1: {{ type: 'linear', position: 'right', title: {{ display: true, text: '费用 ($)' }}, grid: {{ drawOnChartArea: false }} }},
                x: {{ grid: {{ display: false }} }}
            }}
        }}
    }});

    const topModels = modelLabels.slice(0, 8);
    const stackedData = dates.map(date => {{
        const row = {{}};
        topModels.forEach(model => {{
            const entry = rawData.find(r => r.date === date && r.model === model);
            row[model] = entry ? entry.total : 0;
        }});
        return row;
    }});
    new Chart(document.getElementById('modelStackedChart'), {{
        type: 'bar',
        data: {{
            labels: dates,
            datasets: topModels.map((model, i) => ({{
                label: model,
                data: stackedData.map(d => d[model] || 0),
                backgroundColor: chartColors[i % chartColors.length],
                stack: 'stack0'
            }}))
        }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 8, font: {{ size: 10 }} }} }}, tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label+': '+(ctx.raw/1000000).toFixed(2)+'M' }} }} }}, scales: {{ x: {{ stacked: true, grid: {{ display: false }} }}, y: {{ stacked: true, ticks: {{ callback: v => (v/1000000).toFixed(0)+'M' }}, grid: {{ color: 'rgba(255,255,255,0.05)' }} }} }} }}
    }});

    const tbody = document.querySelector('#detailTable tbody');
    rawData.sort((a,b) => b.date.localeCompare(a.date) || b.total - a.total).forEach(row => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${{row.date}}</td><td><span class="model-badge">${{row.model}}</span></td><td>${{row.provider}}</td><td>${{(row.input/1000).toFixed(1)}}K</td><td>${{(row.output/1000).toFixed(1)}}K</td><td>${{(row.cache_read/1000000).toFixed(2)}}M</td><td><strong>${{(row.total/1000000).toFixed(2)}}M</strong></td><td class="${{row.cost > 0 ? 'cost-positive' : ''}}">${{row.cost > 0 ? '$'+row.cost.toFixed(4) : '-'}}</td>`;
        tbody.appendChild(tr);
    }});

    setTimeout(() => location.reload(), 5 * 60 * 1000);
    </script>
</body>
</html>"""

    with open(OUTPUT_DIR / "dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_template)


def export_json(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            date(datetime(time_created/1000, 'unixepoch')) as usage_date,
            LOWER(TRIM(json_extract(data, '$.modelID'))) as model_id,
            json_extract(data, '$.providerID') as provider_id,
            SUM(CAST(json_extract(data, '$.tokens.input') AS INTEGER)) as input_tokens,
            SUM(CAST(json_extract(data, '$.tokens.output') AS INTEGER)) as output_tokens,
            SUM(CAST(json_extract(data, '$.tokens.reasoning') AS INTEGER)) as reasoning_tokens,
            SUM(CAST(json_extract(data, '$.tokens.cache.read') AS INTEGER)) as cache_read,
            SUM(CAST(json_extract(data, '$.tokens.cache.write') AS INTEGER)) as cache_write,
            SUM(CAST(json_extract(data, '$.tokens.total') AS REAL)) as total_tokens,
            SUM(CAST(json_extract(data, '$.cost') AS REAL)) as cost,
            COUNT(*) as message_count
        FROM message
        WHERE json_extract(data, '$.tokens.total') IS NOT NULL
        GROUP BY usage_date, model_id, provider_id
        ORDER BY usage_date ASC, total_tokens DESC
    """)
    rows = cursor.fetchall()

    daily_totals = {}
    model_totals = {}
    provider_costs = {}
    provider_totals = {}
    dates = []
    data_list = []

    for row in rows:
        (
            date,
            model,
            provider,
            input_t,
            output_t,
            reasoning,
            cache_r,
            cache_w,
            total,
            cost,
            msg_count,
        ) = row
        if date not in dates:
            dates.append(date)
        daily_totals[date] = daily_totals.get(date, 0) + total
        model_totals[model] = model_totals.get(model, 0) + total
        provider_costs[provider] = provider_costs.get(provider, 0) + cost
        if provider not in provider_totals:
            provider_totals[provider] = {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total": 0,
                "cost": 0,
                "messages": 0,
            }
        provider_totals[provider]["input"] += input_t or 0
        provider_totals[provider]["output"] += output_t or 0
        provider_totals[provider]["cache_read"] += cache_r or 0
        provider_totals[provider]["cache_write"] += cache_w or 0
        provider_totals[provider]["total"] += total or 0
        provider_totals[provider]["cost"] += cost or 0
        provider_totals[provider]["messages"] += msg_count or 0
        data_list.append(
            {
                "date": date,
                "model": model,
                "provider": provider,
                "input": input_t or 0,
                "output": output_t or 0,
                "reasoning": reasoning or 0,
                "cache_read": cache_r or 0,
                "cache_write": cache_w or 0,
                "total": total or 0,
                "cost": cost or 0,
                "msg_count": msg_count,
            }
        )

    total_tokens = sum(daily_totals.values())
    total_cost = sum(provider_costs.values())
    total_messages = sum(r["msg_count"] for r in data_list)

    result = {
        "summary": {
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_messages": total_messages,
            "active_days": len(daily_totals),
            "date_range": {
                "start": min(dates) if dates else None,
                "end": max(dates) if dates else None,
            },
            "updated_at": datetime.now().isoformat(),
        },
        "daily_totals": daily_totals,
        "model_totals": model_totals,
        "provider_costs": provider_costs,
        "provider_totals": provider_totals,
        "raw_data": data_list,
    }

    with open(OUTPUT_DIR / "data.json", "w", encoding="utf-8") as f:
        json.dump(result, f)


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = "daily"

    conn = get_db_connection()
    try:
        if command == "daily":
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            rows = query_daily_usage(conn, yesterday)

            if rows:
                export_daily_csv(yesterday, rows)
                state = load_state()
                if state["cumulative_start_date"] is None:
                    state["cumulative_start_date"] = yesterday
                    state["last_cumulative_date"] = yesterday
                save_state(state)
                print(f"Daily report for {yesterday} generated successfully.")
            else:
                print(f"No token usage data found for {yesterday}")

        elif command == "cumulative":
            rows, start_date, end_date = query_cumulative_usage(conn, 30)
            if rows:
                export_cumulative_csv(start_date, end_date, rows)
                print(
                    f"30-day cumulative report ({start_date} to {end_date}) generated successfully."
                )
            else:
                print("No token usage data found for the last 30 days.")

        elif command == "check":
            state = load_state()
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if should_generate_cumulative(state, yesterday):
                rows, start_date, end_date = query_cumulative_usage(conn, 30)
                if rows:
                    export_cumulative_csv(start_date, end_date, rows)
                    state["last_cumulative_date"] = yesterday
                    save_state(state)
                    print("30-day cumulative report generated and saved.")
                else:
                    print("No data for cumulative report.")
            else:
                print(
                    f"Cumulative report not due yet. Started: {state['cumulative_start_date']}"
                )

        elif command == "full-history":
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(date(datetime(time_created/1000, 'unixepoch'))) as earliest,
                       MAX(date(datetime(time_created/1000, 'unixepoch'))) as latest
                FROM message
                WHERE json_extract(data, '$.tokens.total') IS NOT NULL
            """)
            result = cursor.fetchone()
            earliest, latest = result[0], result[1]

            if earliest and latest:
                rows = query_date_range_usage(conn, earliest, latest)
                filename = OUTPUT_DIR / f"full_history_{earliest}_to_{latest}.csv"
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "date",
                            "model",
                            "provider",
                            "input_tokens",
                            "output_tokens",
                            "reasoning_tokens",
                            "cache_read",
                            "cache_write",
                            "total_tokens",
                            "cost",
                            "message_count",
                        ]
                    )
                    for row in rows:
                        writer.writerow(row)
                print(f"Full history exported to: {filename}")
            else:
                print("No data found for full history export.")

        elif command == "html":
            generate_html_dashboard(conn)
            print("HTML dashboard generated successfully.")

        elif command == "json":
            export_json(conn)
            print("JSON data exported successfully.")

        else:
            print(f"Unknown command: {command}")
            print(
                "Usage: python3 token_tracker.py [daily|cumulative|check|full-history|html|json]"
            )
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
