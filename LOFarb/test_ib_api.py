# test_ib_api.py - 独立的 IB 夜盘接口探路测试程序
import requests
import json

def test_ib_api():
    # 按照 LOF03 和 LOF004 现有的逻辑，访问本地 5000 端口的 API
    url = "http://localhost:5000/api/ib_prices"
    
    try:
        print(f"🚀 正在请求后端 IB 数据接口: {url}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()  # 如果遇到 404/500 等 HTTP 错误会直接抛出异常
        
        data = response.json()
        
        print("\n" + "="*40)
        print("📦 接口返回的完整原始 JSON 数据:")
        print("="*40)
        # 打印格式化后的 JSON，方便肉眼观察到底有没有 size 字段
        print(json.dumps(data, indent=4, ensure_ascii=False))
        
        print("\n" + "="*40)
        print("🔍 核心字段解析分析:")
        print("="*40)
        
        if data.get("status") == "success" and "prices" in data:
            prices = data["prices"]
            if not prices:
                print("⚠️ 接口状态为 success，但 prices 字典为空，可能处于非交易时间或未订阅数据。")
            
            for symbol, info in prices.items():
                bid = info.get("bid", "无")
                ask = info.get("ask", "无")
                
                # 尝试探测各种常见的 size 字段命名习惯
                bid_size = info.get("bid_size", info.get("bidSize", "接口未提供"))
                ask_size = info.get("ask_size", info.get("askSize", "接口未提供"))
                
                print(f"🎯 标的 [{symbol}]:")
                print(f"   买盘 (Bid): 价格 = {bid:<8} | 数量 = {bid_size}")
                print(f"   卖盘 (Ask): 价格 = {ask:<8} | 数量 = {ask_size}")
                print("-" * 30)
        else:
            print(f"⚠️ 未能获取到正常的行情字典，当前状态: {data.get('status', '未知')}")
            print(f"ℹ️ 后台提示信息: {data.get('message', '无')}")
            
    except requests.exceptions.RequestException as e:
        print("\n❌ 请求失败！")
        print(f"错误详情: {e}")
        print("💡 请检查: LOF后台服务 (LOF02_fetch_trade_data.py) 是否已启动并监听在 5000 端口？")

if __name__ == "__main__":
    test_ib_api()
