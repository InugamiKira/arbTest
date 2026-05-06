# -*- coding: utf-8 -*-
"""
测试用户程序中的指数东财接口是否可用
"""
import requests
import time
import random
import os

os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

def fetch_eastmoney_realtime(index_code):
    """获取东财实时行情（带重试）"""
    # 处理不同格式的代码
    # 例如: 399998.SZ, 399300.SZ, 000922.SH, H30094.HI, HSI.HI

    # 分离市场和代码
    if '.' in index_code:
        code, market = index_code.split('.')
        market = market.upper()
    else:
        code = index_code
        market = None

    # 确定东财secid
    if market == 'SZ':
        secid = f"0.{code}"
    elif market == 'SH':
        secid = f"1.{code}"
    elif market == 'HI':  # 港股
        secid = f"116.{code}"
    else:
        # 尝试判断
        if code.startswith('399'):
            secid = f"0.{code}"
        elif code.startswith('H') or code.startswith('CES') or code.startswith('HSSC') or code.startswith('HST'):
            secid = f"116.{code}"
        else:
            secid = f"1.{code}"

    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    params = {
        'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45',
        'secid': secid,
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
    }

    for attempt in range(3):
        try:
            time.sleep(random.uniform(1.5, 2.5))
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            data = resp.json()

            if data.get('rc') == 0 and data.get('data'):
                d = data['data']
                return {
                    'success': True,
                    'code': index_code,
                    'name': d.get('f58', code),
                    'price': d.get('f43', 0) / 100,
                    'pct': d.get('f170', 0) / 100
                }
            else:
                return {'success': False, 'code': index_code, 'error': f"rc={data.get('rc')}"}
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return {'success': False, 'code': index_code, 'error': str(e)[:50]}

# 用户程序中的指数列表（取几个代表性的）
test_indices = [
    ('399998.SZ', '中证消费服务指数'),
    ('399300.SZ', '沪深300'),
    ('000922.SH', '中证红利'),
    ('399001.SZ', '深证成指'),
    ('000905.SH', '中证500'),
    ('H30094.HI', '消费红利'),
    ('HSI.HI', '恒生指数'),
    ('HSCEI.HI', '国企指数'),
]

print("=" * 70)
print("测试东财接口是否可用")
print("=" * 70)

success_count = 0
fail_count = 0

for code, name in test_indices:
    print(f"\n测试: {code} - {name}")
    result = fetch_eastmoney_realtime(code)

    if result['success']:
        print(f"  ✅ 成功: {result['name']} = {result['price']:.2f} ({result['pct']:+.2f}%)")
        success_count += 1
    else:
        print(f"  ❌ 失败: {result['error']}")
        fail_count += 1

print("\n" + "=" * 70)
print(f"测试结果: 成功 {success_count}/{len(test_indices)}, 失败 {fail_count}/{len(test_indices)}")
print("=" * 70)
