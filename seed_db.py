"""
Dados iniciais (idempotente — pode rodar de novo sem duplicar nada).

    alembic upgrade head      # o schema vem das migrations, não daqui
    python seed_db.py         # primeiro ADMIN + prompt e versão de modelo iniciais
    python seed_db.py --demo  # também cria uma pesquisa publicada com link ABERTO
    python seed_db.py --demo --demo-token nps-keycore-2026   # link de teste fixo (só em dev)

O primeiro ADMIN vem de ADMIN_EMAIL / ADMIN_SENHA no ambiente (.env). Nenhuma
senha fica no código nem aparece no log.
"""
import argparse
import logging
import os
import re
import secrets
import sys

from dotenv import load_dotenv

load_dotenv()

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import gerar_hash_senha  # noqa: E402
from app.models.models import LinkPesquisa, Pesquisa, Prompt, Usuario, VersaoModelo  # noqa: E402
from app.schemas.schemas import UsuarioCreate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

TITULO_DEMO = "Pesquisa de Satisfação KeyCore (demonstração)"


def _admin_do_ambiente() -> UsuarioCreate:
    try:
        return UsuarioCreate(
            nome=os.environ.get("ADMIN_NOME", "Administrador"),
            email=os.environ.get("ADMIN_EMAIL", ""),
            senha=os.environ.get("ADMIN_SENHA", ""),
            papel="ADMIN",
        )
    except ValidationError as exc:
        campos = sorted({str(e["loc"][0]) for e in exc.errors()})
        sys.exit(f"Defina ADMIN_EMAIL e ADMIN_SENHA (12 a 128 caracteres) no .env. Inválido: {', '.join(campos)}")


def _garantir_demo(db, admin: Usuario, demo_token: str | None) -> None:
    """Pesquisa publicada + link ABERTO para testar o fluxo do respondente. Idempotente."""
    pesquisa = db.execute(select(Pesquisa).where(Pesquisa.titulo == TITULO_DEMO)).scalar_one_or_none()
    if pesquisa is None:
        pesquisa = Pesquisa(
            titulo=TITULO_DEMO,
            texto_pergunta_nps="Em uma escala de 0 a 10, o quanto você recomendaria a KeyCore?",
            texto_pergunta_aberta="Qual foi o principal motivo para a sua nota?",
            status="PUBLICADA",
            criado_por=admin.id,
        )
        db.add(pesquisa)
        db.flush()
        logger.info("Pesquisa de demonstração publicada.")

    if demo_token:
        link = db.execute(select(LinkPesquisa).where(LinkPesquisa.token == demo_token)).scalar_one_or_none()
        if link is not None and link.id_pesquisa != pesquisa.id:
            sys.exit(f"O token '{demo_token}' já pertence a outra pesquisa. Escolha outro.")
    else:
        link = db.execute(
            select(LinkPesquisa)
            .where(LinkPesquisa.id_pesquisa == pesquisa.id, LinkPesquisa.tipo == "ABERTO")
            .order_by(LinkPesquisa.criado_em.desc())
            .limit(1)
        ).scalar_one_or_none()
    if link is None:
        link = LinkPesquisa(id_pesquisa=pesquisa.id, tipo="ABERTO",
                            token=demo_token or secrets.token_urlsafe(24))
        db.add(link)
    logger.info("Link público de teste: /pesquisa/%s", link.token)


def popular(demo: bool, demo_token: str | None = None) -> None:
    dados = _admin_do_ambiente()
    with SessionLocal() as db:
        admin = db.execute(select(Usuario).where(Usuario.email == dados.email)).scalar_one_or_none()
        if admin is None:
            admin = Usuario(nome=dados.nome, email=dados.email,
                            senha_hash=gerar_hash_senha(dados.senha), papel="ADMIN")
            db.add(admin)
            db.flush()
            logger.info("ADMIN criado: %s", dados.email)
        else:
            logger.info("ADMIN já existe: %s (senha não alterada)", dados.email)

        if db.execute(select(Prompt.id).limit(1)).first() is None:
            prompt = Prompt(
                objetivo="Classificar o sentimento e o tema de comentários de pesquisas de satisfação (NPS).",
                contexto="Comentários livres, em português, de clientes da KeyCore. Dados pessoais já vêm mascarados.",
                saida_esperada="JSON com sentimento, tema, confianca e justificativa curta.",
            )
            db.add(prompt)
            db.flush()
            # Nasce INATIVA: só ativa depois de aprovada no golden set
            # (POST /golden-set/avaliacoes e POST /modelos-ia/{id}/ativar).
            db.add(VersaoModelo(provedor="Google Gemini", nome_modelo="gemini-2.5-flash",
                                rotulo_versao="gemini-2.5-flash-v1", id_prompt=prompt.id, ativo=False))
            logger.info("Prompt e versão de modelo iniciais criados (modelo inativo até passar no golden set).")

        if demo:
            _garantir_demo(db, admin, demo_token)

        db.commit()   # tudo ou nada


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Popula os dados iniciais.")
    parser.add_argument("--demo", action="store_true", help="cria também uma pesquisa de demonstração")
    parser.add_argument("--demo-token", metavar="TOKEN",
                        help="token fixo para o link ABERTO da demonstração (só desenvolvimento; "
                             "8 a 128 caracteres: letras, números, _ ou -)")
    args = parser.parse_args()
    if args.demo_token is not None and not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", args.demo_token):
        sys.exit("--demo-token inválido: use 8 a 128 caracteres (letras, números, _ ou -).")
    popular(args.demo, args.demo_token)
