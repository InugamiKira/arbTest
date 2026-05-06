# -*- coding: utf-8 -*-
"""
测试腾讯接口作为备选方案
"""
import requests
import re
import time
import os

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

def fetch_tencent_a_stock(symbol):
    """获取腾讯A股实时行情"""
    url = f"http://qt.gtimg.cn/q={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://gu.qq.com/'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        pattern = r'v_([^=]+)="([^"]+)";'
        match = re.search(pattern, resp.text)
        if match:
            fields = match.group(2).split('~')
            if len(fields) >= 6:
                return {
                    'success': True,
                    'symbol': symbol,
                    'name': fields[1],
                    'price': float(fields[3]) if fields[3] else None,
                    'prev_close': float(fields[4]) if fields[4] else None,
                }
        return {'success': False, 'symbol': symbol}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

def fetch_tencent_hk(symbol):
    """获取腾讯港股实时行情"""
    url = f"http://qt.gtimg.cn/q={symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://hk.finance.qq.com/'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        pattern = r'v_([^=]+)="([^"]+)";'
        match = re.search(pattern, resp.text)
        if match:
            fields = match.group(2).split('~')
            if len(fields) >= 6:
                return {
                    'success': True,
                    'symbol': symbol,
                    'name': fields[1],
                    'price': float(fields[3]) if fields[3] else None,
                    'prev_close': float(fields[4]) if fields[4] else None,
                }
        return {'success': False, 'symbol': symbol}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

print("=" * 70)
print("测试腾讯接口作为备选方案")
print("=" * 70)

# A股指数
print("\n【A股指数 - 腾讯接口】")
a_stock_indices = [
    ('sh000922', '中证红利'),
    ('sh000905', '中证500'),
    ('sh000001', '上证指数'),
    ('sz399001', '深证成指'),
    ('sz399300', '沪深300'),
]

for symbol, name in a_stock_indices:
    result = fetch_tencent_a_stock(symbol)
    if result['success']:
        change = result['price'] - result['prev_close']
        pct = (change / result['prev_close']) * 100 if result['prev_close'] else 0
        print(f"  ✅ {symbol} {name}: {result['price']:.2f} ({pct:+.2f}%)")
    else:
        print(f"  ❌ {symbol} {name}: {result.get('error', '失败')}")
    time.sleep(0.5)

# 港股指数
print("\n【港股指数 - 腾讯接口】")
hk_indices = [
    ('hkHSI', '恒生指数'),
    ('hkHSCEI', '国企指数'),
]

for symbol, name in hk_indices:
    result = fetch_tencent_hk(symbol)
    if result['success']:
        change = result['price'] - result['prev_close']
        pct = (change / result['prev_close']) * 100 if result['prev_close'] else 0
        print(f"  ✅ {symbol} {name}: {result['price']:.2f} ({pct:+.2f}%)")
    else:
        print(f"  ❌ {symbol} {name}: {result.get('error', '失败')}")
    time.sleep(0.5)

print("\n" + "=" * 70)
print("结论: 东财接口不稳定时，腾讯接口可作为备选")
print("=" * 70)
