import os
import sys
import sqlite3
import pandas as pd
import logging
import time
import random
import json
import contextlib
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug', 'szse')

def is_trading_day(check_date=None):
    """判断指定日期是否是A股交易日"""
    if check_date is None:
        check_date = datetime.now().date()

    if check_date.weekday() >= 5:
        return False

    holidays = [
        datetime(2026, 1, 1).date(),
        datetime(2026, 1, 28).date(),
        datetime(2026, 1, 29).date(),
        datetime(2026, 1, 30).date(),
        datetime(2026, 1, 31).date(),
        datetime(2026, 2, 1).date(),
        datetime(2026, 4, 4).date(),
        datetime(2026, 5, 1).date(),
        datetime(2026, 5, 2).date(),
        datetime(2026, 5, 3).date(),
        datetime(2026, 6, 25).date(),
        datetime(2026, 10, 1).date(),
        datetime(2026, 10, 2).date(),
        datetime(2026, 10, 3).date(),
        datetime(2026, 10, 4).date(),
        datetime(2026, 10, 5).date(),
        datetime(2026, 10, 6).date(),
        datetime(2026, 10, 7).date(),
        datetime(2026, 9, 27).date(),
    ]

    if check_date in holidays:
        return False

    return True

def get_last_trading_day(check_date=None):
    """获取上一个交易日的日期"""
    if check_date is None:
        check_date = datetime.now().date()

    date = check_date
    while True:
        date -= timedelta(days=1)
        if is_trading_day(date):
            return date
        if (check_date - date).days > 30:
            return None

def get_current_time_int():
    """获取当前时间整数（格式HHMM）"""
    return int(datetime.now().strftime('%H%M'))

def ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_file_path(fund_code):
    """获取缓存文件路径"""
    return os.path.join(CACHE_DIR, f'{fund_code}.json')

def read_cache(fund_code):
    """读取缓存文件"""
    cache_file = get_cache_file_path(fund_code)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def write_cache(fund_code, data):
    """写入缓存文件"""
    ensure_cache_dir()
    cache_file = get_cache_file_path(fund_code)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning(f"⚠️ [SZSE] 写入缓存失败 {fund_code}: {e}")
        return False

