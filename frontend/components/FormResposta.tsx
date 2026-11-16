"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, carregarPesquisaPublica, enviarResposta, PesquisaPublicaResponse } from "@/lib/api";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronta"; pesquisa: PesquisaPublicaResponse }
  | { tipo: "enviada" }
  | { tipo: "indisponivel"; texto: string };

function textoDoErro(erro: unknown): Estado {
  if (erro instanceof ApiError) {
    if (erro.status === 409) return { tipo: "indisponivel", texto: "Esta pesquisa já foi respondida. Obrigado!" };
    if (erro.status === 403) return { tipo: "indisponivel", texto: "Esta pesquisa não está recebendo respostas no momento." };
    if (erro.status === 404 || erro.status === 422) return { tipo: "indisponivel", texto: "Link de pesquisa inválido." };
  }
  return { tipo: "indisponivel", texto: "Não foi possível carregar a pesquisa. Tente novamente em instantes." };
}

function novaChave(): string {
  // Uma chave por formulário aberto: reenviar após falha de rede usa a mesma,
  // e a API nunca conta a resposta duas vezes.
  // randomUUID só existe em HTTPS/localhost; fora disso usa getRandomValues
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

export default function FormResposta({ token }: { token: string }) {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [nota, setNota] = useState<number | null>(null);
  const [comentario, setComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const chave = useRef<string | null>(null);

  useEffect(() => {
    chave.current = novaChave();
    carregarPesquisaPublica(token)
      .then((pesquisa) => setEstado({ tipo: "pronta", pesquisa }))
      .catch((falha) => setEstado(textoDoErro(falha)));
  }, [token]);

  async function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (nota === null || !chave.current) return;
    setEnviando(true);
    setErro(null);
    try {
      await enviarResposta(token, {
        nota_nps: nota,
        texto_comentario: comentario.trim() || null,
        chave_idempotencia: chave.current,
      });
      setEstado({ tipo: "enviada" });
    } catch (falha) {
      if (falha instanceof ApiError && falha.status === 429) {
        setErro("Muitas tentativas. Aguarde um instante e envie de novo.");
      } else if (falha instanceof ApiError && falha.status === 0) {
        setErro("Sem conexão. Verifique a internet e envie de novo.");
      } else if (falha instanceof ApiError && falha.status === 422) {
        setErro("Confira a nota e o comentário e tente de novo.");
      } else {
        setEstado(textoDoErro(falha));
      }
    } finally {
      setEnviando(false);
    }
  }

  if (estado.tipo === "carregando") {
    return (
      <div className="carregando" aria-live="polite">
        <span className="carregando-spinner" />
        Carregando pesquisa...
      </div>
    );
  }
  if (estado.tipo === "enviada") {
    return (
      <div className="resposta-card resposta-final">
        <h1 className="page-title">Obrigado!</h1>
        <p className="page-text">Sua resposta foi registrada.</p>
      </div>
    );
  }
  if (estado.tipo === "indisponivel") {
    return (
      <div className="resposta-card resposta-final">
        <p className="page-text">{estado.texto}</p>
      </div>
    );
  }

  const { pesquisa } = estado;
  const notas = Array.from(
    { length: pesquisa.nota_maxima - pesquisa.nota_minima + 1 },
    (_, i) => pesquisa.nota_minima + i,
  );

  return (
    <form className="resposta-card" onSubmit={enviar}>
      <h1 className="resposta-titulo">{pesquisa.titulo}</h1>

      <fieldset className="resposta-bloco">
        <legend>{pesquisa.texto_pergunta_nps}</legend>
        <div className="escala-nps" role="radiogroup" aria-label="Nota de 0 a 10">
          {notas.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={nota === n}
              className={`escala-nota faixa-${n >= 9 ? "promotor" : n >= 7 ? "neutro" : "detrator"}${nota === n ? " selecionada" : ""}`}
              onClick={() => setNota(n)}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="escala-legenda">
          <span>Nada provável</span>
          <span>Muito provável</span>
        </div>
      </fieldset>

      {pesquisa.texto_pergunta_aberta && (
        <label className="resposta-bloco">
          {pesquisa.texto_pergunta_aberta} <span className="survey-optional">(opcional)</span>
          <textarea
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            maxLength={pesquisa.comentario_max_caracteres}
            rows={4}
          />
          <small>{comentario.length}/{pesquisa.comentario_max_caracteres}</small>
        </label>
      )}

      {erro && <p className="auth-msg erro" role="alert">{erro}</p>}

      <button className="btn-primario" type="submit" disabled={nota === null || enviando}>
        {enviando ? "Enviando..." : "Enviar resposta"}
      </button>
    </form>
  );
}
