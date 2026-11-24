"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ApiError, login, salvarToken, salvarUsuario, usuarioLogado } from "@/lib/api";

export const SENHA_MIN = 12;
export const SENHA_MAX = 128;

export type Mensagem = { tipo: "erro" | "ok"; texto: string } | null;

export function MensagemAuth({ mensagem }: { mensagem: Mensagem }) {
  if (!mensagem) return null;
  return (
    <p className={`auth-msg ${mensagem.tipo}`} role="status">
      {mensagem.texto}
    </p>
  );
}

export default function FormLogin() {
  const [mensagem, setMensagem] = useState<Mensagem>(null);
  const [enviando, setEnviando] = useState(false);
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const router = useRouter();

  async function entrar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const dados = new FormData(e.currentTarget);
    setEnviando(true);
    setMensagem(null);
    try {
      const token = await login(String(dados.get("email")), String(dados.get("senha")));
      salvarToken(token.access_token);
      // O papel vem do backend (lido do banco), não do formulário
      const usuario = await usuarioLogado();
      salvarUsuario(usuario);
      if (usuario.papel === "ADMIN") {
        router.push("/admin/pesquisas");
        return;
      }
      setMensagem({
        tipo: "ok",
        texto: "Login realizado. Os indicadores de NPS ficam no dashboard de análise.",
      });
    } catch (err) {
      setMensagem({
        tipo: "erro",
        texto: err instanceof ApiError ? err.message : "Erro inesperado.",
      });
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <form className="auth-form" onSubmit={entrar}>
        <label>
          E-mail
          <input
            name="email"
            type="email"
            required
            maxLength={200}
            autoComplete="email"
            placeholder="seu@email.com.br"
          />
        </label>
        <div className="auth-field">
          <div className="password-label-row">
            <label htmlFor="campo-senha">Senha</label>
            <button
              type="button"
              className="password-toggle-inline"
              onClick={() => setMostrarSenha((v) => !v)}
              aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
              aria-pressed={mostrarSenha}
            >
              {mostrarSenha ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
              <span>{mostrarSenha ? "Ocultar senha" : "Ver senha"}</span>
            </button>
          </div>
          <div className="password-input-wrap">
            <input
              id="campo-senha"
              name="senha"
              type={mostrarSenha ? "text" : "password"}
              required
              maxLength={SENHA_MAX}
              autoComplete="current-password"
              placeholder="Digite sua senha"
            />
            <button
              type="button"
              className="password-toggle-addon"
              onClick={() => setMostrarSenha((v) => !v)}
              aria-label={mostrarSenha ? "Ocultar senha" : "Ver senha"}
              title={mostrarSenha ? "Ocultar senha" : "Ver senha"}
            >
              {mostrarSenha ? "Ocultar" : "Ver"}
            </button>
          </div>
        </div>
        <button className="btn-primario" type="submit" disabled={enviando}>
          {enviando ? "Entrando..." : "Entrar"}
        </button>
      </form>
      <MensagemAuth mensagem={mensagem} />
    </>
  );
}
