import Link from "next/link";

export default function NotFound() {
  return (
    <section className="not-found-wrap" role="alert" aria-labelledby="not-found-title">
      <div className="not-found-card">
        <span className="not-found-code">404</span>
        <h1 id="not-found-title" className="not-found-title">
          Página não encontrada
        </h1>
        <p className="not-found-text">
          O endereço que você tentou acessar não existe ou não está disponível.
        </p>
        <Link href="/" className="btn-primario not-found-btn">
          Voltar ao início
        </Link>
      </div>
    </section>
  );
}
