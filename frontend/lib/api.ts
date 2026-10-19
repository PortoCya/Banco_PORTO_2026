const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

type ErroApi = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function requisitar<T>(caminho: string, init: RequestInit): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_URL}/api/v1${caminho}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    throw new ApiError(0, "Não foi possível conectar ao servidor.");
  }

  if (!resposta.ok) {
    const corpo = (await resposta.json().catch(() => ({}))) as ErroApi;
    throw new ApiError(resposta.status, corpo.error?.message ?? "Erro inesperado.");
  }
  return (await resposta.json()) as T;
}

export function login(email: string, senha: string) {
  return requisitar<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

export function salvarToken(token: string) {
  try {
    sessionStorage.setItem("token", token);
  } catch {}
}
