import Link from "next/link";
import FormLogin from "@/components/FormLogin";

export default function LoginAdmin() {
  return (
    <section className="auth-wrap">
      {/* Setinha: voltar ao login normal */}
      <Link href="/login" className="admin-toggle">
        <span className="admin-toggle-seta" aria-hidden>←</span>
        Voltar ao login normal
      </Link>

      <div className="auth-card">
        <h1 className="auth-title">
          Acesso <em>administrador</em>
        </h1>
        <FormLogin />
      </div>
    </section>
  );
}
