# -*- coding: utf-8 -*-
"""
测试 fund_list.csv 中所有指数在腾讯接口的可用性
包含防封机制：请求间隔控制
"""
import requests
import re
import json
import os
import time
import pandas as pd
from datetime import datetime

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 防封配置
REQUEST_INTERVAL = 1.5  # 请求间隔（秒）
BATCH_SIZE = 10         # 每批测试数量
BATCH_PAUSE = 5        # 批次间隔（秒）

def fetch_tencent_realtime(symbol):
    """获取腾讯实时行情"""
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
                    'code': fields[2],
                    'last_price': float(fields[3]) if fields[3] else None,
                    'prev_close': float(fields[4]) if fields[4] else None,
                    'open': float(fields[5]) if fields[5] else None,
                }
        return {'success': False, 'symbol': symbol, 'error': '解析失败'}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

def fetch_eastmoney_history(symbol, days=30):
    """从东财获取历史数据"""
    # 转换代码格式
    if symbol.startswith('sh'):
        secid = f"1.{symbol[2:]}"
        idx_code = symbol[2:]
    elif symbol.startswith('sz'):
        secid = f"0.{symbol[2:]}"
        idx_code = symbol[2:]
    else:
        # 尝试作为纯数字处理
        if symbol.isdigit():
            if symbol.startswith('399'):
                secid = f"0.{symbol}"
            else:
                secid = f"1.{symbol}"
            idx_code = symbol
        else:
            return {'success': False, 'symbol': symbol, 'error': '不支持的格式'}
    
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

def load_index_codes():
    """从CSV加载所有指数代码"""
    df = pd.read_csv('fund_list.csv', dtype=str)
    index_codes = set()
    
    for _, row in df.iterrows():
        idx_code = str(row.get('指数代码', '')).strip()
        if idx_code and idx_code not in ('-', 'nan'):
            # 处理各种格式
            if idx_code.startswith('H30') or idx_code.startswith('9'):
                # 沪深指数
                if idx_code.startswith('399'):
                    index_codes.add(f'sz{idx_code}')
                else:
                    index_codes.add(f'sh{idx_code}')
            elif idx_code.startswith('H11'):
                # 中证海外指数
                clean = idx_code.replace('.CSI', '')
                index_codes.add(f'sh{clean}')
            elif idx_code.isdigit():
                # 纯数字代码
                if idx_code.startswith('399'):
                    index_codes.add(f'sz{idx_code}')
                else:
                    index_codes.add(f'sh{idx_code}')
            # 跳过海外指数（腾讯不支持）
            elif idx_code.startswith(('int_', 'DWRTF', 'SPI', 'NDX', 'AGG', 'inx_', 'spchval')):
                continue
            # 跳过港股指数（腾讯格式不同）
            elif idx_code in ('HSI', 'HSCEI', 'HSCI', 'HSMI'):
                continue
    
    return sorted(list(index_codes))

def test_all_indices():
    """测试所有指数"""
    print("=" * 70)
    print("测试 fund_list.csv 中所有指数的接口可用性")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"请求间隔: {REQUEST_INTERVAL}秒, 每批{BATCH_SIZE}个, 批次间隔{BATCH_PAUSE}秒")
    print("=" * 70)
    
    index_codes = load_index_codes()
    print(f"\n共发现 {len(index_codes)} 个可测试的A股指数代码")
    
    # 腾讯实时行情测试
    print("\n" + "=" * 70)
    print("【腾讯接口 - 盘中实时行情测试】")
    print("=" * 70)
    
    tencent_success = []
    tencent_failed = []
    
    for i, symbol in enumerate(index_codes, 1):
        print(f"\r测试中: {i}/{len(index_codes)} ({symbol})", end='')
        result = fetch_tencent_realtime(symbol)
        
        if result['success']:
            tencent_success.append(result)
        else:
            tencent_failed.append(result)
        
        # 控制请求间隔
        time.sleep(REQUEST_INTERVAL)
        
        # 批次控制
        if i % BATCH_SIZE == 0 and i < len(index_codes):
            print(f"\n--- 已完成 {i} 个，暂停 {BATCH_PAUSE} 秒 ---")
            time.sleep(BATCH_PAUSE)
    
    print("\n\n【腾讯接口测试结果】")
    print(f"成功: {len(tencent_success)} 个")
    print(f"失败: {len(tencent_failed)} 个")
    
    if tencent_success:
        print("\n成功获取的指数:")
        for item in tencent_success:
            print(f"  ✅ {item['symbol']} - {item['name']}: {item['last_price']:.2f}")
    
    if tencent_failed:
        print("\n获取失败的指数:")
        for item in tencent_failed:
            print(f"  ❌ {item['symbol']}: {item['error']}")
    
    # 东财历史数据测试（只测试腾讯成功的）
    print("\n" + "=" * 70)
    print("【东财接口 - 历史收盘测试】")
    print("=" * 70)
    
    eastmoney_success = []
    eastmoney_failed = []
    
    for i, item in enumerate(tencent_success, 1):
        symbol = item['symbol']
        print(f"\r测试中: {i}/{len(tencent_success)} ({symbol})", end='')
        result = fetch_eastmoney_history(symbol)
        
        if result['success']:
            eastmoney_success.append(result)
        else:
            eastmoney_failed.append(result)
        
        time.sleep(REQUEST_INTERVAL)
    
    print("\n\n【东财历史数据测试结果】")
    print(f"成功: {len(eastmoney_success)} 个")
    print(f"失败: {len(eastmoney_failed)} 个")
    
    if eastmoney_success:
        print("\n成功获取历史数据的指数:")
        for item in eastmoney_success:
            print(f"  ✅ {item['symbol']}: {item['count']} 条记录")
    
    if eastmoney_failed:
        print("\n获取历史数据失败的指数:")
        for item in eastmoney_failed:
            print(f"  ❌ {item['symbol']}: {item['error']}")
    
    # 总结
    print("\n" + "=" * 70)
    print("【测试总结】")
    print("=" * 70)
    print(f"总共测试指数: {len(index_codes)}")
    print(f"腾讯实时接口成功: {len(tencent_success)}")
    print(f"东财历史接口成功: {len(eastmoney_success)}")
    print(f"两者都成功: {len([x for x in eastmoney_success if x['symbol'] in [y['symbol'] for y in tencent_success]])}")

if __name__ == '__main__':
    test_all_indices()
