# -*- coding: utf-8 -*-
# jsl004_fetch_index_quotes.py - 全市场指数实时行情轮询引擎 (保留东财原汁原味接口)
import os
import sqlite3
import time
import requests
import sys
import random
import logging
from datetime import datetime

# 强制禁用系统代理，避免 VPN 影响访问
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

DB_PATH = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
FETCH_INTERVAL = 5

# 配置日志：同时输出到控制台和 logs 文件夹
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"jsl004_index_quotes_{datetime.now().strftime('%Y%m%d')}.log")

logger = logging.getLogger('jsl004')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

fh = logging.FileHandler(log_file, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

def _safe_float_from_em(val, divisor=100.0, default=0.0):
    if val in (None, '-', '', 'NaN', 'nan'):
        return default
    try:
        return float(val) / divisor
    except (ValueError, TypeError):
        return default

def _get_index_symbols(conn):
    """从数据库中提取所有需要抓取的指数代码"""
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT idx_code FROM fund_info WHERE idx_code IS NOT NULL AND idx_code != "-"')
    rows = cursor.fetchall()
    
    em_map = {}
    for row in rows:
        if not row[0]: continue
        idx_code = str(row[0]).strip().upper()
        if not idx_code or idx_code in ('NONE', 'NAN', '-'): continue
        
        # 兼容欧美指数白名单拦截
        overseas = ['.SPI', 'DWRTF', 'INT_', 'NDX.GI', 'AGG', 'INX_SP']
        if any(k in idx_code for k in overseas):
            continue
            
        # 智能添加东财 secid 前缀
        if idx_code.isdigit():
            if idx_code.startswith('399'):
                em_map[idx_code] = f"0.{idx_code}"  # 深市指数必须是 0.
            elif idx_code.startswith('000') or idx_code.startswith('001'):
                em_map[idx_code] = f"1.{idx_code}"  # 上证指数是 1.
            else:
                em_map[idx_code] = f"2.{idx_code}"  # 中证定制指数等是 2.
        else:
            clean_code = idx_code.replace('.CSI', '')
            em_map[idx_code] = f"2.{clean_code}"
            
    # 特别补充几个核心港股指数
    hk_map = {
        "HSI": "100.HSI", "HSCEI": "100.HSCEI", "HSCCI": "100.HSCCI", 
        "HSMCI": "100.HSMCI", "HSSI": "124.HSSI", "HSTECH": "124.HSTECH", "HSCI": "124.HSCI"
    }
    em_map.update(hk_map)
    return em_map

def _fetch_and_update_tqcenter(conn, symbols_list):
    """官方通达信 tqcenter 极速引擎（使用日线接口完美获取指数最新价）"""
    if not symbols_list: return []
    success_symbols = []
    details = []
    try:
        from tqcenter import tq
        
        market_syms = []
        sym_map = {}
        for sym in symbols_list:
            sym_str = str(sym).upper()
            # 核心修复：切除 .CSI 等多余后缀，防止破坏 tqcenter 的严格正则校验
            clean_sym = sym_str.split('.')[0]
            
            if clean_sym.isdigit():
                m_sym = f"{clean_sym}.SZ" if clean_sym.startswith('399') else f"{clean_sym}.SH"
            elif clean_sym in ['HSI', 'HSCEI', 'HSCCI', 'HSMCI', 'HSTECH', 'HSCI', 'HSSI', 'HSSCNE', 'HSMI']:
                m_sym = f"{clean_sym}.HI"
            else:
                m_sym = f"{clean_sym}.SH"
                
            market_syms.append(m_sym)
            sym_map[m_sym] = sym_str
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 指数没有买卖盘口，必须使用 get_market_data 获取最新 K 线切片
        df_dict = tq.get_market_data(field_list=[], stock_list=market_syms, start_time='', end_time='', count=2, period='1d')
        
        if df_dict and 'Close' in df_dict:
            for m_sym in market_syms:
                if m_sym in df_dict['Close'] and not df_dict['Close'][m_sym].dropna().empty:
                    close_data = df_dict['Close'][m_sym].dropna()
                    original_sym = sym_map[m_sym]
                    
                    last_price = float(close_data.iloc[-1])
                    prev_close = float(close_data.iloc[-2]) if len(close_data) >= 2 else last_price
                    
                    if last_price > 0 and prev_close > 0:
                        pct_change = (last_price / prev_close - 1.0) * 100.0
                        details.append(f"{original_sym}[{last_price:.2f}, {pct_change:+.2f}%]")
                        success_symbols.append(original_sym)
                        
                        conn.execute("""
                            INSERT INTO index_realtime_quotes
                            (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, 'tqcenter', ?)
                            ON CONFLICT(symbol) DO UPDATE SET
                            last_price=excluded.last_price, prev_close=excluded.prev_close,
                            pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
                        """, (original_sym, original_sym, last_price, prev_close, pct_change, now_str, now_str))
        conn.commit()
        if details:
            logger.info(f"✅ TDX(极速指数) 更新 {len(details)} 只: " + ", ".join(details))
    except Exception as e:
        logger.error(f"tqcenter 获取指数异常: {e}")
    return success_symbols

def _fetch_and_update_eastmoney(conn, em_map):
    """东财慢速引擎：安全获取港股和特殊指数"""
    if not em_map: return 0
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Accept': 'application/json',
        'Connection': 'close'  # 核心：阅后即焚，不占用服务器资源
    }
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_count = 0
    details = []
    
    # 经过实测验证的东财存活节点白名单
    valid_servers = [2, 8, 9, 10, 12, 16, 17, 26, 28, 40, 44, 45, 46, 54, 56, 80, 84, 85, 95]
    
    for symbol, secid in em_map.items():
        params = {
            'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292',
            'secid': secid,
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            'invt': '2',
            'fltt': '1'
        }
        
        for attempt in range(3):
            # 每次重试都重新摇号，绝不死磕同一个节点
            server_id = random.choice(valid_servers)
            url = f'https://{server_id}.push2.eastmoney.com/api/qt/stock/get'
            
            try:
                # 移除 session，使用原生 requests 单次快照直连
                resp = requests.get(url, params=params, headers=headers, timeout=5, proxies={"http": None, "https": None})
                data = resp.json()
                if data.get('rc') == 0 and data.get('data'):
                    d = data['data']
                    last_price = _safe_float_from_em(d.get('f43'))
                    prev_close = _safe_float_from_em(d.get('f60'))
                    pct_change = _safe_float_from_em(d.get('f170'))
                    name = d.get('f58', symbol)
                    
                    details.append(f"{name}[{last_price:.2f}, {pct_change:+.2f}%]")
                    
                    conn.execute("""
                        INSERT INTO index_realtime_quotes
                        (symbol, name, last_price, prev_close, pct_change, quote_time, source, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'eastmoney', ?)
                        ON CONFLICT(symbol) DO UPDATE SET
                        name=excluded.name, last_price=excluded.last_price, prev_close=excluded.prev_close,
                        pct_change=excluded.pct_change, quote_time=excluded.quote_time, source=excluded.source, updated_at=excluded.updated_at
                    """, (symbol, name, last_price, prev_close, pct_change, now_str, now_str))
                    updated_count += 1
                break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"获取东财指数 {symbol} 失败: {e}")
                else:
                    time.sleep(0.5)
        # 每次获取成功后安全停顿，拟人化
        time.sleep(0.5)
                    
    conn.commit()
    if details:
        logger.info(f"✅ EastMoney 更新 {len(details)} 只: " + ", ".join(details))
    return updated_count