class SZSEFundSharesFetcher:
    CACHE_INTERVAL = 20 * 60
    TIME_LIMIT = 915

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
        self.db_path = db_path
        self._szse_blocked = False

    def get_szse_fund_codes(self):
        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql("""
                SELECT DISTINCT fund_code FROM fund_info
                WHERE fund_code LIKE '16%' OR fund_code LIKE '15%' OR fund_code LIKE '14%'
            """, conn)
            return df['fund_code'].tolist() if not df.empty else []
        finally:
            conn.close()

    def _check_time_limit(self):
        """woody技术：9:15之前不请求数据"""
        current_time = get_current_time_int()
        if current_time < self.TIME_LIMIT:
            logger.info(f"[SZSE] ⏰ 时间 {current_time} < 0915，数据未更新，跳过请求")
            return False
        return True

    def _check_cache_valid(self, fund_code):
        """woody技术：20分钟缓存机制"""
        cache_data = read_cache(fund_code)
        if cache_data is None:
            return None

        cache_time = cache_data.get('cache_time', 0)
        current_time = time.time()

        if current_time - cache_time < self.CACHE_INTERVAL:
            logger.debug(f"[SZSE] ⏳ 缓存有效（{int(self.CACHE_INTERVAL - (current_time - cache_time))}秒后过期），跳过 {fund_code}")
            return cache_data.get('data')

        return None

    def _check_already_fetched_today(self, fund_code):
        """woody技术：检查今日是否已有数据，有则跳过"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            today_date = datetime.now().date()
            if not is_trading_day(today_date):
                target_date = get_last_trading_day(today_date)
            else:
                target_date = today_date

            if target_date is None:
                return False

            today_str = target_date.strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT id FROM fund_history
                WHERE fund_code = ? AND date = ? AND shares IS NOT NULL
            """, (fund_code, today_str))

            existing = cursor.fetchone()
            if existing:
                logger.debug(f"[SZSE] ✓ 今日已有数据（{today_str}），跳过 {fund_code}")
                return True

            return False
        finally:
            conn.close()

    def _fetch_szse_fund_by_code(self, fund_code):
        """通过基金代码获取深交所LOF基金的详细信息"""
        url = f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1945_LOF&txtQueryKeyAndJC={fund_code}&random={random.random()}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.szse.cn/market/fund/list/index.html",
            "X-Request-Type": "ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Host": "www.szse.cn"
        }

        try:
            import requests
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=10, verify=False, proxies={"http": None, "https": None})
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0 and 'data' in data[0]:
                    fund_list = data[0]['data']
                    if fund_list and len(fund_list) > 0:
                        return fund_list[0]
        except Exception as e:
            logger.warning(f"⚠️ [SZSE] 获取基金 {fund_code} 数据失败: {e}")
        return None

    def fetch_shares_safe(self, fund_code):
        """安全地获取基金场内份额（woody防封技术）"""
        if self._szse_blocked:
            logger.debug(f"[SZSE] 🔒 熔断激活，跳过 {fund_code}")
            return None

        if not self._check_time_limit():
            return None

        cached_data = self._check_cache_valid(fund_code)
        if cached_data is not None:
            return cached_data

        if self._check_already_fetched_today(fund_code):
            return None

        time.sleep(random.uniform(2.0, 4.0))
        fund_info = self._fetch_szse_fund_by_code(fund_code)

        if fund_info:
            dqgm = fund_info.get('dqgm', '')
            if isinstance(dqgm, str):
                dqgm = dqgm.replace(',', '')
            if dqgm:
                try:
                    shares_float = float(dqgm)
                    logger.info(f"✅ [SZSE] {fund_code} 当前规模: {dqgm} 万份")

                    result = {
                        'nav_date': datetime.now().strftime('%Y-%m-%d'),
                        'shares': shares_float
                    }

                    write_cache(fund_code, {
                        'cache_time': time.time(),
                        'data': result
                    })

                    return result
                except Exception as e:
                    logger.warning(f"⚠️ [SZSE] {fund_code} 规模数据解析失败: {e}")

        logger.warning(f"⚠️ [SZSE] 未能查到 {fund_code} 的规模信息")
        return None

    def batch_fetch_shares(self, fund_codes, delay_range=(3.0, 6.0), max_count=None):
        results = {}
        count = 0
        skipped_cache = 0
        skipped_today = 0
        skipped_time = 0

        for fund_code in fund_codes:
            before_time = get_current_time_int()

            result = self.fetch_shares_safe(fund_code)

            after_time = get_current_time_int()

            if result:
                results[fund_code] = result
                count += 1
            elif before_time < self.TIME_LIMIT:
                skipped_time += 1
            elif self._check_cache_valid(fund_code) is not None:
                skipped_cache += 1
            elif self._check_already_fetched_today(fund_code):
                skipped_today += 1

            if max_count and count >= max_count:
                logger.info(f"[SZSE] 达到最大获取数量 {max_count}，停止")
                break

            if count < len(fund_codes):
                time.sleep(random.uniform(*delay_range))

        logger.info(f"[SZSE] 批量获取完成：成功 {count}，时间限制跳过 {skipped_time}，缓存跳过 {skipped_cache}，今日已有 {skipped_today}")
        return results

    def update_shares_in_history(self, shares_data):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            updated = 0

            today_date = datetime.now().date()
            if is_trading_day(today_date):
                target_date = today_date
            else:
                last_trading_day = get_last_trading_day(today_date)
                if last_trading_day is None:
                    logger.warning("[SZSE] 无法获取上一个交易日，跳过更新")
                    conn.close()
                    return 0
                target_date = last_trading_day
                logger.info(f"[SZSE] 今日({today_date})非交易日，使用上一个交易日({target_date})")

            today = target_date.strftime('%Y-%m-%d')

            for fund_code, data in shares_data.items():
                if not data or 'shares' not in data:
                    continue

                shares = data.get('shares')
                if shares is None:
                    continue

                cursor.execute("""
                    SELECT id FROM fund_history
                    WHERE fund_code = ? AND date = ?
                """, (fund_code, today))

                existing = cursor.fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE fund_history
                        SET shares = ?
                        WHERE fund_code = ? AND date = ?
                    """, (shares, fund_code, today))
                else:
                    cursor.execute("""
                        INSERT INTO fund_history (date, fund_code, shares)
                        VALUES (?, ?, ?)
                    """, (today, fund_code, shares))

                updated += 1

            conn.commit()
            logger.info(f"[SZSE] 更新了 {updated} 只基金的份额数据")
            return updated
        finally:
            conn.close()

def fetch_and_update_szse_shares():
    fetcher = SZSEFundSharesFetcher()
    fund_codes = fetcher.get_szse_fund_codes()
    if not fund_codes:
        logger.info("未找到深交所基金代码")
        return

    logger.info(f"找到 {len(fund_codes)} 只深交所基金")
    results = fetcher.batch_fetch_shares(fund_codes, delay_range=(3.0, 6.0), max_count=50)

    if results:
        fetcher.update_shares_in_history(results)

    return results

if __name__ == "__main__":
    fetch_and_update_szse_shares()