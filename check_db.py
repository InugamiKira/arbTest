import sqlite3

conn = sqlite3.connect(r'd:\Study\arbTest\database\arb_master.db')
cursor = conn.cursor()

# 获取所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")
    # 获取表结构
    cursor.execute(f"PRAGMA table_info({table[0]})")
    columns = cursor.fetchall()
    print("    Columns:")
    for col in columns:
        print(f"      - {col[1]} ({col[2]})")
    print()

conn.close()
