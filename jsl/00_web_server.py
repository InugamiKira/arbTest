# -*- coding: utf-8 -*-
# jsl_monitor_server.py - version 0502完美复刻集思录风格的动态分类看板
import os
import sys
import pandas as pd
import sqlite3
import re
import contextlib
from datetime import datetime
from flask import Flask, render_template_string
import requests

# 引入缓存库防刷
from cachetools import cached, TTLCache

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

app = Flask(__name__)

# 创建一个有效期10秒的缓存池，避免自动刷新频繁拉取新浪API导致封IP
quote_cache = TTLCache(maxsize=100, ttl=10)

def _safe_float_from_em(val, divisor=100.0, default=0.0):
    """安全处理东方财富API返回的数值，防止 '-' 或空值导致程序崩溃"""
    if val in (None, '-', '', 'NaN', 'nan'):
        return default
    try:
        return float(val) / divisor
    except (ValueError, TypeError):
        return default

def _ensure_quotes_table(conn):
    """确保实时行情表存在，废弃了旧版容易出错的 ALTER TABLE 逻辑"""
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

def _normalize_index_symbol(raw_code):
    """统一使用东财格式的指数符号，港股指数添加hk前缀"""
    if raw_code is None:
        return None
    code = str(raw_code).strip().upper()  # 统一转大写
    if not code or code in ('-', 'NAN'):
        return None
    
    return code

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
    db_candidates = [
        db_local,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "arb_master.db"),
        os.path.join(os.path.dirname(__file__), "arb_master.db")
    ]
    for dbp in db_candidates:
        if not os.path.exists(dbp): continue
        try:
            with contextlib.closing(sqlite3.connect(dbp, timeout=15.0)) as conn:
                rows = conn.execute(f"""
                    SELECT date, {field_name} FROM exchange_rate WHERE {field_name} IS NOT NULL ORDER BY date DESC LIMIT 2
                """).fetchall()
                if len(rows) >= 2 and rows[0][1] and rows[1][1]:
                    latest, prev = float(rows[0][1]), float(rows[1][1])
                    if prev > 0: return (latest / prev - 1.0) * 100.0, "exchange_rate_db"
        except Exception:
            continue
    return 0.0, "exchange_rate_db_missing"

def _extract_quote_numbers(payload):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", payload or "")]

def _parse_sina_line(symbol, line):
    name_match = re.search(r'="([^,]*)', line or "")
    name = name_match.group(1) if name_match else symbol
    nums = _extract_quote_numbers(line)
    if len(nums) < 3: return None
    last_price = nums[0]
    prev_close, pct_change = None, None
    if symbol.startswith("s_") and len(nums) >= 3:
        pct_change = nums[2]
    elif symbol.startswith("gb_"):
        payload = (line or "").split('"')
        fields = payload[1].split(",") if len(payload) > 1 else []
        if len(fields) >= 3:
            try:
                last_price, pct_change = float(fields[1]), float(fields[2])
                if len(fields) > 26 and fields[26]: prev_close = float(fields[26])
            except Exception: pass
    elif symbol.startswith("hk") and len(nums) >= 5:
        last_price, prev_close, pct_change = nums[1], nums[2], nums[4]
    elif symbol.startswith("int_") and len(nums) >= 3:
        pct_change = nums[2]
    else:
        if len(nums) >= 3 and nums[0] != 0: pct_change = (nums[1] / nums[0]) * 100
        elif len(nums) >= 2: pct_change = nums[1]
        
    if prev_close is None and pct_change is not None and last_price:
        prev_close = last_price / (1 + pct_change / 100.0)
    return {"symbol": symbol, "name": name, "last_price": last_price, "prev_close": prev_close, "pct_change": pct_change, "source": "sina"}

def _fetch_realtime_quotes(conn, symbols):
    clean_symbols = [s for s in {_normalize_index_symbol(x) for x in symbols} if s]
    if not clean_symbols: return {}
    url = "https://hq.sinajs.cn/list=" + ",".join(clean_symbols)
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
    quotes = {}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.encoding = "gbk"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for line in resp.text.splitlines():
            m = re.search(r"var hq_str_([^=]+)=", line)
            if not m: continue
            symbol = m.group(1).strip()
            parsed = _parse_sina_line(symbol, line)
            if not parsed: continue
            quotes[symbol] = parsed
            conn.execute("""
                INSERT INTO index_realtime_quotes
                (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'sina', ?)
                ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
                pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
            """, (symbol, parsed["name"], parsed["last_price"], parsed["prev_close"], parsed["pct_change"], now_str, now_str))
        conn.commit()
    except Exception:
        pass
    return quotes

# 新浪API请求间隔控制（反爬机制）
import time
_last_sina_request_time = 0
_sina_request_interval = 20  # 新浪请求最小间隔（秒）

def _fetch_lof_realtime_prices(conn, fund_codes):
    """从新浪财经获取LOF基金实时价格（带反爬间隔控制）"""
    global _last_sina_request_time
    
    # LOF基金在深交所上市，格式为 s_sz + 基金代码
    sina_symbols = [f"s_sz{code}" for code in fund_codes if code and code.isdigit()]
    if not sina_symbols: return {}
    
    # 反爬控制：确保请求间隔至少20秒
    current_time = time.time()
    time_since_last_request = current_time - _last_sina_request_time
    if time_since_last_request < _sina_request_interval:
        time.sleep(_sina_request_interval - time_since_last_request)
    
    _last_sina_request_time = time.time()
    
    # 分批请求，每批最多20个基金
    batch_size = 20
    prices = {}
    
    for i in range(0, len(sina_symbols), batch_size):
        batch = sina_symbols[i:i+batch_size]
        url = "https://hq.sinajs.cn/list=" + ",".join(batch)
        headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            resp.encoding = "gbk"
            for line in resp.text.splitlines():
                m = re.search(r"var hq_str_s_sz(\d{6})=\"(.*?)\";", line)
                if not m: continue
                
                fund_code = m.group(1)
                data = m.group(2).split(",")
                
                if len(data) >= 9:
                    try:
                        price = float(data[3])  # 最新价
                        prev_close = float(data[2])  # 昨收
                        change_pct = (price / prev_close - 1) * 100
                        volume = float(data[8])  # 成交量（股）
                        
                        prices[fund_code] = {
                            "price": price,
                            "prev_close": prev_close,
                            "change_pct": change_pct,
                            "volume": volume
                        }
                    except Exception:
                        continue
            
            # 批次之间也添加间隔
            if i + batch_size < len(sina_symbols):
                time.sleep(5)
                
        except Exception as e:
            # 单个批次失败不影响其他批次
            continue
    
    return prices

