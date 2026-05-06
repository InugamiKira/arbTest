# -*- coding: utf-8 -*-
# 程序C —— 纯静态展示版，可直接部署Vercel，无爬虫、无外网请求
import os
import sys
import pandas as pd
import sqlite3
import re
import contextlib
from datetime import datetime
from flask import Flask, render_template_string

app = Flask(__name__)

def _ensure_quotes_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS index_realtime_quotes (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            last_price REAL,
            prev_close REAL,
            pct_change REAL,
            quote_time TEXT,
            source TEXT,
            updated_at TEXT
        )
    ''')
    conn.commit()

def _parse_position_ratio(raw):
    s = str(raw).strip()
    if not s or s.lower() == 'nan': return 0.95
    try:
        if s.endswith('%'): return float(s[:-1]) / 100.0
        v = float(s)
        return v / 100.0 if v > 1.5 else v
    except Exception:
        return 0.95

def _get_exchange_rate_mid_pct_from_db(currency="usd"):
    field_name = "usd_cny_mid" if currency == "usd" else "hkd_cny_mid"
    db_local = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
    try:
        with contextlib.closing(sqlite3.connect(db_local)) as conn:
            rows = conn.execute(f"""
                SELECT date, {field_name} FROM exchange_rate WHERE {field_name} IS NOT NULL ORDER BY date DESC LIMIT 2
            """).fetchall()
            if len(rows) >= 2 and rows[0][1] and rows[1][1]:
                latest, prev = float(rows[0][1]), float(rows[1][1])
                if prev > 0:
                    return (latest / prev - 1.0) * 100.0, "db"
    except Exception:
        pass
    return 0.0, "db_missing"

def get_color_style(value):
    if not isinstance(value, (int, float)) or pd.isna(value): return ""
    if value > 0: return "color: #d32f2f; font-weight: bold;"
    if value < 0: return "color: #1b5e20; font-weight: bold;"
    return "color: #333;"

def get_premium_color(value):
    if not isinstance(value, (int, float)) or pd.isna(value): return "color:#000;"
    if value >= 5: return "color: #FF0000; font-weight: bold;"
    if value >= 1: return "color: #FF4500; font-weight: bold;"
    if value > -1: return "color: #2E8B57; font-weight: bold;"
    return "color: #006400; font-weight: bold;"

def load_jsl_data():
    db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
    csv_file = os.path.join(os.path.dirname(__file__), "fund_list.csv")
    
    try:
        df_funds = pd.read_csv(csv_file, dtype=str)
    except:
        return {}
    
    grouped_data = {}
    all_symbols = set(["fx_hkdcny"])

    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        _ensure_quotes_table(conn)
        
        for _, row in df_funds.iterrows():
            category = str(row.get('分类', row.get('类别', row.get('基金类型', row.iloc[0])))).strip()
            code = str(row.get('code', row.get('基金代码', row.iloc[1] if len(row)>1 else ''))).strip()
            name = str(row.get('name', row.get('基金名称', row.iloc[2] if len(row)>2 else ''))).strip()
            
            if not code or code == 'nan': continue
            if category not in grouped_data: grouped_data[category] = []
                
            idx_code = row.get('相关指数代码', row.get('指数代码', '-'))
            idx_name = row.get('相关指数名称', row.get('相关指数', row.get('指数名称', '-')))
            pos_ratio = _parse_position_ratio(row.get('仓位比例', row.get('仓位', '95%')))
            
            purchase_fee = str(row.get('申购费', '-')).strip()
            purchase_status = str(row.get('申购状态', '-')).strip()
            redemption_fee = str(row.get('赎回费', '-')).strip()
            redemption_status = str(row.get('赎回状态', '-')).strip()
            
            if purchase_fee.lower() == 'nan': purchase_fee = '-'
            if purchase_status.lower() == 'nan': purchase_status = '-'
            if redemption_fee.lower() == 'nan': redemption_fee = '-'
            if redemption_status.lower() == 'nan': redemption_status = '-'
            
            price_df = pd.read_sql("SELECT date, price, volume FROM fund_history WHERE fund_code=? AND price IS NOT NULL ORDER BY date DESC LIMIT 2", conn, params=(code,))
            nav_only_df = pd.read_sql("SELECT date, nav FROM fund_history WHERE fund_code=? AND nav IS NOT NULL ORDER BY date DESC LIMIT 1", conn, params=(code,))
            shares_only_df = pd.read_sql("SELECT date, shares, volume FROM fund_history WHERE fund_code=? AND shares IS NOT NULL ORDER BY date DESC LIMIT 2", conn, params=(code,))
            
            info = {
                'code': code, 'name': name, 'idx_code': idx_code, 'idx_name': idx_name,
                'pos_ratio': pos_ratio, 'category': category,
                'price': '-', 'change_pct': '-', 'turnover_amt': '-', 'shares_10k': '-',
                'added_shares': '-', 'turnover_rate': '-', 'est_price': '-', 'premium': '-',
                'rt_premium': '-', 'rt_source': 'static_db', 'nav': '-', 'nav_date': '-',
                'idx_price': '-', 'idx_change_pct': '-',
                'purchase_fee': purchase_fee, 'purchase_status': purchase_status,
                'redemption_fee': redemption_fee, 'redemption_status': redemption_status
            }
            
            if not price_df.empty:
                t_row = price_df.iloc[0]
                if pd.notna(t_row['price']):
                    info['price'] = float(t_row['price'])
                if pd.notna(t_row['price']) and pd.notna(t_row['volume']):
                    info['turnover_amt'] = (float(t_row['price']) * float(t_row['volume'])) / 10000
                if len(price_df) > 1 and pd.notna(t_row['price']) and pd.notna(price_df.iloc[1]['price']) and float(price_df.iloc[1]['price']) > 0:
                    info['change_pct'] = (float(t_row['price']) / float(price_df.iloc[1]['price']) - 1) * 100
            
            if not nav_only_df.empty:
                t_nav = nav_only_df.iloc[0]
                if pd.notna(t_nav['nav']):
                    info['nav'] = float(t_nav['nav'])
                    info['nav_date'] = t_nav['date']
            
            if not shares_only_df.empty:
                t_shares = shares_only_df.iloc[0]
                if pd.notna(t_shares['shares']) and float(t_shares['shares']) > 0:
                    info['shares_10k'] = float(t_shares['shares'])
                    if pd.notna(t_shares['volume']) and float(t_shares['volume']) > 0:
                        vol_10k = float(t_shares['volume']) / 10000
                        info['turnover_rate'] = (vol_10k / info['shares_10k']) * 100
                if len(shares_only_df) > 1 and pd.notna(t_shares['shares']) and pd.notna(shares_only_df.iloc[1]['shares']):
                    info['added_shares'] = float(t_shares['shares']) - float(shares_only_df.iloc[1]['shares'])
            
            if info['price'] != '-' and info['nav'] != '-' and float(info['nav']) > 0:
                info['premium'] = (float(info['price']) / float(info['nav']) - 1) * 100
            
            grouped_data[category].append(info)
    
    # 从数据库读取历史指数数据，不发起任何网络请求
    quote_map = {}
    hkd_pct, hkd_source = _get_exchange_rate_mid_pct_from_db("hkd")
    usd_pct, usd_source = _get_exchange_rate_mid_pct_from_db("usd")
    quote_map["fx_hkdcny"] = {"pct_change": hkd_pct}
    quote_map["fx_usdcny"] = {"pct_change": usd_pct}

    for _, funds in grouped_data.items():
        for fund in funds:
            fund['est_price'] = '静态版不计算实时估值'
            fund['rt_premium'] = '-'
            fund['idx_price'] = '静态展示'
            fund['idx_change_pct'] = '-'
    
    return grouped_data

def _load_fund_meta():
    csv_file = os.path.join(os.path.dirname(__file__), "fund_list.csv")
    try:
        df = pd.read_csv(csv_file, dtype=str)
        meta = {}
        for _, row in df.iterrows():
            code = str(row.get('code', row.get('基金代码', row.iloc[1] if len(row) > 1 else ''))).strip()
            if code and code != 'nan':
                meta[code] = {
                    "category": str(row.get('分类', row.iloc[0] if len(row) > 0 else '-')).strip(),
                    "name": str(row.get('name', row.iloc[2] if len(row) > 2 else code)).strip()
                }
        return meta
    except Exception:
        return {}

def load_fund_history(fund_code, limit=30):
    db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        df = pd.read_sql("""
            SELECT date, MAX(price) AS price, MAX(nav) AS nav, MAX(volume) AS volume, MAX(shares) AS shares
            FROM fund_history WHERE fund_code = ? GROUP BY date ORDER BY date DESC LIMIT ?
        """, conn, params=(fund_code, limit))
    rows = []
    for _, row in df.iterrows():
        date = row["date"]
        price, nav, volume, shares = row["price"], row["nav"], row["volume"], row["shares"]
        premium = (float(price)/float(nav)-1)*100 if pd.notna(price) and pd.notna(nav) and float(nav)>0 else None
        turnover_amt = (float(price)*float(volume))/10000 if pd.notna(price) and pd.notna(volume) else None
        rows.append({
            "date": date, "price": float(price) if pd.notna(price) else None,
            "index_close": None, "nav_date": date, "nav": float(nav) if pd.notna(nav) else None,
            "static_valuation": None, "premium": premium, "turnover_amt": turnover_amt,
            "shares_10k": float(shares) if pd.notna(shares) else None,
            "added_shares": None, "shares_change_pct": None
        })
    return rows

# ===================== 前端页面完全和你原来一样 =====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>静态展示版-广益录基金数据</title>
    <style>
        body { font-family: 'Arial', 'Microsoft YaHei', sans-serif; background-color: #f7f8fa; margin: 20px; font-size: 13px;}
        .header-bar { display: flex; align-items: center; justify-content: center; gap: 30px; width: 100%; margin-bottom: 20px; padding: 10px 15px; background: #fff; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
        .header-title { font-size: 20px; font-weight: bold; color: #1a237e;}
        .clock { font-size: 14px; color: #666;}
        .refresh-btn { padding: 6px 12px; background: #2196f3; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px;}
        .refresh-btn:hover { background: #1976d2;}
        .tabs { display: flex; border-bottom: 2px solid #ddd; margin-bottom: 20px;}
        .tab { padding: 10px 20px; background: #f5f5f5; border: 1px solid #ddd; border-bottom: none; cursor: pointer; font-size: 14px; font-weight: 500; border-radius: 4px 4px 0 0; margin-right: 5px;}
        .tab.active { background: #fff; color: #2196f3; border-color: #2196f3;}
        .tab:hover { background: #e8f4fc;}
        .tab-content { display: none;}
        .tab-content.active { display: block;}
        .jsl-table { width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
        .jsl-table th { background: #aed6f1; color: #1a237e; font-weight: 700; padding: 8px 4px; border: 1px solid #64b5f6; text-align: right; white-space: nowrap; font-size: 12px; cursor: pointer; }
        .jsl-table th:hover { background: #90caf9; }
        .jsl-table td { padding: 6px 4px; border: 1px solid #ddd; text-align: right; font-size: 12px; }
        .jsl-table th:nth-child(1), .jsl-table th:nth-child(2),
        .jsl-table td:nth-child(1), .jsl-table td:nth-child(2) { text-align: left; }
        .jsl-table tr:hover { background-color: #f5f9ff; }
        .code-text { color: #0056b3; text-decoration: none; font-weight: bold;}
        .jsl-table th::after { content: ' ↕'; font-size: 10px; color: #64b5f6; }
        .jsl-table th.sort-asc::after { content: ' ↑'; color: #1a237e; }
        .jsl-table th.sort-desc::after { content: ' ↓'; color: #1a237e; }
    </style>
</head>
<body>
    <div class="header-bar">
        <span class="header-title">📊 静态展示版 - 广益录基金数据</span>
        <span id="live-clock" class="clock"></span>
        <span style="color:#666; font-size:12px;">💡 数据每日自动更新</span>
        <button class="refresh-btn" onclick="location.reload();">🔄 重新加载</button>
    </div>
    <script>
        function updateClock() { document.getElementById('live-clock').textContent = new Date().toLocaleString('zh-CN'); }
        updateClock(); setInterval(updateClock, 1000);
    </script>
    <div class="tabs">
        {% for category_name in data.keys() %}
        <div class="tab {% if loop.first %}active{% endif %}" onclick="showTab('tab-{{ loop.index0 }}')">{{ category_name }}</div>
        {% endfor %}
    </div>
    {% for category_name, fund_list in data.items() %}
    <div id="tab-{{ loop.index0 }}" class="tab-content {% if loop.first %}active{% endif %}">
        <table class="jsl-table" id="table-{{ loop.index0 }}">
            <thead>
                <tr>
                    <th onclick="sortTable({{ loop.index0 }}, 0)">基金代码</th>
                    <th onclick="sortTable({{ loop.index0 }}, 1)">基金名称</th>
                    <th onclick="sortTable({{ loop.index0 }}, 2)">现价</th>
                    <th onclick="sortTable({{ loop.index0 }}, 3)">涨幅</th>
                    <th onclick="sortTable({{ loop.index0 }}, 4)">成交(万元)</th>
                    <th onclick="sortTable({{ loop.index0 }}, 5)">场内份额</th>
                    <th onclick="sortTable({{ loop.index0 }}, 6)">静态折溢价</th>
                    <th onclick="sortTable({{ loop.index0 }}, 7)">净值</th>
                    <th onclick="sortTable({{ loop.index0 }}, 8)">净值日期</th>
                </tr>
            </thead>
            <tbody>
                {% for fund in fund_list %}
                <tr>
                    <td><a href="/fund/{{ fund.code }}" target="_blank" class="code-text">{{ fund.code }}</a></td>
                    <td>{{ fund.name }}</td>
                    <td style="{{ get_color_style(fund.change_pct) }}" data-value="{{ fund.price if fund.price != '-' else '' }}">{{ "%.3f"|format(fund.price) if fund.price != '-' else '-' }}</td>
                    <td style="{{ get_color_style(fund.change_pct) }}" data-value="{{ fund.change_pct if fund.change_pct != '-' else '' }}">{{ "%.2f"|format(fund.change_pct) ~ '%' if fund.change_pct != '-' else '-' }}</td>
                    <td data-value="{{ fund.turnover_amt if fund.turnover_amt != '-' else '' }}">{{ "%.2f"|format(fund.turnover_amt) if fund.turnover_amt != '-' else '-' }}</td>
                    <td data-value="{{ fund.shares_10k if fund.shares_10k != '-' else '' }}">{{ "%.2f"|format(fund.shares_10k) if fund.shares_10k != '-' else '-' }}</td>
                    <td style="{{ get_premium_color(fund.premium) }}" data-value="{{ fund.premium if fund.premium != '-' else '' }}">{{ "%.2f"|format(fund.premium) ~ '%' if fund.premium != '-' else '-' }}</td>
                    <td data-value="{{ fund.nav if fund.nav != '-' else '' }}">{{ "%.4f"|format(fund.nav) if fund.nav != '-' else '-' }}</td>
                    <td style="color:#666">{{ fund.nav_date[-5:] if fund.nav_date != '-' else '-' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endfor %}
    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector('.tab[onclick="showTab(\\''+tabId+'\\')"]').classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }
        
        // 表格排序功能
        function sortTable(tableIndex, colIndex) {
            var table = document.getElementById('table-' + tableIndex);
            var tbody = table.tBodies[0];
            var rows = Array.from(tbody.rows);
            var th = table.tHead.rows[0].cells[colIndex];
            
            // 切换排序方向
            var sortAsc = !th.classList.contains('sort-asc');
            
            // 移除所有排序状态
            table.tHead.rows[0].querySelectorAll('th').forEach(function(h) {
                h.classList.remove('sort-asc', 'sort-desc');
            });
            
            // 设置当前列排序状态
            if (sortAsc) {
                th.classList.add('sort-asc');
            } else {
                th.classList.add('sort-desc');
            }
            
            // 排序
            rows.sort(function(a, b) {
                var valA = a.cells[colIndex].getAttribute('data-value') || a.cells[colIndex].textContent.trim();
                var valB = b.cells[colIndex].getAttribute('data-value') || b.cells[colIndex].textContent.trim();
                
                // 尝试数字排序
                var numA = parseFloat(valA);
                var numB = parseFloat(valB);
                
                if (!isNaN(numA) && !isNaN(numB)) {
                    return sortAsc ? numA - numB : numB - numA;
                }
                
                // 字符串排序
                return sortAsc ? valA.localeCompare(valB, 'zh-CN') : valB.localeCompare(valA, 'zh-CN');
            });
            
            // 重新插入排序后的行
            rows.forEach(function(row) {
                tbody.appendChild(row);
            });
        }
    </script>
</body>
</html>
"""

HISTORY_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>历史数据</title>
    <style>
        body { font-family: Arial, Microsoft YaHei; background:#f7f8fa; margin:20px; font-size:13px; }
        .jsl-table { width:100%; border-collapse:collapse; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,0.1); }
        .jsl-table th { background:#aed6f1; color:#1a237e; padding:8px 4px; border:1px solid #64b5f6; text-align:center; }
        .jsl-table td { padding:6px 4px; border:1px solid #ddd; text-align:right; }
    </style>
</head>
<body>
    <h3>{{ fund_code }} {{ fund_name }} 历史数据</h3>
    <table class="jsl-table">
        <tr><th>日期</th><th>价格</th><th>净值</th><th>溢价率</th><th>成交额</th></tr>
        {% for r in rows %}
        <tr>
            <td>{{ r.date }}</td>
            <td>{{ "%.3f"|format(r.price) if r.price else '-' }}</td>
            <td>{{ "%.4f"|format(r.nav) if r.nav else '-' }}</td>
            <td>{{ "%.2f"|format(r.premium) ~ '%' if r.premium else '-' }}</td>
            <td>{{ "%.2f"|format(r.turnover_amt) if r.turnover_amt else '-' }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

@app.route('/')
def index():
    data = load_jsl_data()
    return render_template_string(HTML_TEMPLATE, data=data, get_color_style=get_color_style, get_premium_color=get_premium_color)

@app.route('/fund/<fund_code>')
def fund_detail(fund_code):
    meta = _load_fund_meta()
    item = meta.get(fund_code, {"name": fund_code, "category": "-"})
    rows = load_fund_history(fund_code)
    return render_template_string(HISTORY_TEMPLATE, fund_code=fund_code, fund_name=item["name"], rows=rows)