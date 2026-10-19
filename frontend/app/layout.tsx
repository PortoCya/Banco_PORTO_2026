import type { Metadata } from "next";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import "./globals.css";

export const metadata: Metadata = {
  title: "KeyCore",
  description: "Plataforma de pesquisa de satisfação e NPS",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/* Menu */}
        <Header />
        {/* Conteúdo da página */}
        <main className="page-content">{children}</main>
        {/* Rodapé */}
        <Footer />
      </body>
    </html>
  );
}
