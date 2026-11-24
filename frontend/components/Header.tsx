"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  EVENTO_AUTH,
  lerToken,
  lerUsuario,
  sair,
  salvarUsuario,
  usuarioLogado,
  UsuarioResponse,
} from "@/lib/api";

export default function Header() {
  const caminho = usePathname();
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const [adminLogado, setAdminLogado] = useState<UsuarioResponse | null>(null);

  useEffect(() => {
    let ativo = true;

    async function sincronizarUsuario() {
      const token = lerToken();
      if (!token) {
        if (ativo) setAdminLogado(null);
        return;
      }
      const cache = lerUsuario();
      if (cache) {
        if (ativo) setAdminLogado(cache.papel === "ADMIN" ? cache : null);
        return;
      }
      try {
        const u = await usuarioLogado();
        salvarUsuario(u);
        if (ativo) setAdminLogado(u.papel === "ADMIN" ? u : null);
      } catch {
        if (ativo) setAdminLogado(null);
      }
    }

    void sincronizarUsuario();
    window.addEventListener(EVENTO_AUTH, sincronizarUsuario);
    return () => {
      ativo = false;
      window.removeEventListener(EVENTO_AUTH, sincronizarUsuario);
    };
  }, [caminho]);

  function encerrarSessao() {
    sair();
    setAdminLogado(null);
    setAberto(false);
    router.push("/login");
  }

  const ativo = (href: string) =>
    caminho === href ||
    (href === "/login" && caminho === "/admin/login") ||
    (href === "/admin/pesquisas" && caminho.startsWith("/admin/pesquisas"));

  const renderLinks = () => (
    <>
      <Link
        href="/"
        className={`nav-link${ativo("/") ? " active" : ""}`}
        onClick={() => setAberto(false)}
      >
        Início
      </Link>

      {adminLogado ? (
        <div className="nav-user-group">
          <Link
            href="/admin/pesquisas"
            className={`nav-link nav-user-name${ativo("/admin/pesquisas") ? " active" : ""}`}
            onClick={() => setAberto(false)}
            title={`Logado como ${adminLogado.nome} (ADMIN)`}
          >
            {adminLogado.nome}
          </Link>
          <button
            type="button"
            className="nav-logout-btn"
            onClick={encerrarSessao}
            title="Encerrar sessão"
          >
            Sair
          </button>
        </div>
      ) : (
        <Link
          href="/login"
          className={`nav-link${ativo("/login") ? " active" : ""}`}
          onClick={() => setAberto(false)}
        >
          Login
        </Link>
      )}

      <Link
        href="/sobre"
        className={`nav-link${ativo("/sobre") ? " active" : ""}`}
        onClick={() => setAberto(false)}
      >
        Sobre nós
      </Link>
    </>
  );

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="logo">
          <span className="logo-name">KEYCORE</span>
          <span className="logo-tagline">Pesquisa de satisfação</span>
        </Link>
        {/* Links do menu */}
        <nav className="main-nav">{renderLinks()}</nav>
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
      <div className={`mobile-nav${aberto ? " open" : ""}`}>{renderLinks()}</div>
    </header>
  );
}
