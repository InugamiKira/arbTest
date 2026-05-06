# -*- coding: utf-8 -*-
# jsl003_fetch_lof_quotes.py - LOF 基金盘中实时价格/成交量轮询引擎
import os
import sys
import sqlite3
import requests
import time
import logging
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
FETCH_INTERVAL = 5  # 轮询间隔（秒）

# 配置日志：同时输出到控制台和 logs 文件夹
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"jsl003_lof_quotes_{datetime.now().strftime('%Y%m%d')}.log")

logger = logging.getLogger('jsl003')
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

fh = logging.FileHandler(log_file, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

def _get_fund_codes(conn):
    """从数据库获取所有基金代码"""
    cursor = conn.cursor()
    cursor.execute("SELECT fund_code FROM fund_info WHERE fund_code != '-'")
    return [row[0] for row in cursor.fetchall() if row[0] and row[0].isdigit()]

def _fetch_and_update_tqcenter_quotes(conn, fund_codes):
    """优先使用官方 tqcenter 接口获取实时数据 (极速本地内存读取)"""
    if not fund_codes: return 0
    updated_count = 0
    details = []
    try:
        from tqcenter import tq
        tq.initialize(__file__)
        
        market_syms = []
        sym_map = {}
        for code in fund_codes:
            code_str = str(code)
            m_sym = f"{code_str}.SH" if code_str.startswith('5') else f"{code_str}.SZ"
            market_syms.append(m_sym)
            sym_map[m_sym] = code_str
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 改用 Snapshot 快照极速获取，彻底摆脱客户端 K线数据缓存限制
        for m_sym in market_syms:
            snap = tq.get_market_snapshot(m_sym, [])
            if snap and 'Now' in snap:
                now_v = snap.get('Now', 0)
                price = float(now_v[0]) if isinstance(now_v, list) else float(now_v)
                
                if price > 0:
                    vol_v = snap.get('Vol', snap.get('Volume', 0))
                    volume_shares = float(vol_v[0]) if isinstance(vol_v, list) else float(vol_v)
                    fund_code = sym_map[m_sym]
                    details.append(f"{fund_code}[{price:.3f}]")
                    
                    conn.execute("""
                        INSERT INTO fund_history (date, fund_code, price, volume)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(date, fund_code) DO UPDATE SET 
                        price=excluded.price, volume=excluded.volume
                    """, (today_str, fund_code, price, volume_shares))
                    updated_count += 1
        conn.commit()
        tq.close()
        if details:
            logger.info(f"✅ TDX(LOF) 更新 {len(details)} 只: " + ", ".join(details))
    except Exception:
        try: tq.close()
        except: pass
    return updated_count

def _fetch_and_update_sina_quotes(conn, fund_codes):
    """请求新浪接口并更新今日历史数据表"""
    if not fund_codes:
        return
        
    # 构造新浪标准查询符 (沪市5开头sh，深市15/16开头sz)
    sina_symbols = []
    for code in fund_codes:
        prefix = 'sh' if str(code).startswith('5') else 'sz'
        sina_symbols.append(f"{prefix}{code}")
        
    # 分批查询，每批最多 30 个，防封禁
    batch_size = 30
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    session = requests.Session()
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
    
    updated_count = 0
    details = []
    for i in range(0, len(sina_symbols), batch_size):
        batch = sina_symbols[i:i+batch_size]
        url = "https://hq.sinajs.cn/list=" + ",".join(batch)
        
        try:
            resp = session.get(url, headers=headers, timeout=5)
            resp.encoding = "gbk"
            
            for line in resp.text.splitlines():
                if '="' not in line:
                    continue
                # 解析类似于: var hq_str_sz162411="华宝油气,0.612,0.610,0.613,0.615...
                code_part, data_part = line.split('="')
                fund_code = code_part[-6:] # 提取六位纯数字代码
                fields = data_part.replace('";', '').split(',')
                
                # 新浪标准A股返回，至少要有32个字段
                if len(fields) > 30:
                    try:
                        price = float(fields[3])  # 最新价
                        volume_shares = float(fields[8])  # 成交量(股/份)
                        
                        if price > 0:
                            details.append(f"{fund_code}[{price:.3f}]")
                            
                            conn.execute("""
                                INSERT INTO fund_history (date, fund_code, price, volume)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(date, fund_code) DO UPDATE SET 
                                price=excluded.price, volume=excluded.volume
                            """, (today_str, fund_code, price, volume_shares))
                            updated_count += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"新浪 LOF 请求批次失败: {e}")
            
    conn.commit()
    if details:
        logger.info(f"✅ Sina(兜底LOF) 更新 {len(details)} 只: " + ", ".join(details))
    return updated_count

def run():
    logger.info("🚀 启动 LOF 盘中实时价格轮询引擎 (TDX主引擎 / 新浪备用)...")
    while True:
        try:
            with sqlite3.connect(DB_PATH, timeout=15.0) as conn:
                codes = _get_fund_codes(conn)
                
                # 优先尝试通达信极速获取
                tdx_count = _fetch_and_update_tqcenter_quotes(conn, codes)
                if tdx_count == 0:
                    # 通达信获取失败(如周末维护/网络断开)，自动降级到新浪兜底
                    _fetch_and_update_sina_quotes(conn, codes)
        except Exception as e:
            logger.error(f"数据库连接或循环异常: {e}")
            
        time.sleep(FETCH_INTERVAL)

if __name__ == '__main__':
    run()
