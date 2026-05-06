# -*- coding: utf-8 -*-
"""
腾讯行情接口综合测试
1. 盘中实时行情 (腾讯接口)
2. 历史收盘数据 (东财接口作为补充)
"""
import requests
import re
import json
import os
from datetime import datetime, timedelta

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

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
            if len(fields) >= 14:
                return {
                    'source': 'tencent',
                    'symbol': symbol,
                    'name': fields[1],
                    'code': fields[2],
                    'last_price': float(fields[3]),
                    'prev_close': float(fields[4]),
                    'open': float(fields[5]),
                    'volume': int(fields[6]),
                    'high': float(fields[8]) if fields[8] != '0' else None,
                    'low': float(fields[9]) if fields[9] != '0' else None,
                    'quote_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        return None
    except Exception as e:
        print(f"腾讯接口失败: {e}")
        return None

def fetch_eastmoney_history(index_code, days=60):
    """从东财获取历史收盘数据"""
    # 转换代码格式
    if index_code.startswith('sh'):
        secid = f"1.{index_code[2:]}"
    elif index_code.startswith('sz'):
        secid = f"0.{index_code[2:]}"
    else:
        secid = f"1.{index_code}"
    
    # 计算日期范围
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    
    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101',  # 日线
        'fqt': '1',    # 前复权
        'beg': start_date,
        'end': end_date,
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
            history = []
            for kline in klines:
                parts = kline.split(',')
                if len(parts) >= 6:
                    history.append({
                        'date': parts[0],
                        'open': float(parts[1]),
                        'close': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'volume': int(parts[5])
                    })
            return history
        return None
    except Exception as e:
        print(f"东财历史接口失败: {e}")
        return None

def test_realtime():
    """测试实时行情"""
    print("=" * 60)
    print("【实时行情测试】- 腾讯接口")
    print("=" * 60)
    
    indices = [
        ('sh000922', '中证红利指数'),
        ('sh000001', '上证指数'),
        ('sz399001', '深证成指'),
        ('sh000300', '沪深300'),
    ]
    
    for symbol, name in indices:
        data = fetch_tencent_realtime(symbol)
        if data:
            change = data['last_price'] - data['prev_close']
            pct_change = (change / data['prev_close']) * 100
            print(f"\n{name} ({symbol})")
            print(f"  最新价: {data['last_price']:.2f}")
            print(f"  昨收: {data['prev_close']:.2f}")
            print(f"  涨跌: {change:+.2f} ({pct_change:+.2f}%)")
            print(f"  今开: {data['open']:.2f}")
            print(f"  成交量: {data['volume']:,}")
            print(f"  更新时间: {data['quote_time']}")

def test_history():
    """测试历史数据"""
    print("\n" + "=" * 60)
    print("【历史收盘测试】- 东财接口")
    print("=" * 60)
    
    indices = [
        ('sh000922', '中证红利指数'),
        ('sh000001', '上证指数'),
    ]
    
    for symbol, name in indices:
        history = fetch_eastmoney_history(symbol, days=60)
        if history:
            recent = history[-10:]  # 取最近10条
            print(f"\n{name} ({symbol}) - 最近{len(recent)}个交易日")
            print(f"{'日期':<12} {'收盘':>10} {'涨跌额':>10} {'涨跌幅':>10}")
            print("-" * 45)
            
            for i, day in enumerate(recent):
                if i > 0:
                    prev_close = recent[i-1]['close']
                    change = day['close'] - prev_close
                    pct = (change / prev_close) * 100
                else:
                    change = '-'
                    pct = '-'
                
                print(f"{day['date']:<12} {day['close']:>10.2f} {change:>10.2f} {pct:>10.2f}%" if isinstance(change, float) else f"{day['date']:<12} {day['close']:>10.2f} {change:>10} {pct:>10}")

if __name__ == '__main__':
    test_realtime()
    test_history()
    print("\n" + "=" * 60)
    print("测试完成！")
