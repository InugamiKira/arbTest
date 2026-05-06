# -*- coding: utf-8 -*-
"""
测试港股指数的接口可用性
港股代码格式特殊，需要单独处理
"""
import requests
import re
import os
import time

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

def fetch_tencent_hk(symbol):
    """获取腾讯港股实时行情"""
    # 腾讯港股代码格式：hk+5位数字
    # 例如：hk00001 (长和), hk0005 (汇丰)
    # 指数：hkHSI (恒生指数), hkHSCEI (国企指数)
    
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
                # 处理成交量字段（港股可能是小数）
                try:
                    volume = int(float(fields[6])) if fields[6] else 0
                except:
                    volume = 0
                    
                return {
                    'success': True,
                    'symbol': symbol,
                    'name': fields[1],
                    'code': fields[2],
                    'last_price': float(fields[3]) if fields[3] else None,
                    'prev_close': float(fields[4]) if fields[4] else None,
                    'open': float(fields[5]) if fields[5] else None,
                    'volume': volume,
                    'high': float(fields[8]) if fields[8] != '0' else None,
                    'low': float(fields[9]) if fields[9] != '0' else None,
                }
        return {'success': False, 'symbol': symbol, 'error': '解析失败'}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

def fetch_eastmoney_hk(symbol):
    """从东财获取港股实时行情"""
    # 东财港股代码格式：116.xxxx 或 115.xxxx
    # 恒生指数：116.HSI, 国企指数：116.HSCEI
    
    # 处理代码格式
    if symbol.startswith('hk'):
        hk_code = symbol[2:]
    else:
        hk_code = symbol
    
    # 判断是指数还是股票
    if hk_code in ('HSI', 'HSCEI', 'HSCI', 'HSMI'):
        secid = f"116.{hk_code}"
    else:
        # 港股股票
        secid = f"116.{hk_code}"
    
    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    params = {
        'fields': 'f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45',
        'secid': secid,
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
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
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

def fetch_eastmoney_hk_history(symbol, days=30):
    """从东财获取港股历史数据"""
    if symbol.startswith('hk'):
        hk_code = symbol[2:]
    else:
        hk_code = symbol
    
    secid = f"116.{hk_code}"
    
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101',
        'fqt': '1',
        'beg': '20260401',
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
            if len(klines) > 0:
                return {'success': True, 'symbol': symbol, 'count': len(klines)}
            else:
                return {'success': False, 'symbol': symbol, 'error': '无历史数据'}
        else:
            return {'success': False, 'symbol': symbol, 'error': f"rc={data.get('rc')}"}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

# 港股指数列表
hk_indices = [
    ('hkHSI', '恒生指数'),
    ('hkHSCEI', '恒生中国企业指数'),
    ('hkHSCI', '恒生综合指数'),
    ('hkHSMI', '恒生中型股指数'),
    # 港股通相关指数
    ('hk99901', '港股通AH溢价'),
    ('hk99902', '港股通指数'),
]

print("=" * 70)
print("测试港股指数接口可用性")
print("=" * 70)

# 测试腾讯接口
print("\n【腾讯港股接口测试】")
print("-" * 70)

tencent_results = []
for symbol, name in hk_indices:
    result = fetch_tencent_hk(symbol)
    tencent_results.append(result)
    print(f"\r测试: {symbol} - {name}", end='')
    time.sleep(1)

print("\n\n【腾讯测试结果】")
for result in tencent_results:
    if result['success']:
        change = result['last_price'] - result['prev_close']
        pct = (change / result['prev_close']) * 100 if result['prev_close'] else 0
        print(f"  ✅ {result['symbol']} ({result['name']}): {result['last_price']:.2f} ({pct:+.2f}%)")
    else:
        print(f"  ❌ {result['symbol']}: {result['error']}")

# 测试东财接口
print("\n【东财港股接口测试】")
print("-" * 70)

eastmoney_results = []
for symbol, name in hk_indices:
    result = fetch_eastmoney_hk(symbol)
    eastmoney_results.append(result)
    print(f"\r测试: {symbol} - {name}", end='')
    time.sleep(1)

print("\n\n【东财实时行情结果】")
for result in eastmoney_results:
    if result['success']:
        print(f"  ✅ {result['symbol']} ({result['name']}): {result['last_price']:.2f} ({result['pct_change']:+.2f}%)")
    else:
        print(f"  ❌ {result['symbol']}: {result['error']}")

# 测试东财历史数据
print("\n【东财港股历史数据测试】")
print("-" * 70)

history_results = []
for symbol, name in hk_indices:
    result = fetch_eastmoney_hk_history(symbol)
    history_results.append(result)
    print(f"\r测试: {symbol} - {name}", end='')
    time.sleep(1)

print("\n\n【东财历史数据结果】")
for result in history_results:
    if result['success']:
        print(f"  ✅ {result['symbol']}: {result['count']} 条记录")
    else:
        print(f"  ❌ {result['symbol']}: {result['error']}")

# 总结
print("\n" + "=" * 70)
print("【港股指数测试总结】")
print("=" * 70)
print(f"总共测试: {len(hk_indices)} 个港股指数")
print(f"腾讯实时接口成功: {sum(1 for r in tencent_results if r['success'])}")
print(f"东财实时接口成功: {sum(1 for r in eastmoney_results if r['success'])}")
print(f"东财历史接口成功: {sum(1 for r in history_results if r['success'])}")
