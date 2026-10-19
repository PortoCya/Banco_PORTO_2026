"""
Serviço de IA Qualitativa e Cálculo Determinístico de NPS — NPS KeyCore v1.0.
Regras de Ouro do PRD:
  1. O cálculo de NPS é 100% determinístico no backend/banco. LLMs NUNCA participam do cálculo.
  2. Comentários passam por mascaramento de PII (LGPD) antes de qualquer chamada externa à IA.
  3. Falha, timeout ou indisponibilidade da IA (ou Circuit Breaker aberto) NUNCA bloqueia ou desfaz uma Submissão.
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AIError,
    AIQuotaExceededError,
    AIContentFilterError,
    TimeoutError,
    ExternalAPIError,
)
from app.core.security import mascarar_pii
from app.models.models import (
    Submissao,
    JobIa,
    AnaliseFeedback,
    VersaoModelo,
    Prompt,
    EventoCircuitBreaker,
)

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None

TAXONOMIA_TEMAS_FECHADA = {
    "ATENDIMENTO",
    "PRODUTO",
    "PRECO",
    "USABILIDADE",
    "PERFORMANCE",
    "SUPORTE",
    "SEGURANCA",
    "OUTROS",
}


# ══════════════════════════════════════════════════════════════════
# 1. MOTOR DETERMINÍSTICO DE NPS (Sem participação de IA - Pág. 3 e 4 PRD)
# ══════════════════════════════════════════════════════════════════
def classificar_nota_nps(nota: int) -> str:
    """
    Regras do NPS (PRD Pág. 3):
      - Detratores: 0 a 6
      - Neutros: 7 e 8
      - Promotores: 9 e 10
    """
    if nota < 0 or nota > 10:
        raise ValueError("A nota NPS deve ser um inteiro entre 0 e 10.")
    if nota <= 6:
        return "DETRATOR"
    if nota <= 8:
        return "NEUTRO"
    return "PROMOTOR"


def calcular_nps_deterministico(notas: list[int]) -> dict:
    """
    Fórmula oficial (PRD Pág. 4):
      NPS = (% Promotores - % Detratores), arredondado para inteiro na faixa [-100, +100].
    """
    total = len(notas)
    if total == 0:
        return {
            "valor_nps": 0,
            "total_respostas": 0,
            "qtd_promotores": 0,
            "qtd_neutros": 0,
            "qtd_detratores": 0,
            "pct_promotores": 0.0,
            "pct_neutros": 0.0,
            "pct_detratores": 0.0,
        }

    promotores = sum(1 for n in notas if 9 <= n <= 10)
    neutros = sum(1 for n in notas if 7 <= n <= 8)
    detratores = sum(1 for n in notas if 0 <= n <= 6)

    pct_prom = (promotores / total) * 100.0
    pct_neut = (neutros / total) * 100.0
    pct_detr = (detratores / total) * 100.0

    valor_nps = int(round(pct_prom - pct_detr))
    valor_nps = max(-100, min(100, valor_nps))

    return {
        "valor_nps": valor_nps,
        "total_respostas": total,
        "qtd_promotores": promotores,
        "qtd_neutros": neutros,
        "qtd_detratores": detratores,
        "pct_promotores": round(pct_prom, 2),
        "pct_neutros": round(pct_neut, 2),
        "pct_detratores": round(pct_detr, 2),
    }


# ══════════════════════════════════════════════════════════════════
# 2. CLIENTE DE IA (Google Gemini Gratuito ou OpenAI)
# ══════════════════════════════════════════════════════════════════
def _usar_gemini() -> bool:
    if settings.GEMINI_API_KEY:
        return True
    if settings.OPENAI_API_KEY and settings.AI_PROVIDER.lower() == "openai":
        return False
    return settings.AI_PROVIDER.lower() == "gemini"


def get_ai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if _usar_gemini():
            if not settings.GEMINI_API_KEY:
                raise AIError(
                    "Chave GEMINI_API_KEY não configurada no .env. "
                    "Gere gratuitamente em https://aistudio.google.com/app/apikey"
                )
            _client = AsyncOpenAI(
                api_key=settings.GEMINI_API_KEY,
                base_url=settings.GEMINI_BASE_URL,
                timeout=settings.OPENAI_TIMEOUT_SECONDS,
                max_retries=settings.OPENAI_MAX_RETRIES,
            )
        else:
            if not settings.OPENAI_API_KEY:
                raise AIError("Chave OPENAI_API_KEY não configurada no .env.")
            _client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.OPENAI_TIMEOUT_SECONDS,
                max_retries=settings.OPENAI_MAX_RETRIES,
            )
    return _client


async def gerar_resposta_ia(
    prompt_sistema: str,
    mensagem_usuario: str,
    modelo: str = None,
    max_tokens: int = None,
    temperatura: float = 0.2,
) -> dict:
    default_model = settings.GEMINI_MODEL if _usar_gemini() else settings.OPENAI_MODEL
    modelo = modelo or default_model
    max_tokens = max_tokens or settings.MAX_TOKENS_RESPONSE
    client = get_ai_client()

    try:
        resposta = await client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensagem_usuario},
            ],
            max_tokens=max_tokens,
            temperature=temperatura,
        )
    except RateLimitError as exc:
        raise AIQuotaExceededError(f"Limite de quota da IA atingido: {exc}")
    except APITimeoutError as exc:
        raise TimeoutError(f"A IA excedeu o tempo limite: {exc}")
    except APIConnectionError as exc:
        raise ExternalAPIError(f"Erro de conexão com a API de IA: {exc}")
    except Exception as exc:
        raise AIError(f"Erro ao consultar provedor de IA: {exc}")

    escolha = resposta.choices[0] if resposta.choices else None
    if escolha is None:
        raise AIError("A IA retornou lista de choices vazia.")

    if escolha.finish_reason == "content_filter":
        raise AIContentFilterError("Conteúdo bloqueado pelo filtro de segurança da IA.")

    conteudo = getattr(escolha.message, "content", None)
    if not conteudo:
        raise AIError("A IA retornou conteúdo vazio.")

    return {
        "content": conteudo,
        "tokens_entrada": resposta.usage.prompt_tokens if resposta.usage else 0,
        "tokens_saida": resposta.usage.completion_tokens if resposta.usage else 0,
        "modelo_utilizado": resposta.model or modelo,
        "finish_reason": escolha.finish_reason or "stop",
    }


async def analisar_comentario_qualitativo(texto_mascarado: str, prompt_obj: Optional[Prompt] = None, nome_modelo: Optional[str] = None) -> dict:
    """
    Executa análise qualitativa sobre o comentário JÁ MASCARADO contra PII.
    Retorna dicionário validado: sentimento, tema, confianca, justificativa, status.
    """
    temas_str = ", ".join(sorted(TAXONOMIA_TEMAS_FECHADA))
    if prompt_obj:
        prompt_sistema = (
            f"Objetivo: {prompt_obj.objetivo}\n"
            f"Contexto: {prompt_obj.contexto}\n"
            f"Saída esperada: {prompt_obj.saida_esperada}\n"
            f"Taxonomia fechada de temas permitidos: {temas_str}."
        )
    else:
        prompt_sistema = (
            "Você é o motor de análise qualitativa do NPS KeyCore. "
            "Analise o comentário do respondente e retorne APENAS um objeto JSON válido com:\n"
            '{"sentimento": "POSITIVO|NEUTRO|NEGATIVO", '
            f'"tema": "um entre [{temas_str}]", '
            '"confianca": 0.0 a 1.0, '
            '"justificativa": "explicação sucinta sem dados pessoais"}'
        )

    resultado = await gerar_resposta_ia(
        prompt_sistema=prompt_sistema,
        mensagem_usuario=texto_mascarado,
        modelo=nome_modelo,
        temperatura=0.1,
    )
    raw = resultado["content"].strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        dados = json.loads(raw)
        sentimento = str(dados.get("sentimento", "")).upper()
        if sentimento not in {"POSITIVO", "NEUTRO", "NEGATIVO"}:
            raise ValueError(f"Sentimento fora do enum: {sentimento}")
        tema = str(dados.get("tema", "OUTROS")).upper()
        if tema not in TAXONOMIA_TEMAS_FECHADA:
            tema = "OUTROS"
        confianca = float(dados.get("confianca", 0.5))
        confianca = max(0.0, min(1.0, confianca))
        justificativa = str(dados.get("justificativa", ""))[:1000]
        status_analise = "BAIXA_CONFIANCA" if confianca < 0.60 else "CONCLUIDA"
        return {
            "sentimento": sentimento,
            "tema": tema,
            "confianca": confianca,
            "justificativa": justificativa,
            "status": status_analise,
        }
    except Exception as exc:
        logger.warning("Falha de schema na resposta da IA: %s", exc)
        return {
            "sentimento": "NEUTRO",
            "tema": "OUTROS",
            "confianca": 0.0,
            "justificativa": f"Falha ao validar schema JSON da IA: {exc}",
            "status": "FALHA_SCHEMA",
        }


# ══════════════════════════════════════════════════════════════════
# 3. WORKER ASSÍNCRONO DE JOB_IA (Nunca bloqueia ou desfaz Submissao)
# ══════════════════════════════════════════════════════════════════
async def processar_job_ia_background(job_id: str) -> None:
    """
    Processa um JOB_IA em background.
    Verifica Circuit Breaker, aplica mascaramento de PII e grava ANALISE_FEEDBACK.
    """
    from app.core.database import SessionLocal
    db: Session = SessionLocal()
    try:
        job = db.query(JobIa).filter(JobIa.id == job_id).first()
        if not job:
            return

        submissao = db.query(Submissao).filter(Submissao.id == job.id_submissao).first()
        if not submissao or not submissao.texto_comentario:
            job.status = "CONCLUIDO"
            db.commit()
            return

        # 1. Verifica se há Circuit Breaker aberto (proteção financeira/operacional)
        cb_aberto = (
            db.query(EventoCircuitBreaker)
            .filter(EventoCircuitBreaker.resolvido_em.is_(None))
            .first()
        )
        if cb_aberto:
            job.status = "TENTANDO_NOVAMENTE"
            job.tentativas += 1
            job.ultimo_erro = f"Circuit Breaker ativo: {cb_aberto.motivo}"
            job.proxima_tentativa_em = datetime.utcnow() + timedelta(minutes=15)
            db.commit()
            return

        # 2. Segurança LGPD: garante que PII foi mascarado antes de sair para a IA externa
        texto_seguro, status_pii = mascarar_pii(submissao.texto_comentario)
        if status_pii == "FALHA_MASCARAMENTO_PII" or not texto_seguro:
            submissao.status_mascaramento_pii = "FALHA_MASCARAMENTO_PII"
            job.status = "FALHOU"
            job.tentativas += 1
            job.ultimo_erro = "Envio abortado por segurança: falha no mascaramento de PII."
            db.commit()
            return

        job.status = "PROCESSANDO"
        job.tentativas += 1
        db.commit()

        # 3. Busca VersaoModelo ativa e seu Prompt
        versao_ativa = db.query(VersaoModelo).filter(VersaoModelo.ativa == True).first()
        if not versao_ativa:
            job.status = "FALHOU"
            job.ultimo_erro = "Nenhuma VersaoModelo ativa cadastrada."
            db.commit()
            return

        prompt_obj = db.query(Prompt).filter(Prompt.id == versao_ativa.id_prompt).first()

        # 4. Chama a IA
        resultado = await analisar_comentario_qualitativo(
            texto_mascarado=texto_seguro,
            prompt_obj=prompt_obj,
            nome_modelo=versao_ativa.nome_modelo,
        )

        # 5. Calcula sequencia_versao (reprocessamento vira nova versão, não duplica)
        ultima_seq = (
            db.query(AnaliseFeedback)
            .filter(AnaliseFeedback.id_submissao == submissao.id)
            .count()
        )
        analise = AnaliseFeedback(
            id_submissao=submissao.id,
            id_versao_modelo=versao_ativa.id,
            sentimento=resultado["sentimento"],
            tema=resultado["tema"],
            confianca=resultado["confianca"],
            justificativa=resultado["justificativa"],
            sequencia_versao=ultima_seq + 1,
            status=resultado["status"],
        )
        db.add(analise)
        job.status = "CONCLUIDO" if resultado["status"] != "FALHA_SCHEMA" else "TENTANDO_NOVAMENTE"
        job.ultimo_erro = None if resultado["status"] != "FALHA_SCHEMA" else resultado["justificativa"]
        db.commit()

    except Exception as exc:
        logger.warning("Job IA %s falhou sem afetar a submissão primária: %s", job_id, exc)
        db.rollback()
        try:
            job = db.query(JobIa).filter(JobIa.id == job_id).first()
            if job:
                job.status = "TENTANDO_NOVAMENTE" if job.tentativas < 3 else "FALHOU"
                job.ultimo_erro = str(exc)[:500]
                job.proxima_tentativa_em = datetime.utcnow() + timedelta(minutes=5)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