def _parse_tencent_line(line):
    m = re.search(r'^v_([^=]+)="(.*)";$', (line or "").strip())
    if not m: return None, None
    symbol = m.group(1).strip()
    payload = m.group(2).strip()
    if not payload: return symbol, None
    return symbol, payload.split("~")

def _fetch_tencent_hk_quotes(conn, symbols):
    req_symbols = [s for s in symbols if s and s.startswith("hk")]
    if not req_symbols: return {}
    tencent_symbols = ["r_" + s for s in req_symbols]
    url = "https://qt.gtimg.cn/q=" + ",".join(tencent_symbols)
    quotes = {}
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=8)
        resp.encoding = "gbk"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for line in resp.text.splitlines():
            key, parts = _parse_tencent_line(line)
            if not key or not parts or len(parts) < 6: continue
            symbol = key[2:] if key.startswith("r_") else key
            name = parts[1] or symbol
            last_price = float(parts[3]) if parts[3] else None
            prev_close = float(parts[4]) if parts[4] else None
            if not last_price or not prev_close: continue
            pct_change = (last_price / prev_close - 1.0) * 100.0
            quotes[symbol] = {"symbol": symbol, "name": name, "last_price": last_price, "prev_close": prev_close, "pct_change": pct_change, "source": "tencent"}
            conn.execute("""
                INSERT INTO index_realtime_quotes
                (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'tencent', ?)
                ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
                pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
            """, (symbol, name, last_price, prev_close, pct_change, now_str, now_str))
        conn.commit()
    except Exception:
        pass
    return quotes

def _convert_a_index_to_secid(index_code):
    index_code = str(index_code).strip()
    if not index_code or index_code in ('-', 'nan', '0'):
        return None
    if re.match(r'^399\d{3,6}$', index_code):
        return f"0.{index_code}"
    elif re.match(r'^000\d{3,6}$', index_code) or re.match(r'^001\d{3,6}$', index_code):
        return f"1.{index_code}"
    elif re.match(r'^\d{6}$', index_code):
        if index_code.startswith('399'):
            return f"0.{index_code}"
        else:
            return f"1.{index_code}"
    return None

