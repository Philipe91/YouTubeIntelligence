import type { Metadata } from "next";
import { Bricolage_Grotesque, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";
import type { ReactNode } from "react";

import { MarkLegend } from "@/components/Mark";
import { Sidebar } from "@/components/Sidebar";
import { api, type SystemStatus } from "@/lib/api";

import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", weight: ["500", "600"] });
const body = IBM_Plex_Sans({ subsets: ["latin"], variable: "--font-plex", weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "YouTube Intelligence",
  description: "Inteligência competitiva local para canais do YouTube",
};

async function ModeBanner() {
  let status: SystemStatus | null = null;
  try {
    status = await api<SystemStatus>("/api/system");
  } catch {
    return (
      <div role="alert" className="bg-bad px-6 py-2 text-sm text-white">
        A API local não está respondendo. Inicie o backend: veja o README.
      </div>
    );
  }
  if (status.mode === "demo") {
    return (
      <div className="bg-warn-soft px-6 py-2 text-sm text-warn">
        Modo demonstração: a pesquisa usa dados fictícios. Canais marcados como &ldquo;Seu canal&rdquo; são cadastros seus e nunca recebem esses números.
      </div>
    );
  }
  if (!status.policy.derived_allowed) {
    return (
      <div className="bg-bad-soft px-6 py-2 text-sm text-bad">
        Pesquisa com dados reais do YouTube, só crus. Scores e VPH estão bloqueados pela política da API.{" "}
        <Link className="underline" href="/sistema">Ver como liberar</Link>
      </div>
    );
  }
  return (
    <div className="bg-cobalt-soft px-6 py-2 text-sm text-cobalt">
      Dados reais do YouTube. Métricas calculadas por este aplicativo não são dados do YouTube.
    </div>
  );
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen">
        <Sidebar />
        <div className="md:pl-56">
          <ModeBanner />
          <main className="mx-auto max-w-[76rem] px-4 py-7 md:px-8">{children}</main>
          <footer className="mx-auto flex max-w-[76rem] flex-wrap items-start justify-between gap-6 border-t border-line px-4 py-6 md:px-8">
            <div>
              <p className="mb-2 text-[0.8125rem] font-medium text-ink-2">O sinal ao lado de cada número indica de onde ele vem</p>
              <MarkLegend tone="light" />
            </div>
            <p className="max-w-sm text-[0.8125rem] leading-relaxed text-ink-3">
              Ferramenta independente, sem relação com o YouTube ou o vidIQ. Dados de vídeos e canais vêm das APIs do YouTube quando o modo real está ativo.
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
