"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  alterarStatusPesquisa,
  ApiError,
  criarPesquisa,
  gerarLinkPesquisa,
  LinkPesquisaResponse,
  listarLinksPesquisa,
  listarPesquisas,
  PesquisaResponse,
  TipoLinkPesquisa,
} from "@/lib/api";

type LinksPorPesquisa = Record<string, LinkPesquisaResponse[]>;
type NichoTemplate = "SUPORTE" | "ECOMMERCE";

function mensagemErro(erro: unknown) {
  if (erro instanceof ApiError) {
    if (erro.status === 401) return "Faça login para acessar a gestão de pesquisas.";
    if (erro.status === 403) return "Esta área exige uma conta com papel ADMIN.";
    return erro.message;
  }
  return "Não foi possível concluir a operação. Tente novamente.";
}

export default function GestaoPesquisas() {
  const [pesquisas, setPesquisas] = useState<PesquisaResponse[]>([]);
  const [links, setLinks] = useState<LinksPorPesquisa>({});
  
  // Estados configurados com os 2 nichos definidos pelo mentor
  const [nichoSelecionado, setNichoSelecionado] = useState<NichoTemplate>("SUPORTE");
  const [titulo, setTitulo] = useState("Pós-atendimento de Suporte — KeyCore");
  const [perguntaNps, setPerguntaNps] = useState(
    "De 0 a 10, o quanto você recomendaria nosso atendimento?",
  );
  const [perguntaAberta, setPerguntaAberta] = useState(
    "Qual é o principal motivo para a sua nota sobre a resolução do chamado?",
  );

  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [acaoId, setAcaoId] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  function aplicarTemplateNicho(tipo: NichoTemplate) {
    setNichoSelecionado(tipo);
    if (tipo === "SUPORTE") {
      setTitulo("Pós-atendimento de Suporte — KeyCore");
      setPerguntaNps("De 0 a 10, o quanto você recomendaria nosso atendimento?");
      setPerguntaAberta(
        "Qual é o principal motivo para a sua nota sobre a resolução do chamado?",
      );
    } else {
      setTitulo("Pós-compra de E-commerce — KeyCore");
      setPerguntaNps(
        "De 0 a 10, o quanto você recomendaria nossa experiência de compra e entrega?",
      );
      setPerguntaAberta(
        "Como foi sua experiência em relação à entrega, ao produto ou ao processo de compra?",
      );
    }
  }

  const carregarDados = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const lista = await listarPesquisas();
      setPesquisas(lista);
      const paresLinks = await Promise.all(
        lista.map(async (pesquisa) => [pesquisa.id, await listarLinksPesquisa(pesquisa.id)] as const),
      );
      setLinks(Object.fromEntries(paresLinks));
    } catch (falha) {
      setErro(mensagemErro(falha));
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregarDados();
  }, [carregarDados]);

  async function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    setSucesso(null);
    try {
      await criarPesquisa({
        titulo: titulo.trim(),
        texto_pergunta_nps: perguntaNps.trim(),
        texto_pergunta_aberta: perguntaAberta.trim() || null,
      });
      setSucesso("Pesquisa criada como rascunho.");
      await carregarDados();
    } catch (falha) {
      setErro(mensagemErro(falha));
    } finally {
      setSalvando(false);
    }
  }

  async function publicar(pesquisa: PesquisaResponse) {
    setAcaoId(pesquisa.id);
    setErro(null);
    setSucesso(null);
    try {
      await alterarStatusPesquisa(pesquisa.id, "PUBLICADA");
      setSucesso(`“${pesquisa.titulo}” está publicada e pronta para receber respostas.`);
      await carregarDados();
    } catch (falha) {
      setErro(mensagemErro(falha));
    } finally {
      setAcaoId(null);
    }
  }

  async function criarLink(pesquisa: PesquisaResponse, tipo: TipoLinkPesquisa) {
    setAcaoId(pesquisa.id);
    setErro(null);
    setSucesso(null);
    try {
      const novoLink = await gerarLinkPesquisa(pesquisa.id, tipo);
      setLinks((atuais) => ({
        ...atuais,
        [pesquisa.id]: [novoLink, ...(atuais[pesquisa.id] ?? [])],
      }));
      setSucesso(`Link ${tipo} gerado para “${pesquisa.titulo}”.`);
    } catch (falha) {
      setErro(mensagemErro(falha));
    } finally {
      setAcaoId(null);
    }
  }

  return (
    <section className="survey-admin">
      <div className="survey-admin-heading">
        <div>
          <p className="survey-eyebrow">PAINEL ADMINISTRATIVO</p>
          <h1 className="page-title">Pesquisas <em>NPS</em></h1>
          <p className="page-text">Crie, publique e compartilhe pesquisas de satisfação.</p>
        </div>
        <Link className="survey-secondary-link" href="/admin/login">Acesso ADMIN</Link>
      </div>

      <section className="survey-panel" aria-labelledby="nova-pesquisa-titulo">
        <h2 id="nova-pesquisa-titulo" className="survey-panel-title">Criar pesquisa</h2>

        <div style={{ marginBottom: "1.25rem" }}>
          <span
            style={{
              display: "block",
              fontSize: "0.875rem",
              fontWeight: 600,
              marginBottom: "0.5rem",
              color: "#1e3a8a",
            }}
          >
            Escolha o modelo de nicho da pesquisa:
          </span>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className={nichoSelecionado === "SUPORTE" ? "btn-primario" : "survey-outline-button"}
              onClick={() => aplicarTemplateNicho("SUPORTE")}
            >
              1. Pós-atendimento de suporte
            </button>
            <button
              type="button"
              className={nichoSelecionado === "ECOMMERCE" ? "btn-primario" : "survey-outline-button"}
              onClick={() => aplicarTemplateNicho("ECOMMERCE")}
            >
              2. Pós-compra de e-commerce
            </button>
          </div>
        </div>

        <form className="survey-form" onSubmit={criar}>
          <label>
            Título
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              required
              minLength={3}
              maxLength={300}
              placeholder="Ex.: Pós-atendimento de suporte"
            />
          </label>
          <label>
            Pergunta NPS
            <textarea
              value={perguntaNps}
              onChange={(e) => setPerguntaNps(e.target.value)}
              required
              minLength={5}
              maxLength={1000}
              rows={3}
            />
          </label>
          <label>
            Pergunta aberta <span className="survey-optional">(opcional)</span>
            <textarea
              value={perguntaAberta}
              onChange={(e) => setPerguntaAberta(e.target.value)}
              maxLength={1000}
              rows={2}
              placeholder="Qual é o principal motivo para a sua nota?"
            />
          </label>
          <button className="btn-primario survey-submit" type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Criar rascunho"}
          </button>
        </form>
      </section>

      {erro && (
        <p className="survey-alert error" role="alert">
          {erro} {erro.includes("Faça login") && <Link href="/admin/login">Entrar</Link>}
        </p>
      )}
      {sucesso && <p className="survey-alert success" role="status">{sucesso}</p>}

      <section className="survey-list" aria-labelledby="lista-pesquisas-titulo">
        <div className="survey-list-heading">
          <div>
            <p className="survey-eyebrow">SUAS PESQUISAS</p>
            <h2 id="lista-pesquisas-titulo" className="survey-panel-title">Gestão e links</h2>
          </div>
          <button className="survey-refresh" type="button" onClick={() => void carregarDados()} disabled={carregando}>
            Atualizar lista
          </button>
        </div>

        {carregando ? (
          <div className="carregando" aria-live="polite">
            <span className="carregando-spinner" />
            Carregando pesquisas...
          </div>
        ) : pesquisas.length === 0 ? (
          <div className="survey-empty">Nenhuma pesquisa cadastrada. Crie seu primeiro rascunho acima.</div>
        ) : (
          <div className="survey-cards">
            {pesquisas.map((pesquisa) => (
              <article className="survey-card" key={pesquisa.id}>
                <div className="survey-card-heading">
                  <div>
                    <h3>{pesquisa.titulo}</h3>
                    <p>{pesquisa.texto_pergunta_nps}</p>
                  </div>
                  <span className={`survey-status ${pesquisa.status.toLowerCase()}`}>{pesquisa.status}</span>
                </div>
                <p className="survey-version">Versão {pesquisa.numero_versao}</p>
                <div className="survey-actions">
                  {pesquisa.status !== "PUBLICADA" && pesquisa.status !== "ARQUIVADA" && (
                    <button
                      className="btn-primario"
                      type="button"
                      disabled={acaoId === pesquisa.id}
                      onClick={() => void publicar(pesquisa)}
                    >
                      {acaoId === pesquisa.id ? "Processando..." : "Publicar"}
                    </button>
                  )}
                  <button
                    className="survey-outline-button"
                    type="button"
                    disabled={acaoId === pesquisa.id}
                    onClick={() => void criarLink(pesquisa, "ABERTO")}
                  >
                    Gerar link aberto
                  </button>
                  <button
                    className="survey-outline-button"
                    type="button"
                    disabled={acaoId === pesquisa.id}
                    onClick={() => void criarLink(pesquisa, "NOMINAL")}
                  >
                    Gerar link nominal
                  </button>
                </div>
                {(links[pesquisa.id] ?? []).length > 0 && (
                  <div className="survey-links">
                    <h4>Links de resposta</h4>
                    {(links[pesquisa.id] ?? []).map((link) => {
                      const url = `/pesquisa/${encodeURIComponent(link.token)}`;
                      return (
                        <div className="survey-link-row" key={link.id}>
                          <span className={`survey-link-type ${link.tipo.toLowerCase()}`}>{link.tipo}</span>
                          <Link href={url} target="_blank" rel="noreferrer">{url}</Link>
                          {link.tipo === "NOMINAL" && link.usado_em && <span className="survey-link-used">Já utilizado</span>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}