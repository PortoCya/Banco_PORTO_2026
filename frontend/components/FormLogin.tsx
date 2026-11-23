"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ApiError, login, salvarToken, usuarioLogado } from "@/lib/api";

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
          <input name="email" type="email" required maxLength={200} autoComplete="email" />
        </label>
        <label>
          Senha
          <input
            name="senha"
            type="password"
            required
            maxLength={SENHA_MAX}
            autoComplete="current-password"
          />
        </label>
        <button className="btn-primario" type="submit" disabled={enviando}>
          {enviando ? "Entrando..." : "Entrar"}
        </button>
      </form>
      <MensagemAuth mensagem={mensagem} />
    </>
  );
}
