import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Empty, PageHeader, Panel, Pill, SourceLink, str, Thumb } from "@/components/ui";
import { Notice, OriginPill, Pagination, RealChannelsNote, Tabs, VideoResults } from "@/components/intel";
import { compact, dateTime, shortDate } from "@/lib/format";
import { intelGet, PERIODS, type ExplorerResult, type IntelContext, type Page, type StudyItem } from "@/lib/intel";

import { addStudy, removeStudy, saveStudyNote } from "../intel-actions";

const TABS = [{ key: "explorar", label: "Explorar" }, { key: "estudo", label: "Lista de estudo" }];
const ORIGIN: Record<string, string> = { explorer: "Explorer", competidor: "Concorrente", pesquisa: "Pesquisa" };

function StudyList({ data, channel }: { data: Page<StudyItem>; channel: string }) {
  if (!data.items.length) return <Panel><Empty title="A lista de estudo deste canal está vazia.">Na aba Explorar, clique em Guardar para estudo.</Empty></Panel>;
  return (
    <form action="/explorer/comparar">
      <input type="hidden" name="canal" value={channel} />
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
          <p className="text-sm text-ink-2">Marque de 2 a 6 vídeos para comparar títulos e abordagens. Eles entram na fila de medições do coletor.</p>
          <button className="min-h-9 rounded-md bg-pine px-3.5 text-sm font-medium text-white hover:bg-pine-soft">Comparar selecionados</button>
        </div>
        <ul className="divide-y divide-line">
          {data.items.map((item) => (
            <li key={item.video.id} className="flex flex-wrap items-start gap-3 p-3">
              <input type="checkbox" name="ids" value={item.video.id} aria-label={`Comparar ${item.video.title}`} className="mt-1 size-4" />
              <Thumb video={item.video} />
              <div className="min-w-0 flex-1 basis-64">
                <Link href={`/videos/${item.video.id}`} className="text-sm font-medium hover:text-cobalt hover:underline">{item.video.title}</Link>
                <p className="mt-0.5 text-[0.8125rem] text-ink-3">{item.video.channel_title}, publicado em {shortDate(item.video.published_at)}. Guardado em {dateTime(item.added_at)}. <Pill>{ORIGIN[item.origin] ?? item.origin}</Pill></p>
                <p className="mt-1 text-[0.8125rem] text-ink-2">
                  {item.snapshots.count > 0 ? `${item.snapshots.count} medições: ${compact(item.snapshots.first_views ?? 0)} views em ${dateTime(item.snapshots.first_at)} e ${compact(item.snapshots.last_views ?? 0)} em ${dateTime(item.snapshots.last_at)}.` : "Sem medição de views ainda."}{" "}
                  <SourceLink url={item.video.source_url} />
                </p>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </form>
  );
}

function StudyNotes({ data, channel }: { data: Page<StudyItem>; channel: string }) {
  if (!data.items.length) return null;
  return (
    <Panel className="mt-4 p-4">
      <h2 className="font-display text-[1.1875rem] font-semibold">Notas de abordagem</h2>
      <ul className="mt-3 divide-y divide-line">
        {data.items.map((item) => (
          <li key={item.video.id} className="py-3">
            <p className="text-sm font-medium">{item.video.title}</p>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <ActionForm action={saveStudyNote} submit="Salvar nota" tone="quiet" hidden={{ channel_id: channel, video_id: item.video.id }} className="flex min-w-64 flex-1 flex-wrap items-end gap-2" doneMessage="Nota salva.">
                <label className="min-w-56 flex-1 text-[0.8125rem] text-ink-2">Como este vídeo conta a história
                  <input name="note" defaultValue={item.note} maxLength={1000} className="field mt-1 w-full" />
                </label>
              </ActionForm>
              <ActionForm action={removeStudy} submit="Tirar da lista" tone="danger" hidden={{ channel_id: channel, video_id: item.video.id }} />
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default async function Explorer({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const tab = params.aba === "estudo" ? "estudo" : "explorar";
  const context = await intelGet<IntelContext>("/context");
  const canal = str(params.canal);
  const channel = context.channels.some((c) => c.id === canal) ? canal : undefined;
  const offset = Number(str(params.inicio)) || 0;
  const current = { q: str(params.q), days: str(params.periodo), format: params.f === "short" ? "short" : "long", sort: str(params.ordem) ?? (context.derived_allowed ? "idr" : "views"), only_above: params.acima === "1" ? "true" : undefined, min_views: str(params.minimo) };
  const query = (extra: Record<string, string>) => {
    const out = new URLSearchParams();
    for (const [key, value] of Object.entries({ aba: tab, canal: channel, q: current.q, periodo: current.days, f: current.format, ordem: current.sort, acima: params.acima === "1" ? "1" : undefined, minimo: current.min_views, ...extra })) if (value) out.set(key, value);
    return `/explorer?${out}`;
  };
  const [results, study, ids] = await Promise.all([
    tab === "explorar" ? intelGet<ExplorerResult>("/explorer", { ...current, limit: "25", offset: String(offset) }) : null,
    tab === "estudo" && channel ? intelGet<Page<StudyItem>>(`/channels/${channel}/study`, { limit: "30", offset: String(offset) }) : null,
    channel ? intelGet<{ ids: string[] }>(`/channels/${channel}/study/ids`) : { ids: [] as string[] },
  ]);
  const saved = new Set(ids.ids);

  return (
    <>
      <PageHeader title="Outlier Explorer" intro="Procure vídeos públicos por assunto, guarde os que merecem estudo e compare títulos e abordagens narrativas.">
        <Pill tone={context.derived_allowed ? "info" : "warn"}>{context.derived_allowed ? "Índice próprio ativo" : "Só dados crus"}</Pill>
      </PageHeader>
      <Tabs items={TABS} current={tab} href={(key) => `/explorer?aba=${key}${channel ? `&canal=${channel}` : ""}`} />
      <form action="/explorer" className="mb-4 flex flex-wrap items-end gap-2">
        <input type="hidden" name="aba" value={tab} />
        <label className="text-[0.8125rem] text-ink-2">Lista de estudo do canal<br />
          <select name="canal" defaultValue={channel ?? ""} className="field max-w-60"><option value="">Nenhum</option>{context.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        </label>
        {tab === "explorar" && (
          <>
            <label className="text-[0.8125rem] text-ink-2">Assunto no título<br /><input name="q" defaultValue={current.q} placeholder="Ex.: Cartago" className="field w-44" /></label>
            <label className="text-[0.8125rem] text-ink-2">Formato<br /><select name="f" defaultValue={current.format} className="field"><option value="long">Vídeos longos</option><option value="short">Shorts</option></select></label>
            <label className="text-[0.8125rem] text-ink-2">Período<br /><select name="periodo" defaultValue={current.days ?? ""} className="field"><option value="">Qualquer data</option>{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></label>
            <label className="text-[0.8125rem] text-ink-2">Mínimo de views<br /><input name="minimo" type="number" min={0} defaultValue={current.min_views} className="field w-28" /></label>
            <label className="text-[0.8125rem] text-ink-2">Ordenar por<br />
              <select name="ordem" defaultValue={current.sort} className="field">
                {context.derived_allowed && <option value="idr">Índice próprio (IDR)</option>}
                {context.derived_allowed && <option value="vph">VPH observado</option>}
                <option value="views">Views públicas</option><option value="recent">Mais recentes</option>
              </select>
            </label>
            {context.derived_allowed && <label className="flex min-h-9 items-center gap-1.5 text-sm text-ink-2"><input type="checkbox" name="acima" value="1" defaultChecked={params.acima === "1"} /> Só acima do típico</label>}
          </>
        )}
        <button className="min-h-9 rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Aplicar</button>
      </form>
      <div className="mb-4"><RealChannelsNote context={context} /></div>

      {results && (
        <>
          {!results.derived_allowed && <div className="mb-3"><Notice tone="warn" title="Só dados crus">{results.blocked_reason} A lista continua com thumbnail, título, views, data, canal e link de origem.</Notice></div>}
          {results.notes.map((note) => <div key={note} className="mb-3"><Notice>{note}</Notice></div>)}
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-ink-2"><span>{results.total} vídeos na base coletada.</span>{<OriginPill fictional={results.fictional} />}<Link className="text-cobalt underline underline-offset-2" href="/pesquisa">Buscar vídeos novos na central de pesquisa</Link></div>
          <Panel>
            <VideoResults
              videos={results.items}
              actions={(video) => channel && (saved.has(video.id)
                ? <Pill tone="good">Na lista de estudo</Pill>
                : <ActionForm action={addStudy} submit="Guardar para estudo" tone="quiet" hidden={{ channel_id: channel, video_id: video.id }} />)}
            />
            <Pagination total={results.total} limit={results.limit} offset={results.offset} href={(next) => query({ inicio: String(next) })} />
          </Panel>
          {!channel && <p className="mt-2 text-[0.8125rem] text-ink-3">Escolha um canal para guardar vídeos na lista de estudo.</p>}
          {results.origin_note && <p className="mt-2 text-[0.8125rem] text-ink-3">{results.origin_note}</p>}
        </>
      )}

      {tab === "estudo" && !channel && <Panel><Empty title="Escolha um canal.">Cada canal tem a própria lista de estudo.</Empty></Panel>}
      {study && channel && (
        <>
          <StudyList data={study} channel={channel} />
          <StudyNotes data={study} channel={channel} />
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
