"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const LINKS = [
  { href: "/", rotulo: "Início" },
  { href: "/login", rotulo: "Login" },
  { href: "/sobre", rotulo: "Sobre nós" },
];

export default function Header() {
  const caminho = usePathname();
  const [aberto, setAberto] = useState(false);

  const ativo = (href: string) =>
    caminho === href || (href === "/login" && caminho === "/admin/login");

  const links = LINKS.map((l) => (
    <Link
      key={l.href}
      href={l.href}
      className={`nav-link${ativo(l.href) ? " active" : ""}`}
      onClick={() => setAberto(false)}
    >
      {l.rotulo}
    </Link>
  ));

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="logo">
          <span className="logo-name">KEYCORE</span>
          <span className="logo-tagline">Pesquisa de satisfação</span>
        </Link>
        {/* Links do menu */}
        <nav className="main-nav">{links}</nav>
        <button
          className="menu-toggle"
          aria-label="Menu"
          aria-expanded={aberto}
          onClick={() => setAberto((a) => !a)}
        >
          <span />
          <span />
          <span />
        </button>
      </div>
      {/* Menu do celular */}
      <div className={`mobile-nav${aberto ? " open" : ""}`}>{links}</div>
    </header>
  );
}
