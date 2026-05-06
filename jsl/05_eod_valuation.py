# -*- coding: utf-8 -*-
"""
计算并更新基金的静态估值
静态估值 = 前一日净值 × (1 + 仓位比例 × 指数涨跌幅)
"""
import sqlite3
import requests
import os
import sys

os.environ["NO_PROXY"] = "*"

DB_PATH = 'd:\\Study\\arbTest\\jsl\\jsl_monitor.db'

HK_SYMBOL_MAP = {
    'hsi': {'ec': 'HSI', 'prefix': '100'},
    'hscei': {'ec': 'HSCEI', 'prefix': '100'},
    'hscci': {'ec': 'HSCCI', 'prefix': '124'},  # 修正东财可能的前缀变更
    'hsmci': {'ec': 'HSMCI', 'prefix': '124'},  # 修正东财可能的前缀变更
    'hstech': {'ec': 'HSTECH', 'prefix': '124'},
    'hssi': {'ec': 'HSSI', 'prefix': '124'},
    'hsci': {'ec': 'HSCI', 'prefix': '124'},
    'hsscne': {'ec': 'HSSCNE', 'prefix': '124'},
    'hsmi': {'ec': 'HSMI', 'prefix': '124'}
}

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def fetch_index_history_from_db(conn, index_code):
    """从数据库获取指数历史数据"""
    idx_code = str(index_code).strip().lower()

    results = {}
    for sym in [idx_code.upper()]:
        cursor = conn.cursor()
        cursor.execute('SELECT date, close FROM index_history WHERE symbol = ? ORDER BY date', (sym,))
        rows = cursor.fetchall()
        if rows:
            for date, close in rows:
                results[date] = close
            break

    return results if results else None

