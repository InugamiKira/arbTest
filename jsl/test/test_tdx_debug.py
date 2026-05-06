# -*- coding: utf-8 -*-
"""
调试：检查通达信连接状态，并尝试不同的代码格式
"""
import sys
sys.path.insert(0, r'D:\Study\arbTest\test_read_data\5_Place_AShare_Order')
from tqcenter import tq

def setup_tdx():
    try:
        tq.initialize(__file__)
        print("✅ tqcenter API 初始化成功！\n")
        return True
    except Exception as e:
        print(f"❌ tqcenter 初始化失败: {e}")
        return False

def test_snapshot(code):
    """尝试获取实时快照"""
    try:
        snapshot = tq.get_market_snapshot(stock_code=code, field_list=[])
        if snapshot and 'Now' in snapshot:
            return {'success': True, 'price': snapshot.get('Now')}
        return {'success': False}
    except Exception as e:
        return {'success': False, 'error': str(e)[:30]}

if __name__ == '__main__':
    print("=" * 60)
    print("调试：检查通达信连接状态")
    print("=" * 60)

    if not setup_tdx():
        exit(1)

    # 先测试一个已知有数据的指数
    print("\n【测试已知有数据的指数】")
    result = test_snapshot('399300.SZ')
    print(f"399300.SZ (沪深300): {'✅ ' + str(result.get('price')) if result['success'] else '❌ ' + result.get('error', '失败')}")

    # 测试那3个问题指数（多种格式）
    print("\n【测试之前失败的指数（多种格式）】")
    test_codes = [
        ('000922', '中证红利 - 纯数字'),
        ('1.000922', '中证红利 - 1.前缀'),
        ('000922.SH', '中证红利 - SH后缀'),
        ('000922.ZS', '中证红利 - ZS后缀'),
        ('000979', '大宗商品 - 纯数字'),
        ('000961', '中证上游 - 纯数字'),
    ]

    for code, desc in test_codes:
        result = test_snapshot(code)
        if result['success']:
            print(f"  ✅ {desc} ({code}): {result['price']}")
        else:
            print(f"  ❌ {desc} ({code}): {result.get('error', '无数据')}")

    print("\n" + "=" * 60)
    print("调试完成！")
    print("\n💡 如果 '已知有数据的指数' 显示失败，说明通达信客户端未正确连接。")
    print("💡 如果只有特定格式的代码成功，说明需要使用对应的代码格式。")
