"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import FormLogin, { Mensagem, MensagemAuth, SENHA_MAX, SENHA_MIN } from "@/components/FormLogin";

type Aba = "entrar" | "criar";

export default function Login() {
  const [aba, setAba] = useState<Aba>("entrar");
  const [mensagem, setMensagem] = useState<Mensagem>(null);

  function trocarAba(nova: Aba) {
    setAba(nova);
    setMensagem(null);
  }

  function criarConta(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const dados = new FormData(e.currentTarget);
    if (dados.get("senha") !== dados.get("confirmar")) {
      setMensagem({ tipo: "erro", texto: "As senhas não coincidem." });
      return;
    }
    setMensagem({
      tipo: "erro",
      texto: "Cadastro ainda não disponível. Peça a um administrador para criar sua conta.",
    });
  }

  return (
    <section className="auth-wrap">
      {/* Setinha: ir para o login de administrador */}
      <Link href="/admin/login" className="admin-toggle">
        <span className="admin-toggle-seta" aria-hidden>→</span>
        Logar como administrador
      </Link>

      <div className="auth-card">
        {/* Abas Login / Criar conta */}
        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={aba === "entrar"}
            className={`auth-tab${aba === "entrar" ? " active" : ""}`}
            onClick={() => trocarAba("entrar")}
          >
            Login
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={aba === "criar"}
            className={`auth-tab${aba === "criar" ? " active" : ""}`}
            onClick={() => trocarAba("criar")}
          >
            Criar conta
          </button>
        </div>

        {/* Formulário: criar conta | login */}
        {aba === "criar" ? (
          <>
            <form className="auth-form" onSubmit={criarConta}>
              <label>
                Nome
                <input name="nome" type="text" required minLength={2} maxLength={200} autoComplete="name" />
              </label>
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
                  minLength={SENHA_MIN}
                  maxLength={SENHA_MAX}
                  autoComplete="new-password"
                />
                <small>De {SENHA_MIN} a {SENHA_MAX} caracteres.</small>
              </label>
              <label>
                Confirmar senha
                <input
                  name="confirmar"
                  type="password"
                  required
                  minLength={SENHA_MIN}
                  maxLength={SENHA_MAX}
                  autoComplete="new-password"
                />
              </label>
              <button className="btn-primario" type="submit">
                Criar conta
              </button>
            </form>
            <MensagemAuth mensagem={mensagem} />
          </>
        ) : (
          <FormLogin />
        )}
      </div>
    </section>
  );
}
