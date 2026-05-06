# -*- coding: utf-8 -*-
import requests
import json
import os

# 强制禁用系统代理，开着 VPN 也能顺畅跑
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

def test_url(url, name):
    print(f"\n--- 测试 {name} ---")
    
    # 将浏览器的 SSE 长连接推送接口替换为 GET 单次快照接口，彻底解决断连！
    url = url.replace('/api/qt/stock/sse', '/api/qt/stock/get')
    print(f"URL: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Accept': 'application/json',
        'Connection': 'close'  # 阅后即焚，不占用服务器资源
    }
    
    try:
        # 移除 stream=True，加上代理直连双保险
        resp = requests.get(url, headers=headers, timeout=10, proxies={"http": None, "https": None})
        data = resp.json()
        print(f"完整返回数据：\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if data.get('rc') == 0 and data.get('data'):
            d = data['data']
            print(f"\n解析结果：")
            print(f"  f43 (最新价): {d.get('f43')}")
            print(f"  f60 (昨收): {d.get('f60')}")
            print(f"  f170 (涨跌幅): {d.get('f170')}")
            print(f"  f58 (名称): {d.get('f58')}")
            
            last_price = d.get('f43', 0) / 100
            prev_close = d.get('f60', 0) / 100
            pct_change = d.get('f170', 0) / 100
            
            print(f"\n计算后：")
            print(f"  最新价: {last_price}")
            print(f"  昨收: {prev_close}")
            print(f"  涨跌幅: {pct_change}%")
        else:
            print(f"接口返回异常或数据为空: {data}")
    except Exception as e:
        print(f"出错：{e}")


# 测试用户给的URL
url_hscei = 'https://95.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=100.HSCEI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=|0|0|0|web'
test_url(url_hscei, '恒生中国企业指数 (100.HSCEI)')

# 测试恒生指数
url_hsi = 'https://95.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=100.HSI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=|0|0|0|web'
test_url(url_hsi, '恒生指数 (100.HSI)')
