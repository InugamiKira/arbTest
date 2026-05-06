# -*- coding: utf-8 -*-
"""
再次测试那3个之前失败的指数
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

# 之前失败的3个指数
indices = [
    ('000922.SH', '中证红利'),
    ('000979.SH', '大宗商品'),
    ('000961.SH', '中证上游'),
]

if __name__ == '__main__':
    print("=" * 60)
    print("重新测试3个之前失败的指数")
    print("=" * 60)

    if not setup_tdx():
        exit(1)

    for symbol, name in indices:
        try:
            df_dict = tq.get_market_data(
                field_list=[],
                stock_list=[symbol],
                start_time='',
                end_time='',
                count=5,
                period='1d'
            )

            if df_dict and 'Close' in df_dict and symbol in df_dict['Close'].columns:
                close_data = df_dict['Close'][symbol].dropna()
                if not close_data.empty:
                    print(f"\n✅ {symbol} {name}: 成功获取 {len(close_data)} 条数据")
                    print(f"   最新收盘: {close_data.iloc[0]:.2f}")
                else:
                    print(f"\n❌ {symbol} {name}: 仍然无数据")
            else:
                print(f"\n❌ {symbol} {name}: 无数据")

        except Exception as e:
            print(f"\n❌ {symbol} {name}: {e}")

    print("\n" + "=" * 60)
    print("测试完成！")
