import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { Notice, OriginPill, Pagination, ProvenanceNote, VideoResults } from "@/components/intel";
import { Empty, PageHeader, Panel, Pill, SectionTitle, SourceLink, str } from "@/components/ui";
import type { VideoRow } from "@/lib/api";
import { compact, dateTime, FORMAT_LABEL } from "@/lib/format";
import { intelGetOrNull, type ChannelResult, type DiscoveryView, type FormatEstimate } from "@/lib/intel";

import { saveDiscoveryItem } from "../../intel-actions";

const CONFIDENCE: Record<string, { label: string; tone: "good" | "info" | "warn" | "neutral" }> = {
  confirmado: { label: "Formato confirmado", tone: "good" }, confiavel: { label: "Formato confiável", tone: "good" },
  estimado: { label: "Formato estimado", tone: "info" }, indeterminado: { label: "Formato indeterminado", tone: "warn" }, ficticio: { label: "Formato fictício", tone: "neutral" },
};

function FormatPill({ estimate, format }: { estimate?: FormatEstimate; format: string }) {
  const style = CONFIDENCE[estimate?.confidence ?? "indeterminado"];
  return <span title={estimate?.basis}><Pill tone={style.tone}>{FORMAT_LABEL[format] ?? format}: {style.label.replace("Formato ", "")}</Pill></span>;
}

function SaveButtons({ channel, run, type, id, titleToo }: { channel: string; run: string; type: string; id: string; titleToo?: boolean }) {
  const hidden = { channel_id: channel, run_id: run, item_id: id };
  return (
    <>
      <ActionForm action={saveDiscoveryItem} submit={type === "canal" ? "Salvar canal" : "Salvar vídeo"} tone="quiet" hidden={{ ...hidden, item_type: type }} doneMessage="Salvo." />
      {titleToo && <ActionForm action={saveDiscoveryItem} submit="Salvar título" tone="quiet" hidden={{ ...hidden, item_type: "titulo" }} doneMessage="Salvo." />}
    </>
  );
}

function ChannelList({ channels, channel, run }: { channels: ChannelResult[]; channel?: string; run: string }) {
  if (!channels.length) return <Empty title="Nenhum canal encontrado.">Aumente o limite de inscritos, amplie o período ou use um termo mais curto.</Empty>;
  return (
    <ul className="divide-y divide-line">
      {channels.map((item) => (
        <li key={item.id} className="flex flex-wrap items-start justify-between gap-3 p-3">
          <div className="min-w-0 flex-1 basis-56">
            <Link className="text-sm font-medium hover:text-cobalt hover:underline" href={`/concorrentes/${item.id}`}>{item.title}</Link>
            <p className="mt-0.5 text-[0.8125rem] text-ink-3">{[item.handle, item.country ?? "País não informado", `medido em ${dateTime(item.text_refreshed_at)}`].filter(Boolean).join(", ")}</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem]">
              <span><Value metric={item.subscribers} format={compact} muted="Oculto" /> inscritos</span>
              <SourceLink url={item.source_url} />
            </div>
          </div>
          {channel && <div className="flex shrink-0 flex-wrap gap-2"><SaveButtons channel={channel} run={run} type="canal" id={item.id} /></div>}
        </li>
      ))}
    </ul>
  );
}

