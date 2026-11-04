import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { Empty, PageHeader, Panel, Pill, SourceLink, str } from "@/components/ui";
import { Notice, OriginPill, Pagination, ProvenanceNote, VideoResults } from "@/components/intel";
import { compact, dateTime, FORMAT_LABEL, shortDate } from "@/lib/format";
import { intelGet, intelGetOrNull, type ChannelResult, type IntelContext, type Page, type Run, type RunView } from "@/lib/intel";

import { deleteRun, rerunResearch, saveRun } from "../../intel-actions";

function ChannelTable({ channels }: { channels: ChannelResult[] }) {
  if (!channels.length) return <Empty title="Nenhum canal encontrado.">Troque os filtros ou use um termo mais curto.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="data-table w-full">
        <thead><tr><th>Canal</th><th>País</th><th className="num">Inscritos</th><th className="num">Vídeos coletados</th><th>Último vídeo coletado</th><th>Origem</th></tr></thead>
        <tbody>
          {channels.map((channel) => (
            <tr key={channel.id}>
              <td><Link className="font-medium text-cobalt underline underline-offset-2" href={`/concorrentes/${channel.id}`}>{channel.title}</Link>{channel.handle && <div className="text-[0.8125rem] text-ink-3">{channel.handle}</div>}</td>
              <td>{channel.country ?? "Não informado"}</td>
              <td className="num"><Value metric={channel.subscribers} format={compact} muted="Oculto" /></td>
              <td className="num">{channel.videos_collected}</td>
              <td>{channel.last_published_at ? shortDate(channel.last_published_at) : "Nenhum"}</td>
              <td><SourceLink url={channel.source_url} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function RunPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const query = await searchParams;
  const offset = Number(str(query.inicio)) || 0;
  const data = await intelGetOrNull<RunView>(`/research/runs/${id}`, { limit: "25", offset: String(offset) });
  if (!data) notFound();
  const [context, others] = await Promise.all([intelGet<IntelContext>("/context"), intelGet<Page<Run>>("/research/runs", { limit: "30" })]);
  const { run } = data;
  const channelName = context.channels.find((c) => c.id === run.managed_channel_id)?.name;
  const filters = [run.filters.language && `Idioma ${run.filters.language}`, run.filters.country && `País ${run.filters.country}`, run.filters.days && `Últimos ${run.filters.days} dias`, run.filters.format && FORMAT_LABEL[run.filters.format], run.filters.max_subscribers && `Até ${compact(run.filters.max_subscribers)} inscritos`].filter(Boolean);
  const candidates = others.items.filter((other) => other.id !== run.id && other.data_origin === run.data_origin);

  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href="/pesquisa?aba=historico">Voltar ao histórico</Link></p>
      <PageHeader title={run.query} intro={`${run.kind_label}, em ${dateTime(run.executed_at)}. ${channelName ? `Associada a ${channelName}.` : "Sem canal associado."}`}>
        <div className="flex flex-wrap gap-1.5"><OriginPill fictional={run.fictional} simulated={run.simulated} />{run.saved_name && <Pill tone="info">Salva: {run.saved_name}</Pill>}</div>
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <ActionForm action={saveRun} submit={run.saved_name ? "Renomear" : "Salvar pesquisa"} tone="quiet" hidden={{ run_id: run.id }} className="flex flex-wrap items-end gap-2" doneMessage="Salva.">
          <label className="text-sm text-ink-2">Nome<input name="name" defaultValue={run.saved_name ?? run.query} maxLength={120} required className="field mt-1 block" /></label>
        </ActionForm>
        <ActionForm action={rerunResearch} submit="Pesquisar de novo" pending="Pesquisando..." tone="quiet" hidden={{ run_id: run.id }} />
        <a href={`/pesquisa/${run.id}/exportar`} className="inline-flex min-h-9 items-center rounded-md border border-line bg-surface px-3.5 text-sm font-medium hover:bg-page">Exportar CSV</a>
        {candidates.length > 0 && (
          <form action="/pesquisa/comparar" className="flex flex-wrap items-end gap-2">
            <input type="hidden" name="a" value={run.id} />
            <label className="text-sm text-ink-2">Comparar com
              <select name="b" className="field mt-1 block max-w-64">{candidates.map((c) => <option key={c.id} value={c.id}>{c.query}, {dateTime(c.executed_at)}</option>)}</select>
            </label>
            <button className="min-h-9 rounded-md border border-line bg-surface px-3.5 text-sm font-medium hover:bg-page">Comparar</button>
          </form>
        )}
        <ActionForm action={deleteRun} submit="Apagar" tone="danger" hidden={{ run_id: run.id }} />
      </div>

      <div className="mb-4 space-y-2">
        <ProvenanceNote run={run} />
        <p className="text-sm text-ink-2">Filtros: {filters.length ? filters.join(", ") : "nenhum"}. Volume de busca: <Value metric={data.search_volume} format={compact} muted="Indisponível" />.{run.total_results_approx !== null && ` A API informa cerca de ${compact(run.total_results_approx)} resultados, número aproximado.`}</p>
        {data.filter_notes.map((note) => <Notice key={note}>{note}</Notice>)}
        {!data.derived_allowed && <Notice tone="warn" title="Só dados crus">Scores e VPH estão bloqueados pela política da API até a aprovação do Google. <Link className="underline" href="/sistema">Ver o que falta</Link></Notice>}
        {data.removed > 0 && <Notice tone="warn">{data.removed} {data.removed === 1 ? "item saiu" : "itens saíram"} da base nesta página: o texto da API tem prazo de 30 dias sem atualização.</Notice>}
      </div>

      <Panel>
        {run.kind === "channels" || run.kind === "emerging" ? <ChannelTable channels={data.channels} /> : <VideoResults videos={data.videos} />}
        <Pagination total={data.total} limit={data.limit} offset={data.offset} href={(next) => `/pesquisa/${run.id}?inicio=${next}`} />
      </Panel>
      {run.kind === "emerging" && <p className="mt-2 text-[0.8125rem] text-ink-3">Canais que publicaram sobre o tema no período, até o limite de inscritos. {data.derived_allowed ? "Do menor para o maior em inscritos." : "Na ordem da busca do YouTube."} É um filtro sobre o número público, não uma nota de potencial. Canais que ocultam os inscritos ficam de fora.</p>}
    </>
  );
}

export const dynamic = "force-dynamic";
