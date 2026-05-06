# -*- coding: utf-8 -*-
"""
测试东财港股接口 - 添加重试机制和改进请求头
"""
import requests
import os
import time
import random

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

def fetch_eastmoney_hk_with_retry(symbol, max_retries=3):
    """获取东财港股实时行情（带重试）"""
    if symbol.startswith('hk'):
        hk_code = symbol[2:]
    else:
        hk_code = symbol
    
    # 港股secid格式：116.指数代码 或 115.股票代码
    if hk_code in ('HSI', 'HSCEI', 'HSCI', 'HSMI'):
        secid = f"116.{hk_code}"
    else:
        secid = f"116.{hk_code}"
    
    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    params = {
        'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45',
        'secid': secid,
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': f'https://quote.eastmoney.com/{secid}.html',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Origin': 'https://quote.eastmoney.com'
    }
    
    session = requests.Session()
    
    for attempt in range(max_retries):
        try:
            # 添加随机延迟避免被封
            time.sleep(random.uniform(1, 2))
            
            resp = session.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            
            data = resp.json()
            
            if data.get('rc') == 0 and data.get('data'):
                d = data['data']
                return {
                    'success': True,
                    'symbol': symbol,
                    'name': d.get('f58', hk_code),
                    'last_price': d.get('f43', 0) / 100,
                    'prev_close': d.get('f60', 0) / 100,
                    'pct_change': d.get('f170', 0) / 100
                }
            else:
                return {'success': False, 'symbol': symbol, 'error': f"rc={data.get('rc')}"}
                
        except requests.exceptions.RequestException as e:
            print(f"  第{attempt+1}次尝试失败: {str(e)[:50]}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
            else:
                return {'success': False, 'symbol': symbol, 'error': str(e)}
    
    return {'success': False, 'symbol': symbol, 'error': '重试耗尽'}

# 测试港股指数
hk_indices = [
    ('hkHSI', '恒生指数'),
    ('hkHSCEI', '恒生中国企业指数'),
    ('hkHSCI', '恒生综合指数'),
    ('hkHSMI', '恒生中型股指数'),
]

print("=" * 70)
print("东财港股接口测试（带重试机制）")
print("=" * 70)

for symbol, name in hk_indices:
    print(f"\n测试: {symbol} - {name}")
    result = fetch_eastmoney_hk_with_retry(symbol)
    
    if result['success']:
        print(f"  ✅ 成功: {result['name']} = {result['last_price']:.2f} ({result['pct_change']:+.2f}%)")
    else:
        print(f"  ❌ 失败: {result['error']}")

print("\n" + "=" * 70)
print("测试完成！")