export default async function DiscoveryResult({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const query = await searchParams;
  const offset = Number(str(query.inicio)) || 0;
  const data = await intelGetOrNull<DiscoveryView>(`/discovery/runs/${id}`, { offset: String(offset) });
  if (!data) notFound();
  const { run, channel } = data;
  const channelId = channel?.id;
  const filters = [run.filters.niche, run.filters.subniche, run.filters.language && `Idioma ${run.filters.language}`, run.filters.country && `País ${run.filters.country}`, run.filters.days && `Últimos ${run.filters.days} dias`, run.filters.format && FORMAT_LABEL[run.filters.format], run.filters.max_subscribers && `Até ${compact(run.filters.max_subscribers)} inscritos`].filter(Boolean);
  const isChannels = run.kind === "channels" || run.kind === "emerging";
  const videoActions = channelId ? (video: VideoRow) => (
    <div className="flex flex-col items-end gap-1.5">
      <FormatPill estimate={data.format_estimates[video.id]} format={video.format} />
      <div className="flex flex-wrap justify-end gap-2"><SaveButtons channel={channelId} run={run.id} type="video" id={video.id} titleToo /></div>
    </div>
  ) : (video: VideoRow) => <FormatPill estimate={data.format_estimates[video.id]} format={video.format} />;

  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href="/descobrir?aba=historico">Voltar ao histórico</Link></p>
      <PageHeader title={run.query} intro={`${run.kind_label}, em ${dateTime(run.executed_at)}. ${channel ? `Para ${channel.name}.` : "Sem canal associado: associe um canal para salvar."}`}>
        <OriginPill fictional={run.fictional} simulated={run.simulated} />
      </PageHeader>
      <div className="mb-4 space-y-2">
        <ProvenanceNote run={run} />
        <p className="text-sm text-ink-2">Filtros: {filters.length ? filters.join(", ") : "nenhum"}.</p>
        {data.filter_notes.map((note) => <Notice key={note}>{note}</Notice>)}
        {data.blocked_metrics && <Notice tone="warn" title="Só dados crus">{data.blocked_metrics} <Link className="underline" href="/sistema">Ver o que falta</Link></Notice>}
        {data.removed > 0 && <Notice tone="warn">{data.removed} {data.removed === 1 ? "item saiu" : "itens saíram"} da base: o texto da API tem prazo de 30 dias sem atualização.</Notice>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <section aria-labelledby="observado" className="min-w-0">
          <h2 id="observado" className="mb-1 font-display text-[1.125rem] font-semibold">Observado</h2>
          <p className="mb-2 text-[0.8125rem] text-ink-3">{data.observed.note}</p>
          <Panel>
            {isChannels ? <ChannelList channels={data.channels} channel={channelId} run={run.id} /> : <VideoResults videos={data.videos} actions={videoActions} />}
            <Pagination total={data.total} limit={data.limit} offset={data.offset} href={(next) => `/descobrir/${run.id}?inicio=${next}`} />
          </Panel>
        </section>

        <div className="min-w-0 space-y-4">
          <section aria-labelledby="estimado">
            <h2 id="estimado" className="mb-1 font-display text-[1.125rem] font-semibold">Estimado</h2>
            <Panel className="p-4">
              <ul className="space-y-3 text-sm">
                {data.estimates.map((item) => (
                  <li key={item.label}>
                    <p className="font-medium">{item.label}: {item.value === null ? "indisponível" : `cerca de ${compact(item.value)}`}</p>
                    <p className="text-[0.8125rem] text-ink-3">{item.note}</p>
                  </li>
                ))}
                {!isChannels && <li><p className="font-medium">Formato de cada vídeo</p><p className="text-[0.8125rem] text-ink-3">Passe o ponteiro na etiqueta para ver a base. A API não informa a proporção: vídeo curto sem indício fica indeterminado, em vez de virar Short por palpite.</p></li>}
              </ul>
            </Panel>
          </section>

          <section aria-labelledby="hipoteses">
            <h2 id="hipoteses" className="mb-1 font-display text-[1.125rem] font-semibold">Hipóteses editoriais</h2>
            <Panel className="p-4">
              <p className="mb-2 text-[0.8125rem] text-ink-3">{data.hypotheses_note}</p>
              <ul className="space-y-3 text-sm">
                {data.hypotheses.map((item) => <li key={item.text}><p>{item.text}</p><p className="text-[0.8125rem] text-ink-3">Base: {item.basis}</p></li>)}
              </ul>
              {channelId && (
                <div className="mt-4 border-t border-line pt-3">
                  <SectionTitle>Salvar um tema de interesse</SectionTitle>
                  <ActionForm action={saveDiscoveryItem} submit="Salvar tema" tone="quiet" hidden={{ channel_id: channelId, run_id: run.id, item_type: "tema" }} className="mt-2 space-y-2" doneMessage="Tema salvo." resetOnSuccess>
                    <label className="block text-[0.8125rem] text-ink-2">Tema, com as suas palavras<input name="text" required minLength={3} maxLength={200} defaultValue={run.query} className="field mt-1 w-full" /></label>
                    <label className="block text-[0.8125rem] text-ink-2">Sua hipótese ou nota<textarea name="note" rows={2} maxLength={1000} className="field mt-1 mb-2 w-full" /></label>
                  </ActionForm>
                  <p className="mt-2 text-[0.8125rem]"><Link className="text-cobalt underline underline-offset-2" href={`/descobrir?aba=salvos&canal=${channelId}`}>Ver o que está salvo neste canal</Link></p>
                </div>
              )}
            </Panel>
          </section>
        </div>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
