# -*- coding: utf-8 -*-
"""
测试通达信 tqcenter API 对12个A股指数的历史K线支持
"""
import sys
import os

# 添加通达信模块路径
sys.path.insert(0, r'D:\Study\arbTest\test_read_data\5_Place_AShare_Order')
from tqcenter import tq

def setup_tdx():
    """初始化通达信API"""
    try:
        tq.initialize(__file__)
        print("✅ tqcenter API 初始化成功！\n")
        return True
    except Exception as e:
        print(f"❌ tqcenter 初始化失败: {e}")
        return False

def test_index_history(symbol, name, period='1d', count=5):
    """测试获取单个指数的历史K线"""
    try:
        df_dict = tq.get_market_data(
            field_list=[],
            stock_list=[symbol],
            start_time='',
            end_time='',
            count=count,
            period=period
        )
        
        if df_dict and 'Close' in df_dict and symbol in df_dict['Close'].columns:
            close_data = df_dict['Close'][symbol].dropna()
            if not close_data.empty:
                return {
                    'success': True,
                    'name': name,
                    'symbol': symbol,
                    'data_count': len(close_data),
                    'latest_close': close_data.iloc[0],
                    'latest_date': close_data.index[0] if hasattr(close_data.index, '__iter__') else 'N/A'
                }
        return {'success': False, 'name': name, 'symbol': symbol, 'error': '无数据'}
    except Exception as e:
        return {'success': False, 'name': name, 'symbol': symbol, 'error': str(e)[:50]}

# 12个A股指数 (从之前的测试中)
a_stock_indices = [
    ('000922.SH', '中证红利'),
    ('399300.SZ', '沪深300'),
    ('399001.SZ', '深证成指'),
    ('399330.SZ', '深证100'),
    ('000905.SH', '中证500'),
    ('399987.SZ', '中证酒'),
    ('399997.SZ', '中证白酒'),
    ('399441.SZ', '生物医药'),
    ('399809.SZ', '保险主题'),
    ('399989.SZ', '中证医疗'),
    ('000979.SH', '大宗商品'),
    ('000961.SH', '中证上游'),
]

if __name__ == '__main__':
    print("=" * 70)
    print("测试通达信 tqcenter API 对12个A股指数的历史K线支持")
    print("=" * 70)
    
    if not setup_tdx():
        print("无法继续测试！")
        exit(1)
    
    print("\n【日线历史数据测试 (最近5天)】")
    print("-" * 70)
    
    success_count = 0
    fail_count = 0
    
    for symbol, name in a_stock_indices:
        result = test_index_history(symbol, name, period='1d', count=5)
        
        if result['success']:
            print(f"  ✅ {symbol} {name}: 成功获取 {result['data_count']} 条数据, 最新收盘: {result['latest_close']:.2f}")
            success_count += 1
        else:
            print(f"  ❌ {symbol} {name}: {result['error']}")
            fail_count += 1
    
    print("\n" + "=" * 70)
    print(f"【结果汇总】")
    print(f"成功: {success_count}/12")
    print(f"失败: {fail_count}/12")
    print("=" * 70)
    
    if success_count == 12:
        print("\n🎉 所有12个A股指数都支持通达信获取历史数据！")
    else:
        print("\n⚠️ 部分指数获取失败，可能需要先在通达信客户端查看该指数K线以下载数据。")
