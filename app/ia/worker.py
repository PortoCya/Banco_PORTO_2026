"""
Worker de IA — processo separado da API.

    python -m app.ia.worker

Fala com a API só por fila (Redis Streams, que carrega apenas ids) e banco.
A fonte da verdade é a tabela JOB_IA: se o Redis cair ou uma mensagem se
perder, a varredura periódica encontra o job. Nada daqui toca em nota ou NPS;
toda falha vira ESTADO (JOB_IA / ANALISE_FEEDBACK / EVENTO_CIRCUIT_BREAKER),
nunca erro propagado ao núcleo.

Repetição: só erro transitório do provedor (timeout, rede, 429, 5xx) volta
para a fila, com backoff exponencial, até IA_MAX_TENTATIVAS. Erro permanente
(4xx, saída fora do schema, falha ao mascarar PII) não é repetido.
"""
import logging
import os
import signal
import socket
import time
import uuid
from datetime import timedelta
from typing import Optional

import redis
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.core.config import settings
from app.core.database import criar_engine
from app.core.logs import configurar_logs, definir_request_id, restaurar_request_id
from app.core.redis import get_redis
from app.ia.analise import justificativa_segura, montar_prompt, validar_saida
from app.ia.provedor import ErroPermanente, ErroTransitorio, ProvedorHTTP, ProvedorIA
from app.models.models import (
    AnaliseFeedback, AvaliacaoGoldenSet, ComentarioGoldenSet, EventoCircuitBreaker,
    JobIa, Submissao, VersaoModelo, agora_utc,
)
from app.services import custo_ia, golden_set
from app.services.fila import GRUPO_WORKERS, STREAM_ANALISES, STREAM_AVALIACOES
from app.services.pii import mascarar_pii

logger = logging.getLogger("nps.worker")

_ESPERA_SEM_MODELO = timedelta(minutes=10)
_ESPERA_CIRCUIT_BREAKER = timedelta(minutes=15)
_LOTE_VARREDURA = 50


# ══════════════════════════════════════════════════════════════════
# Um job
# ══════════════════════════════════════════════════════════════════

def backoff(tentativas: int) -> timedelta:
    """30s, 60s, 120s... limitado a IA_BACKOFF_MAX_SEGUNDOS."""
    segundos = settings.IA_BACKOFF_BASE_SEGUNDOS * 2 ** max(tentativas - 1, 0)
    return timedelta(seconds=min(segundos, settings.IA_BACKOFF_MAX_SEGUNDOS))


def _reivindicar(db: Session, id_job: uuid.UUID) -> bool:
    """UPDATE condicional: entre dois workers, só um fica com o job."""
    agora = agora_utc()
    pegou = db.execute(
        update(JobIa)
        .where(
            JobIa.id == id_job,
            or_(
                JobIa.status.in_(("NA_FILA", "TENTANDO_NOVAMENTE")),
                # PROCESSANDO com lease vencido = worker anterior morreu no meio
                (JobIa.status == "PROCESSANDO") & (JobIa.proxima_tentativa_em < agora),
            ),
        )
        .values(
            status="PROCESSANDO",
            tentativas=JobIa.tentativas + 1,
            proxima_tentativa_em=agora + timedelta(seconds=settings.IA_LEASE_SEGUNDOS),
        )
    ).rowcount
    db.commit()
    return pegou == 1


def _adiar(db: Session, job: JobIa, espera: timedelta, motivo: str) -> None:
    """Devolve à fila sem gastar tentativa (a culpa não é do job)."""
    job.status = "NA_FILA"
    job.tentativas = max(job.tentativas - 1, 0)
    job.proxima_tentativa_em = agora_utc() + espera
    job.ultimo_erro = motivo[:500]
    db.commit()


def _versao_ativa(db: Session) -> Optional[VersaoModelo]:
    return db.execute(
        select(VersaoModelo).where(VersaoModelo.ativo.is_(True)).options(joinedload(VersaoModelo.prompt))
    ).scalar_one_or_none()


def _orcamento_liberado(db: Session) -> tuple[bool, str]:
    """Confere circuit breaker e orçamento. Abre o evento se o limite estourou."""
    if custo_ia.evento_aberto(db) is not None:
        return False, "Circuit breaker aberto: envios pausados."
    if get_redis() is None:
        return True, ""     # sem Redis não há controle de custo (aviso na subida)
    try:
        acumulado, limite = custo_ia.custo_acumulado(), custo_ia.obter_limite()
    except custo_ia.CustoIndisponivel:
        # Sem conseguir ler o orçamento, não gasta
        return False, "Contador de custo indisponível."
    if acumulado >= limite:
        db.add(EventoCircuitBreaker(
            motivo="Orçamento mensal da IA atingido.",
            custo_acumulado=acumulado,
            limite_custo=limite,
        ))
        db.commit()
        logger.error("Circuit breaker ABERTO: custo %.4f >= limite %.4f", acumulado, limite)
        return False, "Circuit breaker aberto: orçamento atingido."
    return True, ""


