"use client";

import Link from "next/link";
import FormLogin from "@/components/FormLogin";

export default function Login() {
  return (
    <section className="auth-wrap">
      {/* Setinha: ir para o login de administrador */}
      <Link href="/admin/login" className="admin-toggle">
        <span className="admin-toggle-seta" aria-hidden>→</span>
        Logar como administrador
      </Link>

      <div className="auth-card">
        <h1 className="auth-title">
          Acessar <em>conta</em>
        </h1>
        <FormLogin />
      </div>
    </section>
  );
}
