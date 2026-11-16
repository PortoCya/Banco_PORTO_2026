const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
  papel: string;
  usuario_id: string;
};

export type StatusPesquisa = "RASCUNHO" | "PUBLICADA" | "PAUSADA" | "ARQUIVADA";
export type TipoLinkPesquisa = "NOMINAL" | "ABERTO";

export type PesquisaCreate = {
  titulo: string;
  texto_pergunta_nps?: string;
  texto_pergunta_aberta?: string | null;
};

export type PesquisaResponse = {
  id: string;
  titulo: string;
  texto_pergunta_nps: string;
  texto_pergunta_aberta: string | null;
  status: StatusPesquisa;
  numero_versao: number;
  id_pesquisa_pai: string | null;
  criado_por: string;
  criada_em: string;
  atualizada_em: string;
};

export type LinkPesquisaResponse = {
  id: string;
  id_pesquisa: string;
  tipo: TipoLinkPesquisa;
  token: string;
  usado_em: string | null;
  criado_em: string;
};

export type PesquisaPublicaResponse = {
  id_pesquisa: string;
  titulo: string;
  texto_pergunta_nps: string;
  texto_pergunta_aberta: string | null;
  tipo_link: TipoLinkPesquisa;
  escala_nps: { min: number; max: number };
};

export type SubmissaoPublicaCreate = {
  token_link: string;
  nota_nps: number;
  texto_comentario: string | null;
  chave_idempotencia: string;
  fingerprint_dispositivo?: string | null;
};

export type SubmissaoResponse = {
  id: string;
  id_pesquisa: string;
  id_link_pesquisa: string | null;
  nota_nps: number;
  classificacao_nps: string | null;
  texto_comentario: string | null;
  chave_idempotencia: string;
  status: string;
  status_mascaramento_pii: string;
  criada_em: string;
};

type ErroApi = {
  error?: { code?: string; message?: string };
  detail?: string | Array<{ msg?: string }>;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function requisitar<T>(caminho: string, init: RequestInit): Promise<T> {
  let resposta: Response;
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (typeof window !== "undefined") {
    const token = window.sessionStorage.getItem("token");
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  try {
    resposta = await fetch(`${API_URL}/api/v1${caminho}`, {
      ...init,
      headers,
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    throw new ApiError(0, "Não foi possível conectar ao servidor.");
  }

  if (!resposta.ok) {
    const corpo = (await resposta.json().catch(() => ({}))) as ErroApi;
    const detalhe = Array.isArray(corpo.detail)
      ? corpo.detail.map((item) => item.msg).filter(Boolean).join(" ")
      : corpo.detail;
    throw new ApiError(
      resposta.status,
      corpo.error?.message ?? detalhe ?? "Erro inesperado.",
    );
  }
  return (await resposta.json()) as T;
}

export function login(email: string, senha: string) {
  return requisitar<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

export function criarPesquisa(dados: PesquisaCreate) {
  return requisitar<PesquisaResponse>("/surveys", {
    method: "POST",
    body: JSON.stringify(dados),
  });
}

export function listarPesquisas() {
  return requisitar<PesquisaResponse[]>("/surveys", { method: "GET" });
}

export function alterarStatusPesquisa(pesquisaId: string, novoStatus: StatusPesquisa) {
  return requisitar<PesquisaResponse>(
    `/surveys/${encodeURIComponent(pesquisaId)}/status/${encodeURIComponent(novoStatus)}`,
    { method: "POST" },
  );
}

export function gerarLinkPesquisa(pesquisaId: string, tipo: TipoLinkPesquisa) {
  return requisitar<LinkPesquisaResponse>(
    `/surveys/${encodeURIComponent(pesquisaId)}/links`,
    { method: "POST", body: JSON.stringify({ tipo }) },
  );
}

export function listarLinksPesquisa(pesquisaId: string) {
  return requisitar<LinkPesquisaResponse[]>(
    `/surveys/${encodeURIComponent(pesquisaId)}/links`,
    { method: "GET" },
  );
}

export function carregarPesquisaPublica(token: string) {
  return requisitar<PesquisaPublicaResponse>(
    `/public/surveys/${encodeURIComponent(token)}`,
    { method: "GET" },
  );
}

export function enviarSubmissaoPublica(dados: SubmissaoPublicaCreate) {
  return requisitar<SubmissaoResponse>("/public/submissions", {
    method: "POST",
    headers: { "X-Idempotency-Key": dados.chave_idempotencia },
    body: JSON.stringify(dados),
  });
}

export function salvarToken(token: string) {
  try {
    sessionStorage.setItem("token", token);
  } catch {}
}
