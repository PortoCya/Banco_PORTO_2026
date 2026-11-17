"""
Confere o banco configurado em DATABASE_URL: revisão do Alembic e linhas por tabela.

    python check_db.py
"""
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import func, inspect, select, text  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
import app.models.models  # noqa: E402,F401


def main() -> None:
    existentes = set(inspect(engine).get_table_names())
    with engine.connect() as conexao:
        revisao = (
            conexao.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if "alembic_version" in existentes else None
        )
        print(f"Revisão do Alembic: {revisao or 'NENHUMA — rode: alembic upgrade head'}")
        # Só tabelas conhecidas do metadata, sempre via SQLAlchemy: nenhum nome
        # vindo de fora é concatenado em SQL.
        for nome, tabela in sorted(Base.metadata.tables.items()):
            if nome not in existentes:
                print(f"  [FALTA] {nome}")
                continue
            total = conexao.execute(select(func.count()).select_from(tabela)).scalar_one()
            print(f"  [OK] {nome:28s} {total} linha(s)")


if __name__ == "__main__":
    main()
