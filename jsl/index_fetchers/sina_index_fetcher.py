import requests
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SinaIndexFetcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://finance.sina.com.cn/",
            "Accept-Encoding": "gzip, deflate, br"
        }
        self._normalize_map = {
            'hsi': 'hkHSI',
            'hscei': 'hkHSCEI',
            'hscce': 'hkHSCCI',
            'hsmc': 'hkHSMCI',
            'hssmall': 'hkHSSI',
            'hstech': 'hkHSTECH',
            'hkmes': 'hkHSMCI',
            'hktop': 'hkHSI',
            'hkbk': 'hkHSI',
            'int_sp500': 'gb_$inx',
            'int_sox': 'gb_$sox',
            'int_us': 'gb_qqq',
            'int_india': 'gb_inda',
            'int_agg': 'gb_agg',
            'int_djr': 'gb_vnq',
            'inx_chn': 'gb_kweb',
            'inx_spbi': 'gb_xbi',
            'inx_splx': 'gb_xly',
            'inx_spxl': 'gb_xlk',
            'inx_spxv': 'gb_xlv',
            'spchval': 'gb_fxi'
        }

    def normalize_symbol(self, raw_code):
        if not raw_code:
            return None
        code = str(raw_code).strip().lower()
        if not code or code in ('-', 'nan', '0'):
            return None
        if code in self._normalize_map:
            return self._normalize_map[code]
        if code.startswith('hk'):
            return code
        if code.startswith('gb_'):
            return code
        return None

    def _parse_sina_hk_line(self, line):
        nums = re.findall(r"-?\d+(?:\.\d+)?", line or "")
        if len(nums) < 5:
            return None
        try:
            return {
                'last_price': float(nums[1]),
                'prev_close': float(nums[2]),
                'pct_change': float(nums[4])
            }
        except:
            return None

    def _parse_sina_us_line(self, line):
        try:
            payload = (line or "").split('"')
            if len(payload) < 2:
                return None
            fields = payload[1].split(",")
            if len(fields) < 3:
                return None
            last_price = float(fields[1])
            pct_change = float(fields[2])
            prev_close = float(fields[26]) if len(fields) > 26 and fields[26] else None
            if not prev_close:
                prev_close = last_price / (1 + pct_change / 100)
            return {
                'last_price': last_price,
                'prev_close': prev_close,
                'pct_change': pct_change
            }
        except Exception as e:
            logger.debug(f"Failed to parse US line: {e}")
            return None

    def _extract_name(self, line):
        name_match = re.search(r'="([^,]*)', line or "")
        return name_match.group(1) if name_match else None

    def fetch_hk_index(self, symbol):
        sina_sym = self.normalize_symbol(symbol)
        if not sina_sym or not sina_sym.startswith('hk'):
            return None

        url = f"https://hq.sinajs.cn/list={sina_sym}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=8)
            resp.encoding = "gbk"
            line = resp.text.strip()
            parsed = self._parse_sina_hk_line(line)
            if not parsed:
                return None
            name = self._extract_name(line) or sina_sym
            return {
                'symbol': symbol,
                'name': name,
                'last_price': parsed['last_price'],
                'prev_close': parsed['prev_close'],
                'pct_change': parsed['pct_change'],
                'source': 'sina_hk'
            }
        except Exception as e:
            logger.error(f"[Sina-HK] Failed to fetch {symbol}: {e}")
            return None

    def fetch_us_index(self, symbol):
        sina_sym = self.normalize_symbol(symbol)
        if not sina_sym or not sina_sym.startswith('gb_'):
            return None

        url = f"https://hq.sinajs.cn/list={sina_sym}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=8)
            resp.encoding = "gbk"
            line = resp.text.strip()
            parsed = self._parse_sina_us_line(line)
            if not parsed:
                return None
            name = self._extract_name(line) or sina_sym
            return {
                'symbol': symbol,
                'name': name,
                'last_price': parsed['last_price'],
                'prev_close': parsed['prev_close'],
                'pct_change': parsed['pct_change'],
                'source': 'sina_us'
            }
        except Exception as e:
            logger.error(f"[Sina-US] Failed to fetch {symbol}: {e}")
            return None

    def fetch_index(self, symbol):
        sina_sym = self.normalize_symbol(symbol)
        if not sina_sym:
            return None
        if sina_sym.startswith('hk'):
            return self.fetch_hk_index(symbol)
        elif sina_sym.startswith('gb_'):
            return self.fetch_us_index(symbol)
        return None

    def fetch_multiple(self, symbols):
        results = {}
        hk_symbols = []
        us_symbols = []
        symbol_map = {}

        for sym in symbols:
            sina_sym = self.normalize_symbol(sym)
            if not sina_sym:
                continue
            symbol_map[sina_sym] = sym
            if sina_sym.startswith('hk'):
                hk_symbols.append(sina_sym)
            elif sina_sym.startswith('gb_'):
                us_symbols.append(sina_sym)

        if hk_symbols:
            url = f"https://hq.sinajs.cn/list={','.join(hk_symbols)}"
            try:
                resp = requests.get(url, headers=self.headers, timeout=10)
                resp.encoding = "gbk"
                for line in resp.text.splitlines():
                    m = re.search(r'var hq_str_([^=]+)=', line)
                    if not m:
                        continue
                    sina_sym = m.group(1).strip()
                    original_sym = symbol_map.get(sina_sym)
                    if not original_sym:
                        continue
                    parsed = self._parse_sina_hk_line(line)
                    if parsed:
                        name = self._extract_name(line) or sina_sym
                        results[original_sym] = {
                            'symbol': original_sym,
                            'name': name,
                            'last_price': parsed['last_price'],
                            'prev_close': parsed['prev_close'],
                            'pct_change': parsed['pct_change'],
                            'source': 'sina_hk'
                        }
            except Exception as e:
                logger.error(f"[Sina-HK] Batch fetch failed: {e}")

        if us_symbols:
            url = f"https://hq.sinajs.cn/list={','.join(us_symbols)}"
            try:
                resp = requests.get(url, headers=self.headers, timeout=10)
                resp.encoding = "gbk"
                for line in resp.text.splitlines():
                    m = re.search(r'var hq_str_([^=]+)=', line)
                    if not m:
                        continue
                    sina_sym = m.group(1).strip()
                    original_sym = symbol_map.get(sina_sym)
                    if not original_sym:
                        continue
                    parsed = self._parse_sina_us_line(line)
                    if parsed:
                        name = self._extract_name(line) or sina_sym
                        results[original_sym] = {
                            'symbol': original_sym,
                            'name': name,
                            'last_price': parsed['last_price'],
                            'prev_close': parsed['prev_close'],
                            'pct_change': parsed['pct_change'],
                            'source': 'sina_us'
                        }
            except Exception as e:
                logger.error(f"[Sina-US] Batch fetch failed: {e}")

        return results

def fetch_hk_us_indices_via_sina(symbols):
    fetcher = SinaIndexFetcher()
    return fetcher.fetch_multiple(symbols)
