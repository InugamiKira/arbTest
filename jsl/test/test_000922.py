# -*- coding: utf-8 -*-
import requests
import json
import sqlite3
from datetime import datetime, timedelta

def test_000922_history(days=30):
    """测试获取 000922 中证红利指数的历史数据"""
    print("\n--- Get 000922 中证红利历史数据 ---")

    url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
    params = {
        'secid': '1.000922',
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
        'klt': '101',
        'fqt': '1',
        'beg': (datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
        'end': datetime.now().strftime('%Y%m%d'),
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
            print("Got " + str(len(klines)) + " kline data")

            conn = sqlite3.connect('jsl_monitor.db')
            c = conn.cursor()

            count = 0
            for kline in klines:
                parts = kline.split(',')
                if len(parts) >= 3:
                    date = parts[0]
                    close = float(parts[2])

                    c.execute('''
                        INSERT OR REPLACE INTO index_history
                        (symbol, date, close)
                        VALUES (?, ?, ?)
                    ''', ('000922', date, close))
                    count += 1

            conn.commit()
            conn.close()
            print("Saved " + str(count) + " records to index_history")
            return True
        else:
            print("No data returned")
            return False
    except Exception as e:
        print("Error: " + str(e))
        import traceback
        traceback.print_exc()
        return False

def test_000922_realtime():
    """测试 000922 中证红利指数的实时行情"""
    url = 'https://26.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f47,f48,f19,f532,f39,f161,f49,f171,f50,f86,f600,f601,f154,f84,f85,f168,f108,f116,f167,f164,f92,f71,f117,f292,f113,f114,f115,f119,f120,f121,f122,f296&mpi=1000&invt=2&fltt=1&secid=1.000922&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'

    print("\n--- Test 000922 中证红利 (实时行情) ---")

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
                    data = json.loads(text[5:])
                    if data.get('rc') == 0 and data.get('data'):
                        d = data['data']
                        last_price = d.get('f43', 0) / 100
                        prev_close = d.get('f60', 0) / 100
                        pct_change = d.get('f170', 0) / 100
                        idx_name = d.get('f58', '')
                        idx_code = d.get('f57', '')

                        print("\nResult:")
                        print("  Name: " + str(idx_name))
                        print("  Code: " + str(idx_code))
                        print("  Last Price: " + str(last_price))
                        print("  Previous Close: " + str(prev_close))
                        print("  Change: " + str(pct_change) + "%")

                        conn = sqlite3.connect('jsl_monitor.db')
                        c = conn.cursor()
                        c.execute('''
                            INSERT OR REPLACE INTO index_realtime_quotes
                            (symbol, last_price, prev_close, pct_change, source)
                            VALUES (?, ?, ?, ?, ?)
                        ''', ('000922', last_price, prev_close, pct_change, 'eastmoney'))
                        conn.commit()
                        conn.close()
                        print("  Saved to database")
                        return True
                    break
    except Exception as e:
        print("Error: " + str(e))
        return False

if __name__ == '__main__':
    test_000922_realtime()
    test_000922_history(30)