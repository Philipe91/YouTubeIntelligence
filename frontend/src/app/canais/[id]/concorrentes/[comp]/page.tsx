import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { BlockedNotice, PageHeader, Panel, Pill, SectionTitle, SourceLink, str } from "@/components/ui";
import { Notice, OriginPill, Pagination, VideoResults } from "@/components/intel";
import { compact, decimal, duration, FORMAT_LABEL, percent, shortDate } from "@/lib/format";
import { intelGetOrNull, type CompetitorDetail } from "@/lib/intel";

import { addOpportunity, addStudy, refreshCompetitor } from "../../../../intel-actions";

export default async function CompetitorPage({ params, searchParams }: { params: Promise<{ id: string; comp: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id, comp } = await params;
  const query = await searchParams;
  const offset = Number(str(query.inicio)) || 0;
  const data = await intelGetOrNull<CompetitorDetail>(`/channels/${id}/competitors/${comp}`, { offset: String(offset) });
  if (!data) notFound();
  const back = `/canais/${id}/concorrentes`;
  if (!data.linked || !data.summary?.channel || !data.videos) {
    return (
      <>
        <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href={back}>Voltar aos concorrentes</Link></p>
        <PageHeader title={data.competitor.name} />
        <Notice tone="warn" title="Sem vínculo com um canal do YouTube">{data.usable ? "Vincule pelo link, @nome ou ID na lista de concorrentes." : "Neste modo, este canal não recebe dados."}</Notice>
      </>
    );
  }
  const { channel } = data.summary;
  const saved = new Set(data.study_ids ?? []);
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href={back}>Voltar aos concorrentes</Link></p>
      <PageHeader title={channel.title} intro={data.competitor.notes || undefined}>
        <div className="flex flex-wrap items-center gap-2">
          <OriginPill fictional={Boolean(data.fictional)} />
          <SourceLink url={channel.source_url} label="Canal no YouTube" />
          {!data.fictional && <ActionForm action={refreshCompetitor} submit="Atualizar vídeos" tone="quiet" pending="Atualizando..." hidden={{ channel_id: id, competitor_id: comp }} />}
        </div>
      </PageHeader>
      <p className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-ink-2">
        <span><Value metric={channel.subscribers} format={compact} muted="Oculto" /> inscritos</span>
        <span>{channel.country ?? "País não informado"}</span>
        <span>{data.videos.total} vídeos coletados</span>
      </p>

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-4">
          <Panel>
            <div className="border-b border-line p-3"><SectionTitle>Vídeos recentes</SectionTitle></div>
            <VideoResults
              videos={data.videos.items}
              actions={(video) => saved.has(video.id) ? <Pill tone="good">Referência salva</Pill> : <ActionForm action={addStudy} submit="Salvar referência" tone="quiet" hidden={{ channel_id: id, video_id: video.id, origin: "competidor" }} />}
            />
            <Pagination total={data.videos.total} limit={data.videos.limit} offset={data.videos.offset} href={(next) => `/canais/${id}/concorrentes/${comp}?inicio=${next}`} />
          </Panel>
          {data.patterns_blocked ? <BlockedNotice reason={data.reason ?? undefined} /> : (
            <Panel className="p-4">
              <SectionTitle>Padrões editoriais</SectionTitle>
              <div className="mt-3 grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="text-sm font-medium">Assuntos recorrentes</h3>
                  <ul className="mt-1.5 flex flex-wrap gap-1.5 text-[0.8125rem]">{data.recurring_subjects?.map((item) => <li key={item.term} className="rounded border border-line px-2 py-0.5">{item.term} <span className="text-ink-3">{item.videos}</span></li>)}</ul>
                </div>
                <div>
                  <h3 className="text-sm font-medium">Padrões de título, por regra</h3>
                  <ul className="mt-1.5 space-y-1 text-[0.8125rem]">{data.title_patterns?.map((item) => <li key={item.pattern} className="flex justify-between gap-3"><span>{item.pattern}</span><span className="text-ink-3">{item.videos} vídeos</span></li>)}</ul>
                </div>
              </div>
              {data.editorial && (
                <div className="mt-4 overflow-x-auto">
                  <table className="data-table w-full">
                    <thead><tr><th>Formato</th><th className="num">Vídeos</th><th className="num">Por semana</th><th className="num">Duração típica</th><th className="num">Em pergunta</th><th>Dia mais comum</th></tr></thead>
                    <tbody>{Object.entries(data.editorial).map(([format, row]) => (
                      <tr key={format}><td>{FORMAT_LABEL[format]}</td><td className="num">{row.sample_size}</td><td className="num">{row.uploads_per_week === null ? "Sem dado" : decimal(row.uploads_per_week)}</td><td className="num">{row.median_duration_seconds === null ? "Sem dado" : duration(row.median_duration_seconds)}</td><td className="num">{row.question_title_share === null ? "Sem dado" : percent(row.question_title_share * 100)}</td><td>{row.top_weekday ?? "Sem dado"}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
              <p className="mt-3 text-[0.8125rem] text-ink-3">Hábitos observados entre os vídeos coletados, não recomendação de horário nem garantia. {data.origin_note}</p>
            </Panel>
          )}
        </div>
        <div className="min-w-0 space-y-4">
          <Panel className="p-4">
            <SectionTitle>Calendário de publicação</SectionTitle>
            <p className="mt-0.5 text-[0.8125rem] text-ink-3">Vídeos coletados nos últimos {data.calendar_days} dias.</p>
            {data.calendar?.length ? (
              <ol className="mt-3 max-h-96 space-y-2 overflow-y-auto text-[0.8125rem]">
                {data.calendar.map((entry) => (
                  <li key={entry.day}><p className="font-medium">{shortDate(`${entry.day}T12:00:00Z`)}</p><ul className="text-ink-2">{entry.videos.map((video) => <li key={video.id}><Link className="hover:underline" href={`/videos/${video.id}`}>{video.title}</Link> <span className="text-ink-3">{FORMAT_LABEL[video.format]}</span></li>)}</ul></li>
                ))}
              </ol>
            ) : <p className="mt-3 text-sm text-ink-3">Nenhum vídeo coletado nesse período.</p>}
          </Panel>
          <Panel className="p-4">
            <SectionTitle>Registrar oportunidade</SectionTitle>
            <ActionForm action={addOpportunity} submit="Registrar" resetOnSuccess hidden={{ channel_id: id }} className="mt-3" doneMessage="Registrada.">
              <div className="mb-3 space-y-2">
                <label className="block text-[0.8125rem] text-ink-2">Oportunidade<input name="title" required minLength={3} maxLength={200} className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Por quê<input name="note" maxLength={1000} className="field mt-1 w-full" /></label>
              </div>
            </ActionForm>
          </Panel>
        </div>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
