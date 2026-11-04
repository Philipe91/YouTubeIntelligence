"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const GROUPS = [
  {
    label: "Inteligência",
    items: [
      { href: "/", label: "Hoje" },
      { href: "/descobrir", label: "Descobrir oportunidades" },
      { href: "/pesquisa", label: "Central de pesquisa" },
      { href: "/palavras", label: "Palavras-chave" },
      { href: "/explorer", label: "Outlier Explorer" },
      { href: "/ideias", label: "Ideias diárias" },
      { href: "/coach", label: "Coach" },
      { href: "/lab", label: "Títulos e thumbnails" },
      { href: "/oportunidades", label: "Oportunidades" },
      { href: "/videos", label: "Vídeos" },
      { href: "/tendencias", label: "Tendências" },
      { href: "/concorrentes", label: "Concorrentes" },
      { href: "/meus-canais", label: "Analytics" },
    ],
  },
  {
    label: "Canais",
    items: [
      { href: "/canais", label: "Meus canais dark" },
      { href: "/fila", label: "Fila de produção" },
    ],
  },
];
const SECONDARY = [
  { href: "/sistema", label: "Sistema e cotas" },
  { href: "/metodologia", label: "Como calculamos" },
];

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`nav-link block rounded-md px-3 py-1.5 text-[0.9375rem] ${
        active ? "bg-pine-soft font-medium text-white" : "text-mist hover:bg-pine-soft/60 hover:text-white"
      }`}
    >
      {label}
    </Link>
  );
}

export function Sidebar() {
  return (
    <aside className="bg-pine md:fixed md:inset-y-0 md:left-0 md:flex md:w-56 md:flex-col md:overflow-y-auto">
      <div className="px-5 pt-5 pb-3">
        <Link href="/" className="nav-link font-display text-[1.25rem] leading-tight font-semibold text-white">
          YouTube Intelligence
        </Link>
      </div>
      <nav aria-label="Principal" className="flex items-center gap-1 overflow-x-auto px-2 pb-3 whitespace-nowrap md:block md:overflow-visible md:whitespace-normal">
        {GROUPS.map((group) => (
          <div key={group.label} className="contents md:mb-4 md:block md:space-y-0.5">
            <p className="hidden px-3 pb-1 text-[0.8125rem] text-mist/70 md:block">{group.label}</p>
            {group.items.map((item) => <NavLink key={item.href} {...item} />)}
          </div>
        ))}
        <div className="contents md:hidden">{SECONDARY.map((item) => <NavLink key={item.href} {...item} />)}</div>
      </nav>
      <nav aria-label="Suporte" className="mt-auto hidden space-y-0.5 border-t border-pine-line px-2 py-3 md:block">
        {SECONDARY.map((item) => (
          <NavLink key={item.href} {...item} />
        ))}
      </nav>
    </aside>
  );
}
