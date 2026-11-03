import { notFound } from "next/navigation";

import { Value } from "@/components/Mark";
import { VideoTable } from "@/components/VideoTable";
import { BlockedNotice, Empty, FormatTabs, PageHeader, Panel, SectionTitle, SourceLink, formatParam } from "@/components/ui";
import { api, apiOrNull, type ChannelDetail, type VideoRow } from "@/lib/api";
import { compact, decimal, duration, integer, percent, times } from "@/lib/format";

export default async function ChannelPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const format = formatParam((await searchParams).f);
  const [channel, videos] = await Promise.all([
    apiOrNull<ChannelDetail>(`/api/channels/${encodeURIComponent(id)}`),
    api<{ total: number; items: VideoRow[] }>("/api/videos", { channel_id: id, format, sort: "idr", limit: "50" }),
  ]);
  if (!channel) notFound();
  const profile = channel.editorial?.[format];
  return (
    <>
      <PageHeader title={channel.title} intro={[channel.niche, channel.country, channel.language].filter(Boolean).join(", ")}>
        <div className="flex items-center gap-4">
          <SourceLink url={channel.source_url} label="Abrir canal" />
          <FormatTabs current={format} basePath={`/concorrentes/${id}`} />
        </div>
      </PageHeader>
      <p className="mb-4 text-sm text-ink-2">Inscritos: <Value metric={channel.subscribers} format={compact} muted="Oculto pelo canal" /></p>

      {!channel.editorial ? <BlockedNotice reason="Cadência, medianas e termos são métricas derivadas e dependem do aceite do uso analítico." /> : profile && profile.sample_size > 0 ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel className="p-4">
            <SectionTitle>Ritmo e formato</SectionTitle>
            <dl className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
              <dt className="text-ink-2">Vídeos analisados</dt><dd className="text-right">{integer(profile.sample_size)}</dd>
              <dt className="text-ink-2">Publicações por semana</dt><dd className="text-right">{profile.uploads_per_week === null ? "Sem dado" : decimal(profile.uploads_per_week)}</dd>
              <dt className="text-ink-2">Duração típica</dt><dd className="text-right">{profile.median_duration_seconds === null ? "Sem dado" : duration(profile.median_duration_seconds)}</dd>
              <dt className="text-ink-2">Dia mais comum</dt><dd className="text-right">{profile.top_weekday ?? "Sem dado"}</dd>
            </dl>
          </Panel>
          <Panel className="p-4">
            <SectionTitle>Títulos</SectionTitle>
            <dl className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
              <dt className="text-ink-2">Palavras (mediana)</dt><dd className="text-right">{profile.median_title_words === null ? "Sem dado" : integer(profile.median_title_words)}</dd>
              <dt className="text-ink-2">Em forma de pergunta</dt><dd className="text-right">{profile.question_title_share === null ? "Sem dado" : percent(profile.question_title_share * 100)}</dd>
              <dt className="text-ink-2">Com número</dt><dd className="text-right">{profile.number_title_share === null ? "Sem dado" : percent(profile.number_title_share * 100)}</dd>
            </dl>
            <p className="mt-3 text-sm text-ink-2">Mais usados: {profile.top_terms.slice(0, 5).map(([term]) => term).join(", ") || "sem dados"}.</p>
          </Panel>
          <Panel className="p-4">
            <SectionTitle>Termos com melhor desempenho</SectionTitle>
            {profile.overperforming_terms.length ? (
              <ul className="mt-2 space-y-1 text-sm">
                {profile.overperforming_terms.map((term) => (
                  <li key={term.term} className="flex justify-between gap-3"><span>{term.term}</span><span className="text-ink-2">{times(term.median_idr)} em {term.videos} vídeos</span></li>
                ))}
              </ul>
            ) : <p className="mt-2 text-sm text-ink-3">Sem vídeos suficientes com IDR para comparar termos.</p>}
            <p className="mt-3 text-[0.8125rem] text-ink-3">{channel.editorial_note}</p>
          </Panel>
        </div>
      ) : <Panel><Empty title="Este canal não tem vídeos neste formato." /></Panel>}

      <h2 className="mt-8 mb-3 font-display text-[1.1875rem] font-semibold">Vídeos do canal</h2>
      <Panel><VideoTable videos={videos.items} showChannel={false} /></Panel>
    </>
  );
}

export const dynamic = "force-dynamic";
