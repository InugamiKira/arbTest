import requests
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class EastMoneyIndexFetcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://quote.eastmoney.com/",
            "Connection": "keep-alive"
        }
        self._szse_blocked = False

    def _convert_a_index_to_secid(self, index_code):
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

    def fetch_a_share_index(self, index_code):
        secid = self._convert_a_index_to_secid(index_code)
        if not secid:
            return None

        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f43,f60,f169,f170"
        try:
            resp = requests.get(url, headers=self.headers, timeout=8)
            data = resp.json().get("data")
            if not data:
                logger.warning(f"[EM-A] No data for index {index_code} (secid: {secid})")
                return None

            name = data.get("f58", index_code)
            last_raw = data.get("f43")
            prev_raw = data.get("f60")
            pct_raw = data.get("f170")

            if last_raw is None or prev_raw is None:
                logger.warning(f"[EM-A] Missing price data for index {index_code}")
                return None

            last_price = float(last_raw) / 100.0 if last_raw else 0
            prev_close = float(prev_raw) / 100.0 if prev_raw else 0
            pct_change = float(pct_raw) / 100.0 if pct_raw is not None else ((last_price / prev_close - 1) * 100) if prev_close > 0 else 0

            return {
                'symbol': index_code,
                'name': name,
                'last_price': last_price,
                'prev_close': prev_close,
                'pct_change': pct_change,
                'source': 'eastmoney_a'
            }
        except Exception as e:
            logger.error(f"[EM-A] Failed to fetch index {index_code}: {e}")
            return None

    def fetch_multiple_indices(self, index_codes):
        results = {}
        for code in index_codes:
            code_str = str(code).strip()
            if not code_str or code_str in ('-', 'nan', '0'):
                continue
            result = self.fetch_a_share_index(code_str)
            if result:
                results[code_str] = result
        return results

def fetch_a_share_indices_via_eastmoney(index_codes):
    fetcher = EastMoneyIndexFetcher()
    return fetcher.fetch_multiple_indices(index_codes)
