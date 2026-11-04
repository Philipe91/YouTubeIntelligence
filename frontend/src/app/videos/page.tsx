import { VideoTable } from "@/components/VideoTable";
import { FormatTabs, PageHeader, Panel, formatParam, str } from "@/components/ui";
import { api, type Filters, type VideoRow } from "@/lib/api";
import { integer } from "@/lib/format";

export default async function Videos({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = params.f === "indeterminate" ? "indeterminate" : formatParam(params.f);
  const current = {
    q: str(params.q), niche_id: str(params.niche_id), language: str(params.language), country: str(params.country),
    channel_id: str(params.channel_id), days: str(params.days), sort: str(params.sort) ?? "idr", outliers_only: str(params.outliers_only),
  };
  const [data, filters] = await Promise.all([
    api<{ total: number; items: VideoRow[] }>("/api/videos", { format, ...current, limit: "100" }),
    api<Filters>("/api/filters"),
  ]);
  return (
    <>
      <PageHeader title="Vídeos" intro="Filtre por nicho, idioma, país e período. Passe o mouse sobre um número para ver a fonte.">
        <FormatTabs current={format} basePath="/videos" params={current} withIndeterminate />
      </PageHeader>
      {format === "indeterminate" && (
        <p className="mb-4 max-w-3xl rounded-md bg-page px-3 py-2 text-sm text-ink-2">Vídeos curtos sem dados que confirmem se são Shorts. Ficam fora de comparações e tendências, em vez de serem classificados por palpite.</p>
      )}
      <form className="mb-4 flex flex-wrap items-end gap-2">
        <input type="hidden" name="f" value={format} />
        <label className="text-[0.8125rem] text-ink-2">Tema no título<br /><input name="q" defaultValue={current.q} className="field w-44" placeholder="ex.: Cartago" /></label>
        <label className="text-[0.8125rem] text-ink-2">Nicho<br />
          <select name="niche_id" defaultValue={current.niche_id ?? ""} className="field"><option value="">Todos</option>{filters.niches.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}</select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">Idioma<br />
          <select name="language" defaultValue={current.language ?? ""} className="field"><option value="">Todos</option>{filters.languages.map((l) => <option key={l} value={l}>{l}</option>)}</select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">País<br />
          <select name="country" defaultValue={current.country ?? ""} className="field"><option value="">Todos</option>{filters.countries.map((c) => <option key={c} value={c}>{c}</option>)}</select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">Canal<br />
          <select name="channel_id" defaultValue={current.channel_id ?? ""} className="field max-w-52"><option value="">Todos</option>{filters.channels.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">Publicado em<br />
          <select name="days" defaultValue={current.days ?? ""} className="field">
            <option value="">Qualquer data</option><option value="7">7 dias</option><option value="30">30 dias</option><option value="90">90 dias</option>
          </select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">Ordenar por<br />
          <select name="sort" defaultValue={current.sort} className="field">
            <option value="idr">IDR</option><option value="vph">VPH observado</option><option value="views">Views</option><option value="recent">Mais recentes</option>
          </select>
        </label>
        <label className="flex min-h-9 items-center gap-1.5 text-sm text-ink-2">
          <input type="checkbox" name="outliers_only" value="true" defaultChecked={current.outliers_only === "true"} /> Só acima do típico
        </label>
        <button className="min-h-9 rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Aplicar filtros</button>
      </form>
      <p className="mb-2 text-sm text-ink-2">
        {data.total > data.items.length ? `Mostrando ${integer(data.items.length)} de ${integer(data.total)} vídeos.` : `${integer(data.total)} vídeos.`}
      </p>
      <Panel><VideoTable videos={data.items} /></Panel>
    </>
  );
}

export const dynamic = "force-dynamic";
