# -*- coding: utf-8 -*-
# 统一指数符号格式为东财格式（无前缀，大写）
import sqlite3

print("=== 开始统一指数符号格式 ===")

# 1. 更新代码中的映射
with open('jsl009_jsl_monitor_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 更新 hk_alias，直接返回东财格式（大写无前缀）
old_hk_alias = '''hk_alias = {
        'hsi': 'hkHSI', 'hscei': 'hkHSCEI', 'hscce': 'hkHSCCI', 'hsmc': 'hkHSMCI', 'hssmall': 'hkHSSI',
        'hstech': 'hkHSTECH', 'hss': 'hkHSCI', 'hsci': 'hkHSCI', 'hkmes': 'hkHSMCI', 'hktop': 'hkHSI', 'hkbk': 'hkHSI',
        'hssi': 'hkHSSI'
    }'''

new_hk_alias = '''hk_alias = {
        'hsi': 'HSI', 'hscei': 'HSCEI', 'hscce': 'HSCCI', 'hsmc': 'HSMCI', 'hssmall': 'HSSI',
        'hstech': 'HSTECH', 'hss': 'HSCI', 'hsci': 'HSCI', 'hkmes': 'HSMCI', 'hktop': 'HSI', 'hkbk': 'HSI',
        'hssi': 'HSSI', 'hkhssi': 'HSSI'
    }'''

content = content.replace(old_hk_alias, new_hk_alias)

# 更新 em_map，使用东财格式作为键
old_em_map = '''    em_map = {
        "hkHSI": ("HSI", "100"),
        "hkHSCEI": ("HSCEI", "100"),
        "hkHSCCI": ("HSCCI", "100"),
        "hkHSMCI": ("HSMCI", "100"),
        "hkHSSI": ("HSSI", "100"),
        "hkHSTECH": ("HSTECH", "124"),
        "hkHSCI": ("HSCI", "124")
    }'''

new_em_map = '''    em_map = {
        "HSI": ("HSI", "100"),
        "HSCEI": ("HSCEI", "100"),
        "HSCCI": ("HSCCI", "100"),
        "HSMCI": ("HSMCI", "100"),
        "HSSI": ("HSSI", "124"),
        "HSTECH": ("HSTECH", "124"),
        "HSCI": ("HSCI", "124")
    }'''

content = content.replace(old_em_map, new_em_map)

# 更新获取港股指数的条件（移除hk前缀判断）
content = content.replace('if missing_hk: quote_map.update(_fetch_eastmoney_hk_quotes(conn, [s for s in missing_hk if not s.startswith("hk")]))', 
                         'if missing_hk: quote_map.update(_fetch_eastmoney_hk_quotes(conn, missing_hk))')

# 更新 _convert_to_history_symbol 函数，直接返回原值
old_convert_func = '''def _convert_to_history_symbol(symbol):
    """将新浪格式的指数符号转换为index_history表中的符号格式"""
    if not symbol:
        return symbol
    # 映射表：新浪格式 -> index_history格式
    symbol_map = {
        'hkHSI': 'hsi',
        'hkHSCEI': 'hscei',
        'hkHSCI': 'hkHSCI',
        'hkHSTECH': 'hstech',
        'hkHSSI': 'HSSI',
        'hkHSCCI': 'hscce',
        'hkHSMCI': 'hsmc',
    }
    return symbol_map.get(symbol, symbol)'''

new_convert_func = '''def _convert_to_history_symbol(symbol):
    """将指数符号转换为index_history表中的符号格式"""
    if not symbol:
        return symbol
    # 统一使用东财格式映射到历史数据表格式
    symbol_map = {
        'HSI': 'hsi',
        'HSCEI': 'hscei',
        'HSCI': 'hkHSCI',
        'HSTECH': 'hstech',
        'HSSI': 'HSSI',
        'HSCCI': 'hscce',
        'HSMCI': 'hsmc',
    }
    return symbol_map.get(symbol, symbol)'''

content = content.replace(old_convert_func, new_convert_func)

with open('jsl009_jsl_monitor_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated code mappings")

# 2. 更新 fund_list.csv 中的指数代码
with open('fund_list.csv', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 创建指数代码映射
index_mapping = {
    'hsi': 'HSI',
    'hscei': 'HSCEI',
    'hscce': 'HSCCI',
    'hsmc': 'HSMCI',
    'hstech': 'HSTECH',
    'hsci': 'HSCI',
    'hktop': 'HSI',
    'hkbk': 'HSI',
    'hkmes': 'HSMCI',
    'hkhssi': 'HSSI'
}

new_lines = []
for line in lines:
    parts = line.strip().split(',')
    if len(parts) > 14 and parts[14]:  # 第15列是指数代码
        old_code = parts[14].strip()
        if old_code in index_mapping:
            parts[14] = index_mapping[old_code]
            print("  Updated: " + old_code + " -> " + parts[14])
    new_lines.append(','.join(parts))

with open('fund_list.csv', 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print("Updated fund_list.csv")

# 3. 更新数据库中的实时行情符号
conn = sqlite3.connect('jsl_monitor.db')
c = conn.cursor()

# 更新 index_realtime_quotes 表中的符号
c.execute("UPDATE index_realtime_quotes SET symbol = 'HSI' WHERE symbol = 'hkHSI'")
c.execute("UPDATE index_realtime_quotes SET symbol = 'HSCEI' WHERE symbol = 'hkHSCEI'")
c.execute("UPDATE index_realtime_quotes SET symbol = 'HSCI' WHERE symbol = 'hkHSCI'")
c.execute("UPDATE index_realtime_quotes SET symbol = 'HSTECH' WHERE symbol = 'hkHSTECH'")
c.execute("UPDATE index_realtime_quotes SET symbol = 'HSSI' WHERE symbol = 'hkHSSI'")

conn.commit()
print("Updated database realtime quotes")

conn.close()

print("\n=== 统一完成！使用东财格式 ===")
print("Format: HSCI, HSCEI, HSI, HSTECH, HSSI, HSCCI, HSMCI")