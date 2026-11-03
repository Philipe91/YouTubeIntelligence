import Link from "next/link";
import type { ReactNode } from "react";

import type { VideoRow } from "@/lib/api";
import { ACCELERATION_LABEL, BAND_LABEL, OUTLIER_STATUS_LABEL } from "@/lib/format";

export function PageHeader({ title, intro, children }: { title: string; intro?: string; children?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="font-display text-[1.875rem] leading-tight font-semibold text-ink">{title}</h1>
        {intro && <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-ink-2">{intro}</p>}
      </div>
      {children}
    </header>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="font-display text-[1.1875rem] font-semibold text-ink">{children}</h2>;
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-lg border border-line bg-surface ${className}`}>{children}</section>;
}

/** Abas de formato. Shorts e longos nunca aparecem na mesma lista. */
export function FormatTabs({ current, basePath, params = {} }: { current: string; basePath: string; params?: Record<string, string | undefined> }) {
  const href = (format: string) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
    query.set("f", format);
    return `${basePath}?${query}`;
  };
  return (
    <div role="group" aria-label="Formato" className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {[{ key: "short", label: "Shorts" }, { key: "long", label: "Vídeos longos" }].map((tab) => (
        <Link
          key={tab.key}
          href={href(tab.key)}
          aria-current={current === tab.key ? "true" : undefined}
          className={`rounded px-3.5 py-1.5 text-sm ${current === tab.key ? "bg-pine font-medium text-white" : "text-ink-2 hover:bg-page"}`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

const TONES = {
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  info: "bg-cobalt-soft text-cobalt",
  ochre: "bg-ochre-soft text-ochre",
  neutral: "bg-page text-ink-2",
} as const;

export function Pill({ tone = "neutral", children, title }: { tone?: keyof typeof TONES; children: ReactNode; title?: string }) {
  return <span title={title} className={`inline-block rounded px-1.5 py-0.5 text-[0.8125rem] whitespace-nowrap ${TONES[tone]}`}>{children}</span>;
}

export function BandPill({ video }: { video: VideoRow }) {
  const outlier = video.outlier;
  if (!outlier) return <Pill>Bloqueado</Pill>;
  if (outlier.status !== "ok") return <Pill title={video.idr.reason ?? undefined}>{OUTLIER_STATUS_LABEL[outlier.status] ?? outlier.status}</Pill>;
  if (!outlier.band) return <Pill>Sem razão definida</Pill>;
  const tone = outlier.band === "extremo" || outlier.band === "muito_acima" ? "ochre" : outlier.band === "acima" ? "info" : "neutral";
  return <Pill tone={tone}>{BAND_LABEL[outlier.band]}</Pill>;
}

export function AccelerationPill({ status }: { status: string }) {
  const tone = status === "acelerando" || status === "emergente" ? "good" : status === "desacelerando" ? "warn" : "neutral";
  return <Pill tone={tone}>{ACCELERATION_LABEL[status] ?? status}</Pill>;
}

export function ConfidencePill({ level }: { level: string | null }) {
  if (!level) return null;
  return <span className="text-[0.8125rem] text-ink-3">Confiança {level === "media" ? "média" : level}</span>;
}

export function BlockedNotice({ reason }: { reason?: string }) {
  return (
    <Panel className="max-w-2xl border-bad/30 p-5">
      <SectionTitle>Este cálculo está bloqueado com dados reais</SectionTitle>
      <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">{reason}</p>
      <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
        Os dados crus continuam disponíveis em <Link className="text-cobalt underline" href="/videos">Vídeos</Link>. Para liberar os cálculos, veja os passos em{" "}
        <Link className="text-cobalt underline" href="/sistema">Sistema e cotas</Link>.
      </p>
    </Panel>
  );
}

function hue(seed: string): number {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return hash;
}

/** Thumbnail real quando existe. Nos dados fictícios, um bloco de cor deixa claro que não há imagem. */
export function Thumb({ video, size = "md" }: { video: Pick<VideoRow, "id" | "title" | "thumbnail_url" | "format">; size?: "sm" | "md" }) {
  const vertical = video.format === "short";
  const height = size === "sm" ? 44 : 64;
  const width = vertical ? Math.round((height * 9) / 16) : Math.round((height * 16) / 9);
  if (video.thumbnail_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={video.thumbnail_url} alt="" width={width} height={height} className="shrink-0 rounded object-cover" style={{ width, height }} loading="lazy" referrerPolicy="no-referrer" />;
  }
  const color = hue(video.id);
  return (
    <span
      aria-hidden
      title="Sem imagem: vídeo fictício"
      className="block shrink-0 rounded"
      style={{ width, height, background: `linear-gradient(135deg, hsl(${color} 32% 42%), hsl(${(color + 40) % 360} 38% 28%))` }}
    />
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="p-8 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">{children}</p>}
    </div>
  );
}

export function SourceLink({ url, label = "Abrir no YouTube" }: { url: string | null; label?: string }) {
  if (!url) return <span className="text-[0.8125rem] text-ink-3" title="Dado fictício: não existe página no YouTube">Sem link: dado fictício</span>;
  return <a href={url} target="_blank" rel="noreferrer noopener" className="text-sm text-cobalt underline underline-offset-2">{label}</a>;
}

export function formatParam(value: string | string[] | undefined): "short" | "long" {
  return value === "long" ? "long" : "short";
}

export function str(value: string | string[] | undefined): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}
