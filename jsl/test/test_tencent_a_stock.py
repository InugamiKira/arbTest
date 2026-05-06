# -*- coding: utf-8 -*-
"""
腾讯行情接口测试 - A股指数专用
接口格式: http://qt.gtimg.cn/q=sh000922 (上证指数)
返回格式: v_sh000922="1~中证红利指数~000922~...";
"""
import requests
import re
import os

# 禁用系统代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

def parse_tencent_response(response_text):
    """
    解析腾讯行情接口返回的数据
    数据格式: v_sh000922="1~指数名称~代码~最新价~昨收~今开~成交量~成交额~...";
    """
    # 使用正则匹配数据
    pattern = r'v_([^=]+)="([^"]+)";'
    match = re.search(pattern, response_text)
    
    if not match:
        return None
    
    symbol = match.group(1)  # 如: sh000922
    data_str = match.group(2)  # 所有字段用~分隔
    
    # 按~分割字段
    fields = data_str.split('~')
    
    # 字段含义 (根据腾讯接口文档)
    # 0: 市场类型 (1=指数)
    # 1: 名称
    # 2: 代码
    # 3: 最新价
    # 4: 昨收
    # 5: 今开
    # 6: 成交量
    # 7: 成交额
    # 8: 最高
    # 9: 最低
    # 10: 买入价
    # 11: 卖出价
    # 12: 涨跌额
    # 13: 涨跌幅%
    # ...
    
    if len(fields) >= 14:
        return {
            'symbol': symbol,
            'name': fields[1],
            'code': fields[2],
            'last_price': float(fields[3]) if fields[3] else None,
            'prev_close': float(fields[4]) if fields[4] else None,
            'open': float(fields[5]) if fields[5] else None,
            'volume': int(fields[6]) if fields[6] else None,
            'amount': float(fields[7]) if fields[7] else None,
            'high': float(fields[8]) if fields[8] else None,
            'low': float(fields[9]) if fields[9] else None,
            'change': float(fields[12]) if fields[12] else None,
            'pct_change': float(fields[13]) if fields[13] else None
        }
    
    return None

def fetch_tencent_stock(symbol):
    """获取腾讯行情数据"""
    url = f"http://qt.gtimg.cn/q={symbol}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://gu.qq.com/',
        'Connection': 'close'
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10, proxies={"http": None, "https": None})
        resp.encoding = "gbk"  # 腾讯返回GBK编码
        return parse_tencent_response(resp.text)
    except Exception as e:
        print(f"请求失败: {e}")
        return None

def test_index(symbol, name):
    """测试单个指数"""
    print(f"\n=== 测试 {name} ({symbol}) ===")
    data = fetch_tencent_stock(symbol)
    
    if data:
        print(f"名称: {data['name']}")
        print(f"代码: {data['code']}")
        print(f"最新价: {data['last_price']}")
        print(f"昨收: {data['prev_close']}")
        print(f"今开: {data['open']}")
        print(f"最高: {data['high']}")
        print(f"最低: {data['low']}")
        print(f"涨跌额: {data['change']}")
        print(f"涨跌幅: {data['pct_change']}%")
        print(f"成交量: {data['volume']:,}")
        print(f"成交额: {data['amount']:,}")
        
        # 计算验证
        if data['prev_close'] and data['last_price']:
            calc_change = data['last_price'] - data['prev_close']
            calc_pct = (calc_change / data['prev_close']) * 100
            print(f"\n验证计算:")
            print(f"  涨跌额计算: {calc_change:.2f}")
            print(f"  涨跌幅计算: {calc_pct:.2f}%")
    else:
        print(f"获取失败！")

if __name__ == '__main__':
    print("=" * 60)
    print("腾讯A股指数行情接口测试")
    print("=" * 60)
    
    # 测试多个A股指数
    test_index('sh000922', '中证红利指数')
    test_index('sh000001', '上证指数')
    test_index('sz399001', '深证成指')
    test_index('sh000300', '沪深300')
    test_index('sh000852', '中证1000')
    
    print("\n" + "=" * 60)
    print("测试完成！")
