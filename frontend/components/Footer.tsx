import Link from "next/link";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <p className="footer-name">KeyCore</p>
        <div className="footer-links">
          <Link href="/">Início</Link>
          <Link href="/login">Login</Link>
          <Link href="/sobre">Sobre nós</Link>
        </div>
        <p className="footer-copy">© {new Date().getFullYear()} · Todos os direitos reservados</p>
      </div>
    </footer>
  );
}
