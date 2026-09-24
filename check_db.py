import sqlite3
conn = sqlite3.connect("ai_consulting.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cur.fetchall()
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t[0]}")
    count = cur.fetchone()[0]
    print(f"  [OK] {t[0]:40s} ({count} rows)")
print(f"\n{len(tables)} tabelas criadas com sucesso!")
conn.close()
