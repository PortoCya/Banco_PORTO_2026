"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  carregarPesquisaPublica,
  enviarSubmissaoPublica,
  PesquisaPublicaResponse,
} from "@/lib/api";

function mensagemErro(erro: unknown, carregandoPesquisa = false) {
  if (!(erro instanceof ApiError)) return "Não foi possível conectar à pesquisa. Verifique sua conexão e tente novamente.";
  if (erro.status === 409) return "Este link já foi utilizado ou esta resposta já foi registrada.";
  if (erro.status === 422) return `Confira os dados da resposta. ${erro.message}`;
  if (erro.status === 404) return "Link de pesquisa inválido ou expirado.";
  if (erro.status === 403 || erro.status === 400) {
    return carregandoPesquisa
      ? "Esta pesquisa não está publicada ou não está recebendo respostas."
      : erro.message;
  }
  return erro.message || "Ocorreu um erro. Tente novamente.";
}

export default function ResponderPesquisa() {
  const params = useParams<{ token: string }>();
  const token = Array.isArray(params.token) ? params.token[0] : params.token;
  const [pesquisa, setPesquisa] = useState<PesquisaPublicaResponse | null>(null);
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [enviada, setEnviada] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const chaveIdempotencia = useRef<string | null>(null);

  useEffect(() => {
    let ativa = true;
    setCarregando(true);
    setErro(null);
    carregarPesquisaPublica(token)
      .then((dados) => {
        if (ativa) setPesquisa(dados);
      })
      .catch((falha: unknown) => {
        if (ativa) setErro(mensagemErro(falha, true));
      })
      .finally(() => {
        if (ativa) setCarregando(false);
      });
    return () => {
      ativa = false;
    };
  }, [token]);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (nota === null) {
      setErro("Selecione uma nota de 0 a 10 para continuar.");
      return;
    }

    setEnviando(true);
    setErro(null);
    try {
      chaveIdempotencia.current ??= crypto.randomUUID();
      await enviarSubmissaoPublica({
        token_link: token,
        nota_nps: nota,
        texto_comentario: comentario.trim() || null,
        chave_idempotencia: chaveIdempotencia.current,
      });
      setEnviada(true);
    } catch (falha) {
      setErro(mensagemErro(falha));
    } finally {
      setEnviando(false);
    }
  }

  if (carregando) {
    return (
      <section className="public-survey-wrap">
        <div className="carregando" aria-live="polite">
          <span className="carregando-spinner" />
          Carregando pesquisa...
        </div>
      </section>
    );
  }

  if (!pesquisa) {
    return (
      <section className="public-survey-wrap">
        <div className="public-survey-card">
          <p className="survey-eyebrow">PESQUISA NPS</p>
          <h1 className="public-survey-title">Não foi possível abrir a pesquisa</h1>
          <p className="survey-alert error" role="alert">{erro ?? "Link inválido ou indisponível."}</p>
        </div>
      </section>
    );
  }

  if (enviada) {
    return (
      <section className="public-survey-wrap">
        <div className="public-survey-card public-success">
          <span className="public-success-icon" aria-hidden="true">✓</span>
          <p className="survey-eyebrow">PESQUISA CONCLUÍDA</p>
          <h1 className="public-survey-title">Resposta registrada com sucesso!</h1>
          <p>Obrigado por compartilhar sua opinião. Ela ajuda a melhorar a experiência.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="public-survey-wrap">
      <article className="public-survey-card">
        <div className="public-progress-heading">
          <span>Passo 1 de 1</span>
          <span>Menos de 30 segundos</span>
        </div>
        <div className="public-progress-track" aria-label="Passo 1 de 1">
          <span />
        </div>

        <p className="survey-eyebrow">PESQUISA DE SATISFAÇÃO</p>
        <h1 className="public-survey-title">{pesquisa.titulo}</h1>

        <form className="public-response-form" onSubmit={enviar}>
          <fieldset className="nps-fieldset">
            <legend>{pesquisa.texto_pergunta_nps}</legend>
            <p className="nps-instruction">Toque na nota que melhor representa sua opinião.</p>
            <div className="nps-scale" role="radiogroup" aria-label="Nota NPS de 0 a 10">
              {Array.from({ length: 11 }, (_, valor) => (
                <button
                  key={valor}
                  type="button"
                  role="radio"
                  aria-checked={nota === valor}
                  className={`nps-score${nota === valor ? " selected" : ""}`}
                  onClick={() => {
                    setNota(valor);
                    setErro(null);
                  }}
                >
                  {valor}
                </button>
              ))}
            </div>
            <div className="nps-scale-labels"><span>Pouco provável</span><span>Muito provável</span></div>
          </fieldset>

          {pesquisa.texto_pergunta_aberta && (
            <label className="public-comment-label">
              {pesquisa.texto_pergunta_aberta} <span>(opcional)</span>
              <textarea
                value={comentario}
                onChange={(e) => setComentario(e.target.value)}
                maxLength={2000}
                rows={4}
                placeholder="Escreva sua resposta aqui..."
              />
              <span className="comment-counter">{comentario.length}/2000 caracteres</span>
            </label>
          )}

          {erro && <p className="survey-alert error" role="alert">{erro}</p>}
          <button className="btn-primario public-submit" type="submit" disabled={enviando || nota === null}>
            {enviando ? "Enviando resposta..." : "Enviar resposta"}
          </button>
          <p className="public-privacy-note">Sua resposta será registrada com segurança.</p>
        </form>
      </article>
    </section>
  );
}