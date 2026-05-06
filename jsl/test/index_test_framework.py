# -*- coding: utf-8 -*-
"""
统一指数测试框架
支持：实时行情 + 历史数据爬取
"""
import requests
import json
import sqlite3

# 指数配置列表
INDEX_CONFIGS = [
    # 港股指数 (124.XXX)
    {
        'name': '恒生综合指数',
        'symbol': 'HSCI',
        'secid': '124.HSCI',
        'prefix': '124',
        'url': 'https://56.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSCI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '恒生科技指数',
        'symbol': 'HSTECH',
        'secid': '124.HSTECH',
        'prefix': '124',
        'url': 'https://56.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSTECH&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '恒生综合小型股指数',
        'symbol': 'HSSI',
        'secid': '124.HSSI',
        'prefix': '124',
        'url': 'https://9.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSSI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '恒生综合中型股指数',
        'symbol': 'HSMI',
        'secid': '124.HSMI',
        'prefix': '124',
        'url': 'https://40.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSMI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '恒生港股通新经济指数',
        'symbol': 'HSSCNE',
        'secid': '124.HSSCNE',
        'prefix': '124',
        'url': 'https://10.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSSCNE&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    # 港股指数 (100.XXX)
    {
        'name': '恒生指数',
        'symbol': 'HSI',
        'secid': '100.HSI',
        'prefix': '100',
        'url': 'https://28.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=100.HSI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '国企指数',
        'symbol': 'HSCEI',
        'secid': '100.HSCEI',
        'prefix': '100',
        'url': 'https://28.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=100.HSCEI&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    # 中证指数 (2.XXX)
    {
        'name': '港股通高股息',
        'symbol': '930914',
        'secid': '2.930914',
        'prefix': '2',
        'url': 'https://84.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f47,f48,f19,f532,f39,f161,f49,f171,f50,f86,f600,f601,f154,f84,f85,f168,f108,f116,f167,f164,f92,f71,f117,f292,f113,f114,f115,f119,f120,f121,f122,f296&mpi=1000&invt=2&fltt=1&secid=2.930914&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': 'SHS高股息',
        'symbol': '930917',
        'secid': '2.930917',
        'prefix': '2',
        'url': 'https://84.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f47,f48,f19,f532,f39,f161,f49,f171,f50,f86,f600,f601,f154,f84,f85,f168,f108,f116,f167,f164,f92,f71,f117,f292,f113,f114,f115,f119,f120,f121,f122,f296&mpi=1000&invt=2&fltt=1&secid=2.930917&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    {
        'name': '中国互联网指数',
        'symbol': 'H11136',
        'secid': '2.H11136',
        'prefix': '2',
        'url': 'https://28.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=2.H11136&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    },
    # A股股票 (1.XXX)
    {
        'name': 'HK银行',
        'symbol': '000869',
        'secid': '1.000869',
        'prefix': '1',
        'url': 'https://16.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f47,f48,f19,f532,f39,f161,f49,f171,f50,f86,f600,f601,f154,f84,f85,f168,f108,f116,f167,f164,f92,f71,f117,f292,f113,f114,f115,f119,f120,f121,f122,f296&mpi=1000&invt=2&fltt=1&secid=1.000869&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'
    }
]

def test_realtime(index_config):
    """测试实时行情"""
    symbol = index_config['symbol']
    name = index_config['name']
    url = index_config['url']
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Accept': 'text/event-stream'
    }
    
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=10)
        for line in resp.iter_lines():
            if line:
                text = line.decode('utf-8')
                if text.startswith('data:'):
                    json_str = text[5:]
                    data = json.loads(json_str)
                    
                    if data.get('rc') == 0 and data.get('data'):
                        d = data['data']
                        last_price = d.get('f43', 0) / 100
                        prev_close = d.get('f60', 0) / 100
                        pct_change = d.get('f170', 0) / 100
                        
                        # 保存到数据库
                        conn = sqlite3.connect('jsl_monitor.db')
                        c = conn.cursor()
                        c.execute('INSERT OR REPLACE INTO index_realtime_quotes (symbol, last_price, prev_close, pct_change, source) VALUES (?, ?, ?, ?, ?)', 
                                  (symbol, last_price, prev_close, pct_change, 'eastmoney'))
                        conn.commit()
                        conn.close()
                        
                        return {'success': True, 'name': name, 'symbol': symbol, 'last_price': last_price, 'change': pct_change}
                    break
    except Exception as e:
        return {'success': False, 'name': name, 'symbol': symbol, 'error': str(e)}

def test_history(index_config, days=30):
    """测试历史数据"""
    secid = index_config['secid']
    symbol = index_config['symbol']
    
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
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        
        if data.get('rc') == 0 and data.get('data'):
            klines = data['data'].get('klines', [])
            
            conn = sqlite3.connect('jsl_monitor.db')
            c = conn.cursor()
            
            count = 0
            for kline in klines:
                parts = kline.split(',')
                if len(parts) >= 3:
                    c.execute('INSERT OR REPLACE INTO index_history (symbol, date, close) VALUES (?, ?, ?)', 
                              (symbol, parts[0], float(parts[2])))
                    count += 1
            
            conn.commit()
            conn.close()
            return {'success': True, 'symbol': symbol, 'count': count}
        else:
            return {'success': False, 'symbol': symbol, 'error': f"rc={data.get('rc')}"}
    except Exception as e:
        return {'success': False, 'symbol': symbol, 'error': str(e)}

def run_all_tests(test_type='all'):
    """运行所有测试"""
    print("=" * 60)
    print("统一指数测试框架 v1.0")
    print("=" * 60)
    
    if test_type in ['all', 'realtime']:
        print("\n【实时行情测试】")
        print("-" * 40)
        for config in INDEX_CONFIGS:
            result = test_realtime(config)
            if result['success']:
                print(f"✅ {result['name']} ({result['symbol']}): {result['last_price']:.2f}, {result['change']:.2f}%")
            else:
                print(f"❌ {result['name']} ({result['symbol']}): {result.get('error')}")
    
    if test_type in ['all', 'history']:
        print("\n【历史数据测试】")
        print("-" * 40)
        for config in INDEX_CONFIGS:
            result = test_history(config)
            if result['success']:
                print(f"✅ {config['name']} ({config['symbol']}): 保存 {result['count']} 条记录")
            else:
                print(f"❌ {config['name']} ({config['symbol']}): {result.get('error')}")
    
    print("\n" + "=" * 60)
    print("测试完成！")

if __name__ == '__main__':
    import sys
    test_type = sys.argv[1] if len(sys.argv) > 1 else 'all'
    run_all_tests(test_type)