def _fetch_eastmoney_a_index(conn, index_code):
    # 直接使用东财格式
    idx_code = str(index_code).strip()
    
    secid = _convert_a_index_to_secid(idx_code)
    if not secid:
        return None
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f43,f60,f169,f170"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}, timeout=8)
        try:
            data = resp.json().get("data")
        except ValueError:
            return None
        if not data:
            return None
        name = data.get("f58", idx_code)
        last_raw = data.get("f43")
        prev_raw = data.get("f60")
        pct_raw = data.get("f170")
        
        last_price = _safe_float_from_em(last_raw)
        prev_close = _safe_float_from_em(prev_raw)
        if pct_raw not in (None, '-', ''):
            pct_change = _safe_float_from_em(pct_raw)
        else:
            pct_change = ((last_price / prev_close - 1) * 100) if prev_close > 0 else 0.0
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO index_realtime_quotes
            (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'eastmoney_a', ?)
            ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
            pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
        """, (index_code, name, last_price, prev_close, pct_change, now_str, now_str))
        return {"symbol": index_code, "name": name, "last_price": last_price, "prev_close": prev_close, "pct_change": pct_change, "source": "eastmoney_a"}
    except Exception:
        return None

def _fetch_eastmoney_hk_quotes(conn, symbols):
    # 使用东财SSE API获取港股指数数据
    # 港股指数映射: sina格式 -> (东财代码, 前缀)
    # 注意: 不同指数需要不同的前缀
    em_map = {
        "HSI": ("HSI", "100"),
        "HSCEI": ("HSCEI", "100"),
        "HSCCI": ("HSCCI", "100"),
        "HSMCI": ("HSMCI", "100"),
        "HSSI": ("HSSI", "124"),
        "HSTECH": ("HSTECH", "124"),
        "HSCI": ("HSCI", "124"),
        "HKHSI": ("HSI", "100"),
        "HKHSCEI": ("HSCEI", "100"),
        "HKHSCCI": ("HSCCI", "100"),
        "HKHSMCI": ("HSMCI", "100"),
        "HKHSSI": ("HSSI", "124"),
        "HKHSTECH": ("HSTECH", "124"),
        "HKHSCI": ("HSCI", "124")
    }
    req = [s for s in symbols if s in em_map]
    quotes = {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }
    
    for symbol in req:
        ec_sym, prefix = em_map[symbol]
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292',
            'secid': prefix + '.' + ec_sym,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
        }
        
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            data = resp.json()
            if data.get('rc') == 0 and data.get('data'):
                d = data['data']
                last_price = _safe_float_from_em(d.get('f43'))
                prev_close = _safe_float_from_em(d.get('f60'))
                pct_change = _safe_float_from_em(d.get('f170'))
                name = d.get('f58', symbol)
                
                quotes[symbol] = {
                    "symbol": symbol, 
                    "name": name, 
                    "last_price": last_price, 
                    "prev_close": prev_close, 
                    "pct_change": pct_change, 
                    "source": "eastmoney_sse"
                }
                
                conn.execute("""
                    INSERT INTO index_realtime_quotes
                    (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'eastmoney_sse', ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
                    pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
                """, (symbol, name, last_price, prev_close, pct_change, now_str, now_str))
        except Exception as e:
            print(f"获取港股指数{symbol}失败: {e}")
            continue
    
    conn.commit()
    return quotes

def _build_em_map_from_db(conn):
    # 从数据库动态构建东财指数映射
    # 规则：
    # - 以000/399开头的纯数字代码 → 1.xxx（A股指数）
    # - 其他代码 → 2.xxx（东财特色指数）
    em_map = {}
    
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT idx_code FROM fund_info WHERE idx_code IS NOT NULL AND idx_code != "-"')
    rows = cursor.fetchall()
    
    for row in rows:
        if not row[0]:
            continue
        idx_code = str(row[0]).strip().upper()
        if not idx_code or idx_code in ('NONE', 'NAN', '-'):
            continue
            
        # 确定secid前缀
        if idx_code.isdigit():
            if idx_code.startswith('000') or idx_code.startswith('399') or idx_code.startswith('001'):
                em_map[idx_code] = f"1.{idx_code}"
            else:
                em_map[idx_code] = f"2.{idx_code}"
        else:
            # 包含字母的代码使用2.前缀（东财特色指数）
            # 处理特殊格式如 H11136.CSI
            clean_code = idx_code.replace('.CSI', '')
            em_map[idx_code] = f"2.{clean_code}"
            # 同时添加clean_code作为key，方便查询
            if clean_code != idx_code:
                em_map[clean_code] = f"2.{clean_code}"
    
    return em_map

def _fetch_eastmoney_csi_quotes(conn, symbols):
    # 使用东财SSE API获取中证系列指数
    # 映射: symbol -> 2.symbol（统一使用东财格式）
    # 动态从数据库构建映射
    em_map = _build_em_map_from_db(conn)
    req = [s for s in symbols if s in em_map]
    quotes = {}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }

    session = requests.Session()
    session.headers.update(headers)

    for symbol in req:
        ec_sym = em_map[symbol]
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45',
            'secid': ec_sym,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
        }

        for attempt in range(3):
            try:
                resp = session.get(url, params=params, timeout=5)
                data = resp.json()
                if data.get('rc') == 0 and data.get('data'):
                    d = data['data']
                    last_price = _safe_float_from_em(d.get('f43'))
                    prev_close = _safe_float_from_em(d.get('f60'))
                    pct_change = _safe_float_from_em(d.get('f170'))
                    name = d.get('f58', symbol)

                    quotes[symbol] = {
                        "symbol": symbol,
                        "name": name,
                        "last_price": last_price,
                        "prev_close": prev_close,
                        "pct_change": pct_change,
                        "source": "eastmoney_csi"
                    }

                    conn.execute("""
                        INSERT INTO index_realtime_quotes
                        (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'eastmoney_csi', ?)
                        ON CONFLICT(symbol) DO UPDATE SET
                        name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
                        pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
                    """, (symbol, name, last_price, prev_close, pct_change, now_str, now_str))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"获取中证指数{symbol}失败: {e}")
                else:
                    time.sleep(0.2)

    conn.commit()
    session.close()
    return quotes

def _fetch_hkd_cny_pct_from_tencent(conn):
    url = "https://qt.gtimg.cn/q=whUSDCNY,whUSDHKD"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=8)
        resp.encoding = "gbk"
        fx = {}
        for line in resp.text.splitlines():
            key, parts = _parse_tencent_line(line)
            if not key or not parts or len(parts) < 8: continue
            code = key.replace("v_", "")
            last_v, prev_v = float(parts[3]) if parts[3] else None, float(parts[6]) if parts[6] else None
            if last_v and prev_v: fx[code] = (last_v, prev_v)
        if "whUSDCNY" not in fx or "whUSDHKD" not in fx: return None
        usdcny_last, usdcny_prev = fx["whUSDCNY"]
        usdhkd_last, usdhkd_prev = fx["whUSDHKD"]
        hkd_cny_last, hkd_cny_prev = usdcny_last / usdhkd_last, usdcny_prev / usdhkd_prev
        pct = (hkd_cny_last / hkd_cny_prev - 1.0) * 100.0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO index_realtime_quotes
            (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
            VALUES ('fx_hkdcny', 'HKD/CNY', ?, ?, ?, ?, 'tencent', ?)
            ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
            pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
        """, (hkd_cny_last, hkd_cny_prev, pct, now_str, now_str))
        conn.commit()
        return {"symbol": "fx_hkdcny", "name": "HKD/CNY", "last_price": hkd_cny_last, "prev_close": hkd_cny_prev, "pct_change": pct, "source": "tencent"}
    except Exception:
        return None


def get_cached_realtime_quotes(db_path, symbols_tuple):
    with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:
        symbols = list(symbols_tuple)
        
        # 构建多种格式的符号列表用于查询（支持新浪格式和纯数字格式）
        query_symbols = set()
        for s in symbols:
            if s:
                query_symbols.add(str(s).upper())
        
        query_symbols = list(query_symbols)
        
        quote_map = {}
        if not query_symbols:
            return quote_map
            
        try:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(query_symbols))
            cursor.execute(f"""
                SELECT symbol, name, last_price, prev_close, pct_change, source, updated_at 
                FROM index_realtime_quotes 
                WHERE symbol IN ({placeholders})
            """, query_symbols)
            for row in cursor.fetchall():
                symbol, name, last_price, prev_close, pct_change, source, updated_at = row
                quote_map[symbol] = {
                    "symbol": symbol, "name": name, 
                    "last_price": last_price, "prev_close": prev_close, 
                    "pct_change": pct_change, "source": source
                }
        except Exception as e:
            import logging
            logging.error(f"❌ 009读取实时指数缓存表失败: {e}")
        
        # 注意：009 现已完全纯净，不再向外部发起任何接口请求。
        # 任何缺失或过期的行情，均由后台的 003 和 004 守护进程自动轮询并写入数据库。

        # 使用数据库中的人民币中间价（符合证监会法规要求）
        hkd_pct, hkd_source = _get_exchange_rate_mid_pct_from_db("hkd")
        usd_pct, usd_source = _get_exchange_rate_mid_pct_from_db("usd")
        
        quote_map["fx_hkdcny"] = {"symbol": "fx_hkdcny", "name": "HKD/CNY", "pct_change": hkd_pct, "source": hkd_source}
        quote_map["fx_usdcny"] = {"symbol": "fx_usdcny", "name": "USD/CNY", "pct_change": usd_pct, "source": usd_source}
        return quote_map