def save_index_history_to_db(conn, index_code, results):
    """保存指数历史数据到数据库"""
    if not results:
        return

    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS index_history (
            symbol TEXT,
            date TEXT,
            close REAL,
            source TEXT,
            PRIMARY KEY (symbol, date)
        )
    ''')

    for date, close in results.items():
        cursor.execute('''
            INSERT OR REPLACE INTO index_history
            (symbol, date, close, source)
            VALUES (?, ?, ?, ?)
        ''', (index_code, date, close, 'eastmoney'))

    conn.commit()

def fetch_index_history_from_tqcenter(index_code, days=100):
    """使用通达信 tqcenter API获取全市场(A股+港股)指数历史数据"""
    idx_code = str(index_code).strip().upper()
    try:
        from tqcenter import tq
        tq.initialize(__file__)
        
        clean_sym = idx_code.split('.')[0]
        if clean_sym.isdigit():
            market_sym = f"{clean_sym}.SZ" if clean_sym.startswith('399') else f"{clean_sym}.SH"
        elif clean_sym in ['HSI', 'HSCEI', 'HSCCI', 'HSMCI', 'HSTECH', 'HSCI', 'HSSI', 'HSSCNE', 'HSMI']:
            market_sym = f"{clean_sym}.HI"
        else:
            market_sym = f"{clean_sym}.SH"
            
        df_dict = tq.get_market_data(field_list=[], stock_list=[market_sym], start_time='', end_time='', count=days, period='1d')
        
        results = {}
        if df_dict and 'Close' in df_dict and market_sym in df_dict['Close']:
            series = df_dict['Close'][market_sym].dropna()
            for date_idx, close_val in series.items():
                date_str = date_idx.strftime('%Y-%m-%d') if hasattr(date_idx, 'strftime') else str(date_idx)[:10]
                results[date_str] = float(close_val)
        tq.close()
        return results
    except Exception as e:
        print(f"Failed to get index {index_code} from tqcenter: {e}")
        try: tq.close()
        except: pass
        return None

def fetch_a_share_index_history_from_em(index_code, days=100):
    """使用东财获取A股K线作为通达信缓存为空时的兜底"""
    idx_code = str(index_code).strip()
    
    if idx_code.isdigit():
        if idx_code.startswith('399'):
            secid = f"0.{idx_code}"
        elif idx_code.startswith('000') or idx_code.startswith('001'):
            secid = f"1.{idx_code}"
        else:
            secid = f"2.{idx_code}"
    else:
        clean_code = idx_code.replace('.CSI', '')
        secid = f"2.{clean_code}"
    
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101', 'fqt': '1', 
        'beg': '20250101', 'end': '20261231',
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        if data.get('rc') == 0 and data.get('data'):
            results = {}
            for kline in data['data'].get('klines', []):
                parts = kline.split(',')
                if len(parts) >= 3:
                    results[parts[0]] = float(parts[2])
            return results
    except:
        pass
    return None

def fetch_hk_index_history_from_api(symbol, days=100):
    """使用东财K线API获取港股指数历史数据（不操作数据库）"""
    sym_lower = str(symbol).strip().lower()
    if sym_lower not in HK_SYMBOL_MAP:
        return None

    ec_info = HK_SYMBOL_MAP[sym_lower]
    ec_sym = ec_info['ec']
    prefix = ec_info['prefix']

    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': f'{prefix}.{ec_sym}',
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101',
        'fqt': '1',
        'beg': '20250101',
        'end': '20261231',
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()

        if data.get('rc') == 0 and data.get('data'):
            klines = data['data'].get('klines', [])
            results = {}
            for kline in klines:
                parts = kline.split(',')
                if len(parts) >= 3:
                    date = parts[0]
                    close = float(parts[2])
                    results[date] = close
            return results
        else:
            print(f"Failed to get HK index {symbol}: rc={data.get('rc')}")
            return None
    except Exception as e:
        print(f"Failed to get HK index {symbol}: {e}")
        return None

def get_hkd_cny_rate_history(conn, date_str):
    """从数据库获取指定日期的港币人民币中间价"""
    from datetime import datetime
    normalized_date = None
    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y%m%d']:
        try:
            dt = datetime.strptime(str(date_str), fmt)
            normalized_date = dt.strftime('%Y-%m-%d').lstrip('0').replace('-0', '-')
            break
        except:
            continue

    if not normalized_date:
        return None

    cursor = conn.cursor()
    cursor.execute('SELECT hkd_cny_mid FROM exchange_rate WHERE date = ?', (normalized_date,))
    result = cursor.fetchone()
    return result[0] if result and result[0] else None

def get_fx_rate_pct(conn, date, prev_date):
    """获取汇率变化率"""
    curr_rate = get_hkd_cny_rate_history(conn, date)
    prev_rate = get_hkd_cny_rate_history(conn, prev_date)
    if curr_rate and prev_rate and prev_rate > 0:
        return (curr_rate / prev_rate - 1) * 100
    return 0

def calculate_static_valuation():
    """计算静态估值"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT fund_code, idx_code, pos_ratio FROM fund_info')
    funds = cursor.fetchall()

    a_share_funds = []
    hk_funds = []

    for fund_code, idx_code, pos_ratio in funds:
        if not idx_code or idx_code == '-' or idx_code == '0':
            continue

        idx_code_lower = str(idx_code).strip().lower()
        if idx_code_lower in HK_SYMBOL_MAP:
            hk_funds.append((fund_code, idx_code, pos_ratio))
        elif idx_code_lower.startswith('399') or idx_code_lower.startswith('000') or idx_code_lower.startswith('001'):
            a_share_funds.append((fund_code, idx_code, pos_ratio))

    total_updated = 0

    print("=== A股指数基金 ===")
    for fund_code, idx_code, pos_ratio in a_share_funds:
        print(f"处理基金 {fund_code} ({idx_code})...")

        idx_data = fetch_index_history_from_db(conn, idx_code)

        if not idx_data:
            idx_data = fetch_index_history_from_tqcenter(idx_code, days=100)
            if not idx_data:
                print(f"   [降级] 通达信未缓存日K线，自动切回东财...")
                idx_data = fetch_a_share_index_history_from_em(idx_code, days=100)
            if idx_data:
                save_index_history_to_db(conn, idx_code, idx_data)
                idx_data = fetch_index_history_from_db(conn, idx_code)

        if not idx_data:
            print(f"   获取指数数据失败")
            continue

        cursor.execute(
            'SELECT date, nav FROM fund_history WHERE fund_code = ? AND nav IS NOT NULL ORDER BY date DESC',
            (fund_code,)
        )
        history_data = cursor.fetchall()

        if len(history_data) < 2:
            print(f"   历史数据不足")
            continue

        count = 0
        for i in range(len(history_data)):
            date, nav = history_data[i]

            if i + 1 >= len(history_data):
                continue

            prev_date, prev_nav = history_data[i + 1]

            if date not in idx_data or prev_date not in idx_data:
                continue

            idx_change_pct = (idx_data[date] / idx_data[prev_date] - 1) * 100
            # pos_ratio已经是小数形式（0.95表示95%），直接使用
            ratio = pos_ratio if pos_ratio and pos_ratio > 0 else 0.95
            static_valuation = prev_nav * (1 + ratio * idx_change_pct / 100)
            index_close = idx_data[date]

            cursor.execute(
                'UPDATE fund_history SET static_valuation = ?, index_close = ? WHERE fund_code = ? AND date = ?',
                (static_valuation, index_close, fund_code, date)
            )
            count += 1

        total_updated += count
        print(f"   已更新 {count} 条记录")

    print("\n=== 港股指数基金 ===")
    for fund_code, idx_code, pos_ratio in hk_funds:
        print(f"处理基金 {fund_code} ({idx_code})...")

        idx_data = fetch_index_history_from_db(conn, idx_code)

        if not idx_data:
            idx_data = fetch_index_history_from_tqcenter(idx_code, days=100)
            if not idx_data:
                print(f"   [降级] 通达信未缓存日K线，自动切回东财...")
                idx_data = fetch_hk_index_history_from_api(idx_code, days=100)
            if idx_data:
                save_index_history_to_db(conn, idx_code, idx_data)
                idx_data = fetch_index_history_from_db(conn, idx_code)

        if not idx_data:
            print(f"   获取指数数据失败")
            continue

        cursor.execute(
            'SELECT date, nav FROM fund_history WHERE fund_code = ? AND nav IS NOT NULL ORDER BY date DESC',
            (fund_code,)
        )
        history_data = cursor.fetchall()

        if len(history_data) < 2:
            print(f"   历史数据不足")
            continue

        count = 0
        for i in range(len(history_data)):
            date, nav = history_data[i]

            if i + 1 >= len(history_data):
                continue

            prev_date, prev_nav = history_data[i + 1]

            if date not in idx_data or prev_date not in idx_data:
                continue

            idx_change_pct = (idx_data[date] / idx_data[prev_date] - 1) * 100
            # pos_ratio已经是小数形式（0.95表示95%），直接使用
            ratio = pos_ratio if pos_ratio and pos_ratio > 0 else 0.95

            fx_change_pct = get_fx_rate_pct(conn, date, prev_date)
            static_valuation = prev_nav * (1 + ratio * (idx_change_pct + fx_change_pct) / 100)
            index_close = idx_data[date]

            cursor.execute(
                'UPDATE fund_history SET static_valuation = ?, index_close = ? WHERE fund_code = ? AND date = ?',
                (static_valuation, index_close, fund_code, date)
            )
            count += 1

        total_updated += count
        print(f"   已更新 {count} 条记录 (汇率影响: {fx_change_pct:+.3f}%)")

    conn.commit()
    conn.close()

    print(f"\n静态估值计算完成！已更新 {total_updated} 条记录")

if __name__ == '__main__':
    calculate_static_valuation()