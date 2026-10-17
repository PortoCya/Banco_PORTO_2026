"""
Lista as tabelas do banco e quantas linhas cada uma tem.
Execute: python check_db.py
"""
from dotenv import load_dotenv
from sqlalchemy import func, inspect, select, table

load_dotenv()

from app.core.database import engine  # noqa: E402 — depende do .env carregado

insp = inspect(engine)
tabelas = sorted(insp.get_table_names())
with engine.connect() as conn:
    for nome in tabelas:
        # table() faz o quoting do nome; nada de SQL montado com f-string
        count = conn.execute(select(func.count()).select_from(table(nome))).scalar_one()
        print(f"  [OK] {nome:40s} ({count} rows)")
print(f"\n{len(tabelas)} tabelas encontradas.")