def _get_fx_pct_for_index(index_symbol, quote_map):
    if not index_symbol: return 0.0
    index_symbol = str(index_symbol).lower()
    
    # 纯净的港股指数列表判断，不再依赖 'hk' 前缀
    hk_indices = {'hsi', 'hscei', 'hscci', 'hsmci', 'hstech', 'hsci', 'hssi', 'hsscne'}
    if index_symbol in hk_indices or index_symbol.startswith("hk"):
        fx = quote_map.get("fx_hkdcny")
        if fx and fx.get("pct_change") is not None: return float(fx["pct_change"])
    elif index_symbol.startswith("us"):
        fx = quote_map.get("fx_usdcny")
        if fx and fx.get("pct_change") is not None: return float(fx["pct_change"])
    return 0.0

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
    
    with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:
        _ensure_quotes_table(conn)
        
        for _, row in df_funds.iterrows():
            category = str(row.get('分类', row.get('类别', row.get('基金类型', row.get('基金类名', row.iloc[0]))))).strip()
            code = str(row.get('code', row.get('基金代码', row.iloc[1] if len(row)>1 else ''))).strip()
            name = str(row.get('name', row.get('基金名称', row.iloc[2] if len(row)>2 else ''))).strip()
            
            if not code or code == 'nan': continue
            if category not in grouped_data: grouped_data[category] = []
                
            idx_code = row.get('相关指数代码', row.get('指数代码', '-'))
            idx_name = row.get('相关指数名称', row.get('相关指数', row.get('指数名称', '-')))
            pos_ratio = _parse_position_ratio(row.get('仓位比例', row.get('仓位', '95%')))
            idx_symbol = _normalize_index_symbol(idx_code)
            if idx_symbol: all_symbols.add(idx_symbol)
            
            purchase_fee = str(row.get('申购费', '-')).strip()
            purchase_status = str(row.get('申购状态', '-')).strip()
            redemption_fee = str(row.get('赎回费', '-')).strip()
            redemption_status = str(row.get('赎回状态', '-')).strip()
            
            if purchase_fee.lower() == 'nan': purchase_fee = '-'
            if purchase_status.lower() == 'nan': purchase_status = '-'
            if redemption_fee.lower() == 'nan': redemption_fee = '-'
            if redemption_status.lower() == 'nan': redemption_status = '-'
            
            # 分别查询净值、份额的最新记录（不需要同一条记录同时有两者）
            price_df = pd.read_sql("SELECT date, price, volume FROM fund_history WHERE fund_code=? AND price IS NOT NULL ORDER BY date DESC LIMIT 2", conn, params=(code,))
            nav_only_df = pd.read_sql("SELECT date, nav FROM fund_history WHERE fund_code=? AND nav IS NOT NULL ORDER BY date DESC LIMIT 1", conn, params=(code,))
            shares_only_df = pd.read_sql("SELECT date, shares, volume FROM fund_history WHERE fund_code=? AND shares IS NOT NULL ORDER BY date DESC LIMIT 2", conn, params=(code,))
            
            info = {
                'code': code, 'name': name, 'idx_code': idx_code, 'idx_name': idx_name, 'idx_symbol': idx_symbol, 'pos_ratio': pos_ratio, 'category': category,
                'price': '-', 'change_pct': '-', 'turnover_amt': '-', 'shares_10k': '-', 'added_shares': '-', 'turnover_rate': '-',
                'est_price': '-', 'premium': '-', 'rt_premium': '-', 'rt_source': '-', 'nav': '-', 'nav_date': '-',
                'idx_price': '-', 'idx_change_pct': '-',  # 新增：指数价和指数涨幅
                'purchase_fee': purchase_fee, 'purchase_status': purchase_status, 'redemption_fee': redemption_fee, 'redemption_status': redemption_status
            }
            
            if not price_df.empty:
                t_row = price_df.iloc[0]
                if pd.notna(t_row['price']):
                    info['price'] = float(t_row['price'])
                
                # 【重要修正1】成交额(万元) = 成交量(份) × 现价(元/份) ÷ 10000
                # 新浪返回的volume是「份」，需要转换成万份再计算
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
    
    # TODO: 新浪实时价格获取暂时关闭（避免服务器崩溃）
    # 新浪API反爬严格，需要更完善的处理逻辑
    # all_fund_codes = []
    # for _, funds in grouped_data.items():
    #     for fund in funds:
    #         all_fund_codes.append(fund['code'])
    # lof_prices = _fetch_lof_realtime_prices(conn, all_fund_codes)
    # for _, funds in grouped_data.items():
    #     for fund in funds:
    #         if fund['code'] in lof_prices:
    #             realtime = lof_prices[fund['code']]
    #             fund['price'] = realtime['price']
    #             fund['change_pct'] = realtime['change_pct']
    #             fund['rt_source'] = 'sina_realtime'

    quote_map = get_cached_realtime_quotes(db_path, tuple(all_symbols))
    usdcny_mid_pct, usdcny_mid_src = _get_exchange_rate_mid_pct_from_db("usd")
    
    for _, funds in grouped_data.items():
        for fund in funds:
            idx_symbol = fund.get('idx_symbol')
            idx_quote = quote_map.get(idx_symbol) if idx_symbol else None
            
            # 填充指数价和指数涨幅
            if idx_quote:
                if idx_quote.get("last_price") is not None:
                    fund['idx_price'] = idx_quote["last_price"]
                if idx_quote.get("pct_change") is not None:
                    fund['idx_change_pct'] = idx_quote["pct_change"]
            
            # 只要有nav和指数就计算今日估值（不需要有price）
            if fund['nav'] == '-' or not idx_quote or idx_quote.get("pct_change") is None: continue
            
            idx_pct = float(idx_quote["pct_change"])
            if str(idx_symbol).lower().startswith("hk"):
                fx_pct = _get_fx_pct_for_index(idx_symbol, quote_map)
                fx_src = quote_map.get("fx_hkdcny", {}).get("source", "-")
            elif "qdii" in str(fund.get("category", "")).lower():
                fx_pct = usdcny_mid_pct
                fx_src = usdcny_mid_src
            else:
                fx_pct = 0.0
                fx_src = "none"
                
            combined_change = (1 + idx_pct / 100.0) * (1 + fx_pct / 100.0) - 1
            est_nav = float(fund['nav']) * (1 + float(fund.get('pos_ratio', 1.0)) * combined_change)
            fund['est_price'] = est_nav
            fund['rt_source'] = f"idx:{idx_quote.get('source', '-')}/fx:{fx_src}/pos:{float(fund.get('pos_ratio',0))*100:.0f}%"
            
            # 实时折溢价只有有price才计算
            if fund['price'] != '-' and est_nav > 0:
                fund['rt_premium'] = (float(fund['price']) / est_nav - 1) * 100

    return grouped_data


