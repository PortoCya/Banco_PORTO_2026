/**
 * Cliente da API (FastAPI, rotas sob /api/v1).
 *
 * Os tipos abaixo espelham os schemas do backend (app/schemas/schemas.py):
 * nome do campo = nome da coluna. Mudou um schema lá, mude aqui.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHAVE_TOKEN = "token";

// ─── Tipos ───────────────────────────────────────────────────────────────────

export type Papel = "ADMIN" | "ANALYST";
export type StatusPesquisa = "RASCUNHO" | "PUBLICADA" | "PAUSADA" | "ARQUIVADA";
export type TipoLinkPesquisa = "NOMINAL" | "ABERTO";

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export type UsuarioResponse = {
  id: string;
  nome: string;
  email: string;
  papel: Papel;
  ativo: boolean;
  criado_em: string;
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

export type PesquisaCreate = {
  titulo: string;
  texto_pergunta_nps: string;
  texto_pergunta_aberta?: string | null;
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
  titulo: string;
  texto_pergunta_nps: string;
  texto_pergunta_aberta: string | null;
  tipo_link: TipoLinkPesquisa;
  nota_minima: number;
  nota_maxima: number;
  comentario_max_caracteres: number;
};

export type RespostaPublicaCreate = {
  nota_nps: number;
  texto_comentario?: string | null;
  chave_idempotencia: string;
};

export type RespostaPublicaResponse = {
  id: string;
  nota_nps: number;
  criada_em: string;
};

// ─── Infra ───────────────────────────────────────────────────────────────────

type ErroApi = { error?: { code?: string; message?: string; correlation_id?: string } };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public correlationId?: string,
  ) {
    super(message);
  }
}

export function salvarToken(token: string) {
  try {
    sessionStorage.setItem(CHAVE_TOKEN, token);
  } catch {}
}

export function lerToken(): string | null {
  try {
    return sessionStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

export function sair() {
  try {
    sessionStorage.removeItem(CHAVE_TOKEN);
  } catch {}
}

type Opcoes = RequestInit & { autenticado?: boolean };

async function requisitar<T>(caminho: string, { autenticado = true, ...init }: Opcoes = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = autenticado ? lerToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let resposta: Response;
  try {
    resposta = await fetch(`${API_URL}/api/v1${caminho}`, {
      ...init,
      headers: { ...headers, ...(init.headers as Record<string, string> | undefined) },
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    throw new ApiError(0, "Não foi possível conectar ao servidor.");
  }

  if (!resposta.ok) {
    const corpo = (await resposta.json().catch(() => ({}))) as ErroApi;
    if (resposta.status === 401 && autenticado) sair();   // token vencido ou usuário desativado
    throw new ApiError(
      resposta.status,
      corpo.error?.message ?? "Erro inesperado.",
      corpo.error?.code,
      corpo.error?.correlation_id,
    );
  }
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

// ─── Autenticação ────────────────────────────────────────────────────────────

export function login(email: string, senha: string) {
  return requisitar<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
    autenticado: false,
  });
}

export function usuarioLogado() {
  return requisitar<UsuarioResponse>("/auth/me");
}

// ─── Pesquisas (ADMIN) ───────────────────────────────────────────────────────

export function listarPesquisas(status?: StatusPesquisa) {
  const filtro = status ? `&status=${status}` : "";
  return requisitar<PesquisaResponse[]>(`/pesquisas?limit=200${filtro}`);
}

export function criarPesquisa(dados: PesquisaCreate) {
  return requisitar<PesquisaResponse>("/pesquisas", { method: "POST", body: JSON.stringify(dados) });
}

const ACAO_POR_STATUS: Partial<Record<StatusPesquisa, string>> = {
  PUBLICADA: "publicar",
  PAUSADA: "pausar",
  ARQUIVADA: "arquivar",
};

/** RASCUNHO → PUBLICADA ⇄ PAUSADA → ARQUIVADA. Transição inválida → 409. */
export function alterarStatusPesquisa(id: string, status: StatusPesquisa) {
  const acao = ACAO_POR_STATUS[status];
  if (!acao) return Promise.reject(new ApiError(422, `Não é possível mudar o status para ${status}.`));
  return requisitar<PesquisaResponse>(`/pesquisas/${encodeURIComponent(id)}/${acao}`, { method: "POST" });
}

export function gerarLinkPesquisa(id: string, tipo: TipoLinkPesquisa) {
  return requisitar<LinkPesquisaResponse>(`/pesquisas/${encodeURIComponent(id)}/links`, {
    method: "POST",
    body: JSON.stringify({ tipo }),
  });
}

export function listarLinksPesquisa(id: string) {
  return requisitar<LinkPesquisaResponse[]>(`/pesquisas/${encodeURIComponent(id)}/links?limit=200`);
}

// ─── Fluxo público (respondente, sem login) ──────────────────────────────────
// credentials: "include" leva e traz o cookie HttpOnly que barra a segunda
// resposta do mesmo navegador num link ABERTO.

export function carregarPesquisaPublica(token: string) {
  return requisitar<PesquisaPublicaResponse>(`/public/respostas/${encodeURIComponent(token)}`, {
    autenticado: false,
    credentials: "include",
  });
}

export function enviarResposta(token: string, dados: RespostaPublicaCreate) {
  return requisitar<RespostaPublicaResponse>(`/public/respostas/${encodeURIComponent(token)}`, {
    method: "POST",
    body: JSON.stringify(dados),
    autenticado: false,
    credentials: "include",
  });
}
