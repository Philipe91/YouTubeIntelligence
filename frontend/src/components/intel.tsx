import Link from "next/link";
import type { ReactNode } from "react";

import { Value } from "@/components/Mark";
import { BandPill, Empty, Pill, SourceLink, Thumb } from "@/components/ui";
import type { VideoRow } from "@/lib/api";
import { compact, dateTime, FORMAT_LABEL, shortDate, times } from "@/lib/format";
import type { IntelContext, Run } from "@/lib/intel";

export function OriginPill({ fictional, simulated }: { fictional: boolean; simulated?: boolean }) {
  if (simulated) return <Pill tone="warn" title="Resposta de um simulador local, usado em testes. Não veio do YouTube.">API simulada de teste</Pill>;
  return fictional
    ? <Pill tone="warn" title="Dados inventados para demonstração. Não representam nenhum canal real.">Dados fictícios</Pill>
    : <Pill tone="good" title="Veio das APIs oficiais do YouTube.">YouTube</Pill>;
}

/** De onde veio a pesquisa e quando os dados foram buscados. */
export function ProvenanceNote({ run }: { run: Run }) {
  const data = run.provenance;
  if (run.fictional) return <p className="text-[0.8125rem] text-ink-3">Origem: dados fictícios deste aplicativo. Nenhuma chamada à internet.</p>;
  if (!data.source) return <p className="text-[0.8125rem] text-ink-3">Pesquisa anterior ao registro de origem: sem detalhes de coleta.</p>;
  const calls = data.api_calls ?? 0;
  const cached = data.cache_hits ?? 0;
  return (
    <p className="text-[0.8125rem] text-ink-3">
      Origem: {run.simulated ? "API simulada de teste, não o YouTube" : "YouTube Data API v3"}. {calls} {calls === 1 ? "chamada nova" : "chamadas novas"} e {cached} {cached === 1 ? "resposta" : "respostas"} do cache.
      {data.oldest_data_at && ` Dados buscados em ${dateTime(data.oldest_data_at)}${data.newest_data_at && data.newest_data_at !== data.oldest_data_at ? ` a ${dateTime(data.newest_data_at)}` : ""}.`}
    </p>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "bad"; title?: string; children: ReactNode }) {
  const tones = { info: "border-cobalt/25 bg-cobalt-soft/50", warn: "border-warn/30 bg-warn-soft/60", bad: "border-bad/30 bg-bad-soft/60" };
  return (
    <div className={`rounded-md border px-3.5 py-2.5 text-sm leading-relaxed text-ink-2 ${tones[tone]}`}>
      {title && <p className="font-medium text-ink">{title}</p>}
      <div>{children}</div>
    </div>
  );
}

/** Campo de escolha de canal. Só lista canais que podem receber os dados do modo atual. */
export function ChannelSelect({ context, value, name = "channel_id", emptyLabel = "Sem canal" }: { context: IntelContext; value?: string; name?: string; emptyLabel?: string }) {
  return (
    <select name={name} defaultValue={value ?? ""} className="field w-full">
      <option value="">{emptyLabel}</option>
      {context.channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
    </select>
  );
}

/** Filtro por canal que funciona sem JavaScript: é um formulário GET comum. */
export function ChannelFilter({ context, value, action, keep = {} }: { context: IntelContext; value?: string; action: string; keep?: Record<string, string | undefined> }) {
  return (
    <form action={action} className="flex flex-wrap items-center gap-2">
      {Object.entries(keep).map(([key, val]) => val ? <input key={key} type="hidden" name={key} value={val} /> : null)}
      <label className="text-sm text-ink-2" htmlFor="filtro-canal">Canal</label>
      <select id="filtro-canal" name="canal" defaultValue={value ?? ""} className="field">
        <option value="">Todos</option>
        {context.channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
      </select>
      <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
    </form>
  );
}

export function RealChannelsNote({ context }: { context: IntelContext }) {
  const others = context.other_channels.filter((channel) => !channel.is_demo);
  if (context.mode !== "demo" || !others.length) return null;
  return <p className="text-[0.8125rem] text-ink-3">{others.map((c) => c.name).join(", ")} não aparece aqui: no modo demonstração, canal real não recebe dados fictícios.</p>;
}

export function Tabs({ items, current, href }: { items: { key: string; label: string; count?: number }[]; current: string; href: (key: string) => string }) {
  return (
    <nav aria-label="Seções" className="mb-5 flex gap-1 overflow-x-auto border-b border-line">
      {items.map((tab) => (
        <Link
          key={tab.key}
          href={href(tab.key)}
          aria-current={current === tab.key ? "page" : undefined}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${current === tab.key ? "border-pine font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}
        >
          {tab.label}{tab.count ? <span className="ml-1.5 text-ink-3">{tab.count}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

export function Pagination({ total, limit, offset, href }: { total: number; limit: number; offset: number; href: (offset: number) => string }) {
  if (total <= limit) return null;
  const end = Math.min(offset + limit, total);
  return (
    <nav aria-label="Páginas" className="flex items-center justify-between gap-3 border-t border-line px-3 py-2.5 text-sm">
      <span className="text-ink-3">{offset + 1} a {end} de {total}</span>
      <span className="flex gap-2">
        {offset > 0 && <Link className="rounded-md border border-line bg-surface px-3 py-1.5 hover:bg-page" href={href(Math.max(0, offset - limit))}>Anterior</Link>}
        {end < total && <Link className="rounded-md border border-line bg-surface px-3 py-1.5 hover:bg-page" href={href(offset + limit)}>Próxima</Link>}
      </span>
    </nav>
  );
}

/**
 * Lista de vídeos com os dados crus sempre visíveis. Os derivados só aparecem com a política liberada.
 * `actions` acrescenta botões por linha, como guardar para estudo.
 */
export function VideoResults({ videos, actions, empty = "Nenhum vídeo encontrado." }: { videos: VideoRow[]; actions?: (video: VideoRow) => ReactNode; empty?: string }) {
  if (!videos.length) return <Empty title={empty}>Amplie o período, troque os filtros ou use um termo mais curto.</Empty>;
  return (
    <ul className="divide-y divide-line">
      {videos.map((video) => (
        <li key={video.id} className="flex flex-wrap items-start gap-3 p-3">
          <Thumb video={video} />
          <div className="min-w-0 flex-1 basis-56">
            <Link href={`/videos/${video.id}`} className="line-clamp-2 text-sm font-medium hover:text-cobalt hover:underline">{video.title}</Link>
            <p className="mt-0.5 text-[0.8125rem] text-ink-3">
              <Link className="hover:underline" href={`/concorrentes/${video.channel_id}`}>{video.channel_title}</Link>, publicado em {shortDate(video.published_at)}, {FORMAT_LABEL[video.format] ?? video.format}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem]">
              <span title="Visualizações públicas"><Value metric={video.views} format={compact} /> views</span>
              {!video.derived_blocked && <span title="Índice próprio. Não é dado do YouTube."><Value metric={video.idr} format={times} /></span>}
              {!video.derived_blocked && video.outlier && <BandPill video={video} />}
              <SourceLink url={video.source_url} />
            </div>
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-start gap-2">{actions(video)}</div>}
        </li>
      ))}
    </ul>
  );
}