def _load_fund_meta():
    db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
    try:
        # 优先从数据库读取基金配置（包含仓位比例）
        with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:
            df = pd.read_sql("SELECT fund_code, fund_name, category, idx_code, idx_name, pos_ratio FROM fund_info", conn)
            meta = {}
            for _, row in df.iterrows():
                code = str(row['fund_code']).strip()
                if code and code != 'nan':
                    idx_symbol = _normalize_index_symbol(str(row['idx_code']))
                    meta[code] = {
                        "category": str(row['category']).strip(),
                        "name": str(row['fund_name']).strip(),
                        "idx_name": str(row['idx_name']).strip(),
                        "idx_symbol": idx_symbol,
                        "pos_ratio": float(row['pos_ratio']) if pd.notna(row['pos_ratio']) else 0.95
                    }
            return meta
    except Exception:
        # 如果数据库读取失败，回退到CSV（新格式）
        csv_file = os.path.join(os.path.dirname(__file__), "fund_list.csv")
        try:
            df = pd.read_csv(csv_file, dtype=str)
            meta = {}
            for _, row in df.iterrows():
                code = str(row.get('代码', '')).strip()
                if code and code != 'nan':
                    idx_code_raw = str(row.get('指数代码', '-')).strip()
                    idx_symbol = _normalize_index_symbol(idx_code_raw)
                    pos_ratio = _parse_position_ratio(row.get('仓位', '95%'))
                    meta[code] = {
                        "category": str(row.get('分类', '-')).strip(),
                        "name": str(row.get('名称', code)).strip(),
                        "idx_name": str(row.get('相关指数', '-')).strip(),
                        "idx_symbol": idx_symbol,
                        "pos_ratio": pos_ratio
                    }
            return meta
        except Exception:
            return {}

def _convert_to_history_symbol(symbol):
    """将指数符号转换为index_history表中的符号格式"""
    if not symbol:
        return symbol
    return str(symbol).upper()