def _nova_analise(db: Session, id_submissao: uuid.UUID, id_versao: uuid.UUID, **campos) -> None:
    ultima = db.execute(
        select(func.max(AnaliseFeedback.sequencia_versao)).where(AnaliseFeedback.id_submissao == id_submissao)
    ).scalar()
    db.add(AnaliseFeedback(
        id_submissao=id_submissao,
        id_versao_modelo=id_versao,
        sequencia_versao=(ultima or 0) + 1,
        **campos,
    ))


def _registrar_custo(resposta) -> None:
    try:
        custo_ia.somar_custo(resposta.tokens_entrada, resposta.tokens_saida)
    except custo_ia.CustoIndisponivel:
        logger.warning("Custo da chamada não contabilizado (Redis indisponível)")


def processar_job(db: Session, provedor: ProvedorIA, id_job: uuid.UUID) -> None:
    """Processa um JOB_IA. Nunca levanta exceção para quem chama."""
    contexto = definir_request_id(f"job-{id_job.hex[:12]}")
    try:
        if not _reivindicar(db, id_job):
            return
        _processar(db, provedor, db.get(JobIa, id_job))
        logger.info("Job finalizado")
    except SQLAlchemyError as exc:
        # Banco oscilou: o job fica PROCESSANDO e volta sozinho quando o lease vencer
        db.rollback()
        logger.error("Erro de banco no job (%s); será retomado após o lease", type(exc).__name__)
    except Exception as exc:
        db.rollback()
        logger.exception("Erro inesperado no job")
        try:
            job = db.get(JobIa, id_job)
            job.status = "FALHOU"
            job.ultimo_erro = f"Erro inesperado: {type(exc).__name__}"
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    finally:
        restaurar_request_id(contexto)


def _processar(db: Session, provedor: ProvedorIA, job: JobIa) -> None:
    if job.tentativas > settings.IA_MAX_TENTATIVAS:
        job.status, job.ultimo_erro = "FALHOU", "Número máximo de tentativas atingido."
        db.commit()
        return

    submissao = db.get(Submissao, job.id_submissao)
    if submissao.status != "VALIDA" or not (submissao.texto_comentario or "").strip():
        job.status, job.proxima_tentativa_em = "CONCLUIDO", None     # nada a analisar
        db.commit()
        return

    versao = _versao_ativa(db)
    if versao is None:
        _adiar(db, job, _ESPERA_SEM_MODELO, "Nenhuma VERSAO_MODELO ativa.")
        return

    liberado, motivo = _orcamento_liberado(db)
    if not liberado:
        _adiar(db, job, _ESPERA_CIRCUIT_BREAKER, motivo)
        return

    # PII: obrigatório antes de qualquer envio. Na dúvida, o texto não sai.
    mascarado = mascarar_pii(submissao.texto_comentario)
    submissao.status_mascaramento_pii = mascarado.status
    if not mascarado.seguro:
        _nova_analise(db, submissao.id, versao.id, status="PENDENTE")
        job.status, job.proxima_tentativa_em = "FALHOU", None
        job.ultimo_erro = "FALHA_MASCARAMENTO_PII: comentário não enviado ao provedor."
        db.commit()
        return
    db.commit()

    mensagens = montar_prompt(versao.prompt, mascarado.texto)
    try:
        resposta = provedor.completar(
            modelo=versao.nome_modelo, sistema=mensagens.sistema, usuario=mensagens.usuario
        )
    except ErroTransitorio as exc:
        if job.tentativas >= settings.IA_MAX_TENTATIVAS:
            job.status, job.proxima_tentativa_em = "FALHOU", None
        else:
            job.status = "TENTANDO_NOVAMENTE"
            job.proxima_tentativa_em = agora_utc() + backoff(job.tentativas)
        job.ultimo_erro = str(exc)[:500]
        db.commit()
        return
    except ErroPermanente as exc:
        job.status, job.proxima_tentativa_em = "FALHOU", None
        job.ultimo_erro = str(exc)[:500]
        db.commit()
        return

    _registrar_custo(resposta)

    saida = validar_saida(resposta.texto)
    if saida is None:
        _nova_analise(db, submissao.id, versao.id, status="FALHA_SCHEMA")
        job.status, job.proxima_tentativa_em = "FALHOU", None
        job.ultimo_erro = "FALHA_SCHEMA: saída do modelo fora do formato."
    else:
        _nova_analise(
            db, submissao.id, versao.id,
            sentimento=saida.sentimento,
            tema=saida.tema,
            confianca=saida.confianca,
            justificativa=justificativa_segura(saida.justificativa),
            status="CONCLUIDA" if saida.confianca >= settings.IA_CONFIANCA_MINIMA else "BAIXA_CONFIANCA",
        )
        job.status, job.proxima_tentativa_em, job.ultimo_erro = "CONCLUIDO", None, None
    db.commit()


# ══════════════════════════════════════════════════════════════════
# Avaliação no golden set
# ══════════════════════════════════════════════════════════════════

def _ultima_avaliacao(db: Session, id_versao: uuid.UUID) -> Optional[AvaliacaoGoldenSet]:
    return db.execute(
        select(AvaliacaoGoldenSet)
        .where(AvaliacaoGoldenSet.id_versao_modelo == id_versao)
        .order_by(AvaliacaoGoldenSet.executada_em.desc())
        .limit(1)
    ).scalar_one_or_none()


def _classificar_com_repeticao(provedor: ProvedorIA, versao: VersaoModelo, texto: str):
    for tentativa in range(1, 4):
        try:
            mensagens = montar_prompt(versao.prompt, texto)
            return provedor.completar(modelo=versao.nome_modelo, sistema=mensagens.sistema, usuario=mensagens.usuario)
        except ErroTransitorio:
            if tentativa == 3:
                raise
            time.sleep(min(2 ** tentativa, 10))


def executar_avaliacao(db: Session, provedor: ProvedorIA, id_versao: uuid.UUID) -> Optional[AvaliacaoGoldenSet]:
    """
    Roda o golden set inteiro na versão e grava AVALIACAO_GOLDEN_SET.
    Se o provedor ficar indisponível no meio, nada é gravado (avaliação
    incompleta não aprova nem reprova ninguém).
    """
    contexto = definir_request_id(f"avaliacao-{id_versao.hex[:12]}")
    try:
        return _avaliar(db, provedor, id_versao)
    finally:
        restaurar_request_id(contexto)


def _avaliar(db: Session, provedor: ProvedorIA, id_versao: uuid.UUID) -> Optional[AvaliacaoGoldenSet]:
    versao = db.execute(
        select(VersaoModelo).where(VersaoModelo.id == id_versao).options(joinedload(VersaoModelo.prompt))
    ).scalar_one_or_none()
    comentarios = db.execute(select(ComentarioGoldenSet)).scalars().all()
    if versao is None or len(comentarios) < settings.GOLDEN_SET_MINIMO:
        logger.error("Avaliação ignorada: versão inexistente ou golden set incompleto")
        return None

    pares = []
    for c in comentarios:
        mascarado = mascarar_pii(c.texto_comentario)
        saida = None
        if mascarado.seguro:
            try:
                resposta = _classificar_com_repeticao(provedor, versao, mascarado.texto)
            except ErroTransitorio:
                logger.error("Avaliação abortada: provedor indisponível")
                return None
            except ErroPermanente as exc:
                logger.error("Avaliação abortada: %s", exc)
                return None
            _registrar_custo(resposta)
            saida = validar_saida(resposta.texto)
        pares.append(golden_set.Par(
            c.rotulo_sentimento_humano, c.rotulo_tema_humano,
            saida.sentimento if saida else None, saida.tema if saida else None,
        ))

    metricas = golden_set.calcular_metricas(pares)
    ativa = _versao_ativa(db)
    anterior = _ultima_avaliacao(db, ativa.id) if ativa is not None and ativa.id != versao.id else None
    avaliacao = AvaliacaoGoldenSet(
        id_versao_modelo=versao.id,
        acuracia_sentimento=metricas.acuracia_sentimento,
        acuracia_tema=metricas.acuracia_tema,
        taxa_falso_positivo=metricas.taxa_falso_positivo,
        status=golden_set.decidir(
            metricas,
            golden_set.Metricas(anterior.acuracia_sentimento, anterior.acuracia_tema, anterior.taxa_falso_positivo)
            if anterior else None,
        ),
    )
    db.add(avaliacao)
    db.commit()
    logger.info("Avaliação concluída: %s", avaliacao.status)
    return avaliacao


# ══════════════════════════════════════════════════════════════════
# Laço principal
# ══════════════════════════════════════════════════════════════════