def run():
    logger.info("🚀 启动全市场指数行情轮询引擎 (TDX 主引擎 + EastMoney 兜底)...")
            
    try:
        from tqcenter import tq
        tq.initialize(__file__)
    except Exception as e:
        logger.warning(f"⚠️ tqcenter 初始化失败，全量降级至东财兜底: {e}")
        
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS index_realtime_quotes (
                symbol TEXT PRIMARY KEY, name TEXT, last_price REAL, prev_close REAL,
                pct_change REAL, quote_time TEXT, source TEXT, updated_at TEXT
            )
        ''')
        
    while True:
        try:
            with sqlite3.connect(DB_PATH, timeout=15.0) as conn:
                em_map = _get_index_symbols(conn)
                
                # 1. 优先使用通达信极速获取全量指数（A股 + 港股），保障极高稳定性！活着最重要！
                all_symbols = list(em_map.keys())
                tdx_success = _fetch_and_update_tqcenter(conn, all_symbols)
                
                # 2. 找出通达信没有覆盖到的漏网之鱼（如 H30094 等），才迫不得已交给东财兜底
                fallback_map = {k: v for k, v in em_map.items() if k not in tdx_success}
                if fallback_map:
                    _fetch_and_update_eastmoney(conn, fallback_map)
        except Exception as e:
            logger.error(f"数据库连接或循环异常: {e}")
            
        time.sleep(FETCH_INTERVAL)

if __name__ == '__main__':
    run()