def load_fund_history(fund_code, limit=30):
    db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
    fund_meta = _load_fund_meta()
    meta = fund_meta.get(fund_code, {})
    idx_symbol = meta.get("idx_symbol")
    pos_ratio = meta.get("pos_ratio", 0.95)
    
    # 先读取指数历史收盘价
    index_history_map = {}
    if idx_symbol:
        # 将新浪格式转换为index_history表的格式
        history_symbol = _convert_to_history_symbol(idx_symbol)
        with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:
            df_index = pd.read_sql("""
                SELECT date, close FROM index_history WHERE symbol = ? ORDER BY date
            """, conn, params=(history_symbol,))
            for _, idx_row in df_index.iterrows():
                index_history_map[idx_row["date"]] = idx_row["close"]
    
    with contextlib.closing(sqlite3.connect(db_path, timeout=15.0)) as conn:
        # 【重要修改】查询 fund_history
        df = pd.read_sql("""
            SELECT date, MAX(price) AS price, MAX(nav) AS nav, MAX(volume) AS volume, MAX(shares) AS shares
            FROM fund_history WHERE fund_code = ? GROUP BY date ORDER BY date DESC LIMIT ?
        """, conn, params=(fund_code, limit))
        
    if df.empty: return []
    rows = []
    for i in range(len(df)):
        row = df.iloc[i]
        date = row["date"]
        price, nav, volume, shares = row["price"], row["nav"], row["volume"], row["shares"]
        
        # 从index_history_map读取指数收盘价
        index_close = index_history_map.get(date)
        
        premium = (float(price) / float(nav) - 1.0) * 100.0 if pd.notna(price) and pd.notna(nav) and float(nav) > 0 else None
        
        # 计算静态估值：需要找到前一交易日的净值和指数收盘价
        static_valuation = None
        if pd.notna(nav) and pd.notna(index_close) and i + 1 < len(df):
            # 找到前一交易日的nav和index_close
            for j in range(i + 1, len(df)):
                prev_row = df.iloc[j]
                prev_date = prev_row["date"]
                prev_nav = prev_row["nav"]
                prev_index_close = index_history_map.get(prev_date)
                if pd.notna(prev_nav) and pd.notna(prev_index_close) and prev_index_close > 0:
                    # 计算静态估值
                    idx_change_pct = (index_close / prev_index_close) - 1.0
                    static_valuation = prev_nav * (1 + pos_ratio * idx_change_pct)
                    break
        
        # 【重要修正1】成交额(万元) = 成交量(份) × 现价(元/份) ÷ 10000
        turnover_amt = None
        if pd.notna(price) and pd.notna(volume):
            turnover_amt = (float(price) * float(volume)) / 10000
        
        # 深交所返回的dqgm单位已经是万份，不需要再除以10000
        shares_10k = None
        if pd.notna(shares) and float(shares) > 0:
            shares_10k = float(shares)  # 直接是万份

        added_shares, shares_change_pct = None, None
        if i + 1 < len(df) and pd.notna(shares):
            prev_shares = df.iloc[i + 1]["shares"]
            if pd.notna(prev_shares):
                added_shares = float(shares) - float(prev_shares)  # 直接是万份
                if float(prev_shares) > 0:
                    shares_change_pct = (float(shares) / float(prev_shares) - 1.0) * 100.0
                    
        rows.append({
            "date": row["date"], 
            "price": float(price) if pd.notna(price) else None,
            "index_close": float(index_close) if pd.notna(index_close) else None,
            "nav_date": row["date"] if pd.notna(nav) else "-", 
            "nav": float(nav) if pd.notna(nav) else None,
            "static_valuation": float(static_valuation) if pd.notna(static_valuation) else None,
            "premium": premium, 
            "turnover_amt": turnover_amt, 
            "shares_10k": shares_10k,
            "added_shares": added_shares, 
            "shares_change_pct": shares_change_pct
        })
    return rows

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>集思录风格基金监控</title>
    <style>
        body { font-family: 'Arial', 'Microsoft YaHei', sans-serif; background-color: #f7f8fa; margin: 20px; font-size: 13px;}
        .header-bar { display: flex; align-items: center; justify-content: center; gap: 30px; width: 100%; margin-bottom: 20px; padding: 10px 15px; background: #fff; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
        .header-title { font-size: 20px; font-weight: bold; color: #1a237e;}
        .clock { font-size: 14px; color: #666;}
        .refresh-btn { padding: 6px 12px; background: #2196f3; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px;}
        .refresh-btn:hover { background: #1976d2;}
        .auto-refresh { display: flex; align-items: center; gap: 5px;}
        .auto-refresh input { margin: 0;}
        .tabs { display: flex; border-bottom: 2px solid #ddd; margin-bottom: 20px;}
        .tab { padding: 10px 20px; background: #f5f5f5; border: 1px solid #ddd; border-bottom: none; cursor: pointer; font-size: 14px; font-weight: 500; border-radius: 4px 4px 0 0; margin-right: 5px;}
        .tab.active { background: #fff; color: #2196f3; border-color: #2196f3;}
        .tab:hover { background: #e8f4fc;}
        .tab-content { display: none;}
        .tab-content.active { display: block;}
        .jsl-table { width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1);}
        .jsl-table th { background: #aed6f1; color: #1a237e; font-weight: 700; padding: 8px 4px; border: 1px solid #64b5f6; text-align: right; white-space: nowrap; font-size: 12px; }
        .jsl-table th:hover { background: #64b5f6; }
        .jsl-table td { padding: 6px 4px; border: 1px solid #ddd; text-align: right; font-size: 12px; }
        .jsl-table th:nth-child(1), .jsl-table th:nth-child(2),
        .jsl-table td:nth-child(1), .jsl-table td:nth-child(2) { text-align: left; }
        .jsl-table tr:hover { background-color: #f5f9ff; }
        .code-text { color: #0056b3; text-decoration: none; font-weight: bold;}
        .val-dash { color: #999; }
        .status-open { color: #2E8B57; font-weight: bold;}
        .status-close { color: #d32f2f; font-weight: bold;}
        .status-limited { color: #ff9800; font-weight: bold;}
        .red-text { color: #d32f2f; }
    </style>
</head>
<body>
    <div class="header-bar">
        <span class="header-title">📊 "广益录"基金数据练习测试</span>
        <span id="live-clock" class="clock"></span>
        <button class="refresh-btn" id="refreshBtn" onclick="handleRefresh();">🔄 刷新数据</button>
    </div>
    <script>
        var lastRefreshTime = 0;
        var minRefreshInterval = 20; // 最小刷新间隔（秒）
        
        function updateClock() {
            document.getElementById('live-clock').textContent = new Date().toLocaleString('zh-CN');
        }
        updateClock();
        setInterval(updateClock, 1000);
        
        function handleRefresh() {
            var now = Date.now() / 1000;
            var elapsed = now - lastRefreshTime;
            
            if (elapsed < minRefreshInterval) {
                var remaining = Math.ceil(minRefreshInterval - elapsed);
                alert('⏳ 请稍候，距离上次刷新还有 ' + remaining + ' 秒');
                return;
            }
            
            lastRefreshTime = now;
            var btn = document.getElementById('refreshBtn');
            btn.innerHTML = '⏳ 刷新中...';
            btn.disabled = true;
            
            location.reload();
        }
    </script>

    <div class="tabs">
        {% for category_name in data.keys() %}
        <div class="tab {% if loop.first %}active{% endif %}" onclick="showTab('tab-{{ loop.index0 }}')">{{ category_name }}</div>
        {% endfor %}
    </div>

    {% for category_name, fund_list in data.items() %}
    <div id="tab-{{ loop.index0 }}" class="tab-content {% if loop.first %}active{% endif %}">
        <table class="jsl-table" data-sort-asc="true">
            <thead>
                <tr>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 0)">基金代码 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 1)">基金名称 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 2)">现价 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 3)">涨幅 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 4)">成交(万元) ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 5)">场内份额<br/>(万份) ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 6)">场内新增<br/>(万份) ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 7)">换手率 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 8)">今日估值 ▼</th>
                    <th style="text-align:center;cursor:pointer;" class="red-text" onclick="sortTable({{ loop.index0 }}, 10)">实时折溢价 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 11)">T-2/T-1净值 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 12)">净值日期 ▼</th>
                    <th style="text-align:center;cursor:pointer;" class="red-text" onclick="sortTable({{ loop.index0 }}, 9)">静态折溢价 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 13)">指数价 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 14)">指数涨幅 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 15)">指数代码 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 16)">指数名称 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 17)">申购费 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 18)">申购状态 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 19)">赎回费 ▼</th>
                    <th style="text-align:center;cursor:pointer;" onclick="sortTable({{ loop.index0 }}, 20)">赎回状态 ▼</th>
                </tr>
            </thead>
            <tbody>
                {% for fund in fund_list %}
                <tr>
                    <td><a href="/fund/{{ fund.code }}" target="_blank" class="code-text">{{ fund.code }}</a></td>
                    <td>{{ fund.name }}</td>
                    <td style="{{ get_color_style(fund.change_pct) }}">{{ "%.3f"|format(fund.price) if fund.price != '-' else '-' }}</td>
                    <td style="{{ get_color_style(fund.change_pct) }}">{{ "%.2f"|format(fund.change_pct) ~ '%' if fund.change_pct != '-' else '-' }}</td>
                    <td>{{ "%.2f"|format(fund.turnover_amt) if fund.turnover_amt != '-' else '-' }}</td>
                    <td>{{ "%.2f"|format(fund.shares_10k) if fund.shares_10k != '-' else '-' }}</td>
                    <td style="{{ get_color_style(fund.added_shares) }}">{{ "%+.2f"|format(fund.added_shares) if fund.added_shares != '-' else '-' }}</td>
                    <td>{{ "%.2f"|format(fund.turnover_rate) ~ '%' if fund.turnover_rate != '-' else '-' }}</td>
                    <td>{{ "%.4f"|format(fund.est_price) if fund.est_price != '-' else '-' }}</td>
                    <td style="{{ get_premium_color(fund.rt_premium) }}">
                        {{ "%.2f"|format(fund.rt_premium) ~ '%' if fund.rt_premium != '-' else '-' }}
                    </td>
                    <td>{{ "%.4f"|format(fund.nav) if fund.nav != '-' else '-' }}</td>
                    <td style="color:#666; font-size:11px;">{{ fund.nav_date[-5:] if fund.nav_date != '-' else '-' }}</td>
                    <td style="{{ get_premium_color(fund.premium) }}">{{ "%.2f"|format(fund.premium) ~ '%' if fund.premium != '-' else '-' }}</td>
                    <td style="{{ get_color_style(fund.idx_change_pct) }}">{{ "%.3f"|format(fund.idx_price) if fund.idx_price != '-' else '-' }}</td>
                    <td style="{{ get_color_style(fund.idx_change_pct) }}">{{ "%.2f"|format(fund.idx_change_pct) ~ '%' if fund.idx_change_pct != '-' else '-' }}</td>
                    <td style="color:#666;">{{ fund.idx_code }}</td>
                    <td style="color:#666;">{{ fund.idx_name }}</td>
                    <td>{{ fund.purchase_fee if fund.purchase_fee != '-' else '-' }}</td>
                    <td>
                        {% if '开放' in fund.purchase_status %}<span class="status-open">{{ fund.purchase_status }}</span>
                        {% elif '暂停' in fund.purchase_status %}<span class="status-close">{{ fund.purchase_status }}</span>
                        {% elif '限' in fund.purchase_status %}<span class="status-limited">{{ fund.purchase_status }}</span>
                        {% else %}{{ fund.purchase_status }}{% endif %}
                    </td>
                    <td>{{ fund.redemption_fee if fund.redemption_fee != '-' else '-' }}</td>
                    <td>
                        {% if '开放' in fund.redemption_status %}<span class="status-open">{{ fund.redemption_status }}</span>
                        {% elif '暂停' in fund.redemption_status %}<span class="status-close">{{ fund.redemption_status }}</span>
                        {% elif '限' in fund.redemption_status %}<span class="status-limited">{{ fund.redemption_status }}</span>
                        {% else %}{{ fund.redemption_status }}{% endif %}
                    </td>
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
            document.querySelector('.tab[onclick="showTab(\\'' + tabId + '\\')"]').classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }
        
        function sortTable(tabIndex, colIndex) {
            const table = document.querySelectorAll('.tab-content table')[tabIndex];
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const header = table.querySelector('thead tr th');
            
            const isAsc = table.getAttribute('data-sort-asc') === 'true';
            
            rows.sort((a, b) => {
                const aVal = a.cells[colIndex].textContent.trim();
                const bVal = b.cells[colIndex].textContent.trim();
                
                const aNum = parseFloat(aVal.replace(/[%+,\s]/g, ''));
                const bNum = parseFloat(bVal.replace(/[%+,\s]/g, ''));
                
                if (!isNaN(aNum) && !isNaN(bNum)) {
                    return isAsc ? aNum - bNum : bNum - aNum;
                }
                return isAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            });
            
            rows.forEach(row => tbody.appendChild(row));
            table.setAttribute('data-sort-asc', !isAsc);
        }
    </script>

    <div style="margin-top: 20px; padding: 15px; background: #fff; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-size: 12px; color: #666;">
        <strong>📊 数据来源说明：</strong>
        <br>• 指数数据：东方财富(eastmoney)、腾讯(tencent)、新浪(sina)
        <br>• 汇率数据：人民币汇率中间价（央行官方数据，符合证监会法规要求）
        <br>• 场内份额：深交所官方API(SZSE)
        <br>• 基金净值与价格：新浪财经、集思录
        <br>• 实时估值公式：基准日净值 × [1 + 仓位比例 × (指数涨跌幅) × (汇率涨跌幅)]
    </div>

</body>
</html>
"""

HISTORY_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ fund_code }} {{ fund_name }} 历史数据</title>
    <style>
        body { font-family: 'Arial', 'Microsoft YaHei', sans-serif; background:#f7f8fa; margin:20px; font-size:13px; }
        .crumb { margin-bottom:12px; color:#666; }
        .title { font-size:24px; font-weight:700; margin:0 0 14px 0; color:#1f2937; }
        .jsl-table { width:100%; border-collapse:collapse; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,0.1); }
        .jsl-table th { background:#aed6f1; color:#1a237e; font-weight:700; padding:8px 4px; border:1px solid #64b5f6; text-align:center; white-space:nowrap; font-size:12px; }
        .jsl-table td { padding:6px 4px; border:1px solid #ddd; text-align:right; }
        .jsl-table td:nth-child(1), .jsl-table td:nth-child(3) { text-align:center; }
        .red { color:#d32f2f; font-weight:bold; }
        .green { color:#1b5e20; font-weight:bold; }
        .orange { color:#f57c00; font-weight:bold; }
    </style>
</head>
<body>
    <div class="crumb">首页 >> {{ category }} >> {{ fund_name }}</div>
    <h1 class="title">{{ fund_code }} {{ fund_name }} 历史数据（最近30个交易日）</h1>
    <table class="jsl-table">
        <thead>
            <tr>
                <th>价格日期</th>
                <th>收盘价</th>
                <th>指数收盘价</th>
                <th>净值日期</th>
                <th>净值</th>
                <th>静态估值</th>
                <th>估值误差</th>
                <th>溢价率</th>
                <th>成交额(万元)</th>
                <th>场内份额(万份)</th>
                <th>场内新增(万份)</th>
                <th>份额涨幅</th>
            </tr>
        </thead>
        <tbody>
            {% for r in rows %}
            <tr>
                <td>{{ r.date }}</td>
                <td>{{ "%.3f"|format(r.price) if r.price is not none else "-" }}</td>
                <td>{{ "%.2f"|format(r.index_close) if r.index_close is not none else "-" }}</td>
                <td>{{ r.nav_date }}</td>
                <td>{{ "%.4f"|format(r.nav) if r.nav is not none else "-" }}</td>
                <td>{{ "%.4f"|format(r.static_valuation) if r.static_valuation is not none else "-" }}</td>
                <td>{% if r.static_valuation is not none and r.nav is not none and r.nav > 0 %}
                    {% set error = (r.static_valuation - r.nav) / r.nav * 100 %}
                    <span class="{{ 'green' if error >= -0.5 and error <= 0.5 else 'orange' if error >= -1 and error <= 1 else 'red' }}">
                        {{ "%+.2f"|format(error) }}%
                    </span>
                    {% else %}-{% endif %}
                </td>
                <td class="{{ 'red' if (r.premium is not none and r.premium >= 0) else 'green' }}">{{ "%.2f"|format(r.premium) ~ '%' if r.premium is not none else "-" }}</td>
                <td>{{ "%.2f"|format(r.turnover_amt) if r.turnover_amt is not none else "-" }}</td>
                <td>{{ "%.0f"|format(r.shares_10k) if r.shares_10k is not none else "-" }}</td>
                <td class="{{ 'red' if (r.added_shares is not none and r.added_shares >= 0) else 'green' }}">{{ "%+.0f"|format(r.added_shares) if r.added_shares is not none else "-" }}</td>
                <td class="{{ 'red' if (r.shares_change_pct is not none and r.shares_change_pct >= 0) else 'green' }}">{{ "%.3f"|format(r.shares_change_pct) ~ '%' if r.shares_change_pct is not none else "-" }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

@app.route('/')
def index():
    grouped_data = load_jsl_data()
    return render_template_string(HTML_TEMPLATE, data=grouped_data, get_color_style=get_color_style, get_premium_color=get_premium_color)

@app.route('/fund/<fund_code>')
def fund_detail(fund_code):
    meta = _load_fund_meta()
    item = meta.get(fund_code, {"name": fund_code, "category": "-", "idx_name": "-"})
    rows = load_fund_history(fund_code, limit=30)
    return render_template_string(
        HISTORY_TEMPLATE,
        fund_code=fund_code,
        fund_name=item.get("name", fund_code),
        category=item.get("category", "-"),
        rows=rows
    )

def _auto_update_exchange_rates():
    """自动更新汇率数据（使用arbcore的函数，每天只爬取一次）"""
    print("\n=== 自动更新汇率数据 ===")
    
    try:
        # 添加arbcore路径
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        from arbcore.database.db_manager import DatabaseManager
        
        today = datetime.now().date().strftime('%Y-%m-%d')
        
        # 使用统一的数据库管理器
        db_manager = DatabaseManager()
        
        # 检查今天是否已经爬取过汇率数据
        if db_manager.is_access_synced_today(today, 'exchange_rate'):
            print(f"✅ 今日({today})汇率数据已更新，跳过爬取")
            return
        
        from arbcore.fetchers.data_fetcher import data_fetcher
        from arbcore.fetchers.woody_web_crawler import WoodyWebCrawler
        
        woody_crawler = WoodyWebCrawler()
        
        # 获取官方中间价
        official_rate = data_fetcher.fetch_official_exchange_rate()
        usd_cny_mid = official_rate.get('人民币中间价') if official_rate else None
        
        # 从Woody网页获取备用数据
        woody_rates = woody_crawler.get_woody_exchange_rates()
        if woody_rates and 'USCNY' in woody_rates:
            usd_cny_mid = woody_rates['USCNY']['rate']
        
        if usd_cny_mid:
            # 计算港币中间价（假设USD/HKD汇率约为7.8）
            hkd_cny_mid = usd_cny_mid / 7.8
            
            # 保存到数据库
            db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
            conn = sqlite3.connect(db_path, timeout=15.0)
            cursor = conn.cursor()
            
            # 确保表存在
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS exchange_rate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    usd_cny_mid REAL,
                    hkd_cny_mid REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                INSERT OR REPLACE INTO exchange_rate (date, usd_cny_mid, hkd_cny_mid, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (today, usd_cny_mid, hkd_cny_mid, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            
            conn.commit()
            conn.close()
            
            # 标记今日已同步
            db_manager.mark_access_synced(today, 'exchange_rate')
            print(f"✅ 汇率数据已更新: USD/CNY={usd_cny_mid}, HKD/CNY={hkd_cny_mid:.4f}")
        else:
            print("❌ 未能获取汇率数据")
            
    except Exception as e:
        print(f"[警告] 汇率更新失败（不影响主程序运行）: {e}")

def _kill_process_on_port(port):
    """杀掉占用指定端口的进程（Windows）"""
    import subprocess
    try:
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if f':{port}' in line and ('LISTENING' in line or 'LISTEN' in line):
                parts = line.split()
                pid = parts[-1]
                try:
                    subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True, check=True)
                    print(f"⚠️  已杀掉占用端口{port}的旧进程(PID={pid})")
                except Exception as e:
                    pass
    except Exception as e:
        pass

if __name__ == '__main__':
    port = 5003
    # 启动前检查并杀掉旧进程
    _kill_process_on_port(port)
    print("启动集思录风格看板，请访问 http://127.0.0.1:5003")
    _auto_update_exchange_rates()
    app.run(host='0.0.0.0', port=port, debug=False)