def jobs_pendentes(db: Session, limite: int = _LOTE_VARREDURA) -> list[uuid.UUID]:
    return list(db.execute(
        select(JobIa.id)
        .where(
            JobIa.status.in_(("NA_FILA", "TENTANDO_NOVAMENTE", "PROCESSANDO")),
            JobIa.proxima_tentativa_em <= agora_utc(),
        )
        .order_by(JobIa.proxima_tentativa_em)
        .limit(limite)
    ).scalars())


def _garantir_grupos(r: redis.Redis) -> None:
    for stream in (STREAM_ANALISES, STREAM_AVALIACOES):
        try:
            r.xgroup_create(stream, GRUPO_WORKERS, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


def _ler_fila(r: redis.Redis, consumidor: str, espera_ms: int) -> list[tuple[str, str, dict]]:
    # A espera bloqueante precisa caber dentro do timeout do socket do Redis,
    # senão toda leitura sem mensagem viraria um falso "Redis fora do ar".
    espera_ms = max(1, min(espera_ms, int(settings.REDIS_TIMEOUT_SEGUNDOS * 500)))
    lidas = r.xreadgroup(
        GRUPO_WORKERS, consumidor, {STREAM_ANALISES: ">", STREAM_AVALIACOES: ">"},
        count=10, block=espera_ms,
    )
    return [(stream, id_msg, campos) for stream, mensagens in (lidas or []) for id_msg, campos in mensagens]


def executar_ciclo(fabrica_sessao: sessionmaker, provedor: ProvedorIA, consumidor: str, espera_ms: int = 2000) -> int:
    """Um ciclo: lê a fila (se houver Redis) e varre o banco. Devolve quantos itens tratou."""
    tratados = 0
    r = get_redis()
    mensagens: list[tuple[str, str, dict]] = []
    if r is not None:
        try:
            _garantir_grupos(r)
            mensagens = _ler_fila(r, consumidor, espera_ms)
        except redis.RedisError as exc:
            logger.warning("Fila indisponível (%s); seguindo só pela varredura do banco", type(exc).__name__)
            time.sleep(espera_ms / 1000)
    else:
        time.sleep(espera_ms / 1000)

    with fabrica_sessao() as db:
        for stream, id_msg, campos in mensagens:
            try:
                if stream == STREAM_AVALIACOES:
                    executar_avaliacao(db, provedor, uuid.UUID(campos["id_versao_modelo"]))
                else:
                    id_submissao = uuid.UUID(campos["id_submissao"])
                    for id_job in db.execute(select(JobIa.id).where(JobIa.id_submissao == id_submissao)).scalars():
                        processar_job(db, provedor, id_job)
            except (KeyError, ValueError):
                logger.warning("Mensagem inválida descartada (stream=%s)", stream)
            except SQLAlchemyError as exc:
                db.rollback()
                logger.error("Erro de banco ao tratar mensagem (%s)", type(exc).__name__)
            finally:
                tratados += 1
                try:
                    r.xack(stream, GRUPO_WORKERS, id_msg)
                except redis.RedisError:
                    pass

        try:
            for id_job in jobs_pendentes(db):
                processar_job(db, provedor, id_job)
                tratados += 1
        except SQLAlchemyError as exc:
            db.rollback()
            logger.error("Erro de banco na varredura (%s)", type(exc).__name__)
    return tratados


def main() -> None:
    configurar_logs(settings.DEBUG)
    if not settings.IA_API_KEY:
        raise SystemExit("IA_API_KEY não definida: o worker de IA não sobe sem a chave do provedor.")
    if get_redis() is None:
        logger.warning("REDIS_URL não definido: sem fila (só varredura do banco) e SEM controle de custo.")
    if not settings.WORKER_DATABASE_URL:
        logger.warning("WORKER_DATABASE_URL não definido: usando o usuário de banco da API (só para desenvolvimento).")

    engine = criar_engine(settings.WORKER_DATABASE_URL or settings.DATABASE_URL, nome_aplicacao="nps-worker-ia")
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    provedor = ProvedorHTTP(settings.IA_BASE_URL, settings.IA_API_KEY)
    consumidor = f"{socket.gethostname()}-{os.getpid()}"

    rodando = True

    def _parar(*_):
        nonlocal rodando
        rodando = False
        logger.info("Sinal recebido: terminando o ciclo atual e saindo.")

    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)

    logger.info("Worker de IA iniciado (consumidor=%s)", consumidor)
    while rodando:
        try:
            executar_ciclo(fabrica, provedor, consumidor)
        except Exception:
            logger.exception("Falha no ciclo do worker; tentando de novo em 5s")
            time.sleep(5)
    provedor.fechar()
    engine.dispose()


if __name__ == "__main__":
    main()
