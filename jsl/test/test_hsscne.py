# -*- coding: utf-8 -*-
import requests
import json
import sqlite3
from datetime import datetime, timedelta

def test_realtime(url, name, symbol):
    print("\n--- Test " + name + " ---")
    print("URL: " + url)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
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
                        idx_name = d.get('f58', '')
                        idx_code = d.get('f57', '')
                        
                        print("\nResult:")
                        print("  Name: " + idx_name)
                        print("  Code: " + idx_code)
                        print("  Last Price: " + str(last_price))
                        print("  Previous Close: " + str(prev_close))
                        print("  Change: " + str(pct_change) + "%")
                        
                        conn = sqlite3.connect('jsl_monitor.db')
                        c = conn.cursor()
                        c.execute('''
                            INSERT OR REPLACE INTO index_realtime_quotes 
                            (symbol, last_price, prev_close, pct_change, source)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (symbol, last_price, prev_close, pct_change, 'eastmoney'))
                        conn.commit()
                        conn.close()
                        print("  Saved to database")
                        return True
                    break
    except Exception as e:
        print("Error: " + str(e))
        return False

def test_history(secid, symbol, days=30):
    """Test history data using correct parameters"""
    print("\n--- Get " + symbol + " history ---")
    
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
                    ''', (symbol, date, close))
                    count += 1
            
            conn.commit()
            conn.close()
            print("Saved " + str(count) + " history records")
            
            print("\nLast 5 records:")
            conn = sqlite3.connect('jsl_monitor.db')
            c = conn.cursor()
            c.execute('SELECT date, close FROM index_history WHERE symbol = ? ORDER BY date DESC LIMIT 5', (symbol,))
            for row in c.fetchall():
                print("  " + row[0] + ": " + str(row[1]))
            conn.close()
            return True
        else:
            print("Get history failed: rc=" + str(data.get("rc")))
            return False
    except Exception as e:
        print("Get history error: " + str(e))
        return False

# Test HSSCNE 恒生港股通新经济指数 (124.HSSCNE)
url = 'https://10.push2.eastmoney.com/api/qt/stock/sse?fields=f58,f107,f57,f43,f59,f169,f170,f152,f46,f60,f44,f45,f171,f47,f86,f292&mpi=1000&invt=2&fltt=1&secid=124.HSSCNE&ut=fa5fd1943c7b386f172d6893dbfba10b&dect=1&wbp2u=7663325595358202|0|1|0|web'

if test_realtime(url, 'HSSCNE (124.HSSCNE)', 'HSSCNE'):
    test_history('124.HSSCNE', 'HSSCNE', days=30)

print("\n=== Test Complete ===")