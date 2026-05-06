# -*- coding: utf-8 -*-
"""
测试 fund_list.csv 中三类指数的腾讯接口可用性
1. A股指数 - sh/sz格式
2. 中证特色指数 - sh930xxx格式
3. 港股指数 - hk开头格式
"""
import requests
import re
import time
import os

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
            if len(fields) >= 6 and fields[3]:
                return {
                    'success': True,
                    'symbol': symbol,
                    'name': fields[1],
                    'price': float(fields[3]),
                    'prev_close': float(fields[4]) if fields[4] else None,
                }
        return {'success': False, 'symbol': symbol, 'error': '解析失败'}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)[:30]}

def fetch_tencent_history(symbol):
    """获取腾讯历史数据（通过新浪接口）"""
    # 腾讯没有直接的历史接口，但可以通过解析K线页面获取
    # 这里用东财的历史接口，但加入重试
    pass

# 从 fund_list.csv 提取的指数分类
categories = {
    "A股指数 (sh/sz)": [
        ('sh000922', '中证红利', '000922'),
        ('sz399300', '沪深300', '399300'),
        ('sz399001', '深证成指', '399001'),
        ('sz399330', '深证100', '399330'),
        ('sh000905', '中证500', '000905'),
        ('sz399987', '中证酒', '399987'),
        ('sz399997', '中证白酒', '399997'),
        ('sz399441', '生物医药', '399441'),
        ('sz399809', '保险主题', '399809'),
        ('sz399989', '中证医疗', '399989'),
        ('sh000979', '大宗商品', '000979'),
        ('sh000961', '中证上游', '000961'),
    ],
    "中证特色指数 (sh930xxx)": [
        ('sh930713', 'CS人工智能', '930713'),
        ('sh930720', 'CS互联网医疗', '930720'),
        ('sh930875', '空天军工', '930875'),
        ('sh930997', '新能源车', '930997'),
        ('sh930914', '港股通高股息', '930914'),
        ('sh930917', 'SHS高股息', '930917'),
        ('sh950090', '上证50优选', '950090'),
    ],
    "港股指数 (hk)": [
        ('hkHSI', '恒生指数', 'HSI'),
        ('hkHSCEI', '恒生中国企业', 'HSCEI'),
        ('hkHSCI', '恒生综合', 'HSCI'),
        ('hkHSMI', '恒生中型股', 'HSMI'),
        ('hk000869', 'HK银行', '000869'),
    ],
}

print("=" * 70)
print("测试腾讯接口对三类指数的实时行情支持情况")
print("=" * 70)

for category, indices in categories.items():
    print(f"\n【{category}】")
    print("-" * 70)
    
    success = 0
    failed = 0
    
    for symbol, name, code in indices:
        result = fetch_tencent_realtime(symbol)
        if result['success']:
            change = result['price'] - result['prev_close'] if result['prev_close'] else 0
            pct = (change / result['prev_close'] * 100) if result['prev_close'] else 0
            print(f"  ✅ {symbol} {name}: {result['price']:.2f} ({pct:+.2f}%)")
            success += 1
        else:
            print(f"  ❌ {symbol} {name}: {result['error']}")
            failed += 1
        
        time.sleep(0.8)
    
    print(f"\n  小计: 成功 {success}/{len(indices)}, 失败 {failed}/{len(indices)}")

print("\n" + "=" * 70)
print("测试完成！")
