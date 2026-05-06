# -*- coding: utf-8 -*-
"""
测试腾讯失败的9个指数在东财接口的可用性
"""
import requests
import json
import os
import time

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

def fetch_eastmoney_realtime(symbol):
    """从东财获取实时行情"""
    # 处理不同格式的代码
    if symbol.startswith('sh'):
        idx_code = symbol[2:]
    elif symbol.startswith('sz'):
        idx_code = symbol[2:]
    else:
        idx_code = symbol
    
    # 确定secid前缀
    if idx_code.startswith('399'):
        secid = f"0.{idx_code}"
    elif idx_code.startswith('H'):
        # 中证海外指数使用2.前缀
        clean = idx_code.replace('.CSI', '')
        secid = f"2.{clean}"
    else:
        secid = f"1.{idx_code}"
    
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
                'secid': secid,
                'name': d.get('f58', idx_code),
                'last_price': d.get('f43', 0) / 100,
                'prev_close': d.get('f60', 0) / 100,
                'pct_change': d.get('f170', 0) / 100
            }
        else:
            return {'success': False, 'symbol': symbol, 'secid': secid, 'error': f"rc={data.get('rc')}"}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'secid': secid, 'error': str(e)}

def fetch_eastmoney_history(symbol, days=30):
    """从东财获取历史数据"""
    if symbol.startswith('sh'):
        idx_code = symbol[2:]
    elif symbol.startswith('sz'):
        idx_code = symbol[2:]
    else:
        idx_code = symbol
    
    if idx_code.startswith('399'):
        secid = f"0.{idx_code}"
    elif idx_code.startswith('H'):
        clean = idx_code.replace('.CSI', '')
        secid = f"2.{clean}"
    else:
        secid = f"1.{idx_code}"
    
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
                return {'success': True, 'symbol': symbol, 'secid': secid, 'count': len(klines)}
            else:
                return {'success': False, 'symbol': symbol, 'secid': secid, 'error': '无历史数据'}
        else:
            return {'success': False, 'symbol': symbol, 'secid': secid, 'error': f"rc={data.get('rc')}"}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'secid': secid, 'error': str(e)}

# 腾讯失败的9个指数
failed_indices = [
    ('sh930713', 'CS人工智能'),
    ('sh930720', 'CS互联网医疗'),
    ('sh930875', '空天军工'),
    ('sh930914', '港股通高股息'),
    ('sh930917', 'SHS高股息'),
    ('sh930997', '新能源车'),
    ('sh950090', '上证50优选'),
    ('shH11136', '中证海外中国互联网'),
    ('shH30094', '消费红利'),
]

print("=" * 70)
print("测试腾讯失败的9个指数在东财接口的可用性")
print("=" * 70)

# 测试东财实时行情
print("\n【东财实时行情测试】")
print("-" * 70)

realtime_success = []
realtime_failed = []

for symbol, name in failed_indices:
    result = fetch_eastmoney_realtime(symbol)
    print(f"\r测试: {symbol} - {name}", end='')
    
    if result['success']:
        realtime_success.append(result)
    else:
        realtime_failed.append(result)
    
    time.sleep(1)

print("\n\n【实时行情测试结果】")
print(f"成功: {len(realtime_success)} 个")
print(f"失败: {len(realtime_failed)} 个")

if realtime_success:
    print("\n成功获取实时行情:")
    for item in realtime_success:
        print(f"  ✅ {item['symbol']} ({item['name']}): {item['last_price']:.2f} ({item['pct_change']:.2f}%)")

if realtime_failed:
    print("\n获取实时行情失败:")
    for item in realtime_failed:
        print(f"  ❌ {item['symbol']}: {item['error']}")

# 测试东财历史数据
print("\n【东财历史数据测试】")
print("-" * 70)

history_success = []
history_failed = []

for symbol, name in failed_indices:
    result = fetch_eastmoney_history(symbol)
    print(f"\r测试: {symbol} - {name}", end='')
    
    if result['success']:
        history_success.append(result)
    else:
        history_failed.append(result)
    
    time.sleep(1)

print("\n\n【历史数据测试结果】")
print(f"成功: {len(history_success)} 个")
print(f"失败: {len(history_failed)} 个")

if history_success:
    print("\n成功获取历史数据:")
    for item in history_success:
        print(f"  ✅ {item['symbol']}: {item['count']} 条记录")

if history_failed:
    print("\n获取历史数据失败:")
    for item in history_failed:
        print(f"  ❌ {item['symbol']}: {item['error']}")

# 总结
print("\n" + "=" * 70)
print("【总结】")
print("=" * 70)
print(f"腾讯实时接口: 全部失败 (9/9)")
print(f"东财实时接口: 成功 {len(realtime_success)}/9")
print(f"东财历史接口: 成功 {len(history_success)}/9")
