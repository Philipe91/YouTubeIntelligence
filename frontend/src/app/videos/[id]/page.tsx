import Link from "next/link";
import { notFound } from "next/navigation";

import { Bars, ViewsChart } from "@/components/Charts";
import { StudyForm } from "@/components/StudyForm";
import { Value } from "@/components/Mark";
import { AccelerationPill, BandPill, BlockedNotice, ConfidencePill, PageHeader, Panel, Pill, SectionTitle, SourceLink, Thumb } from "@/components/ui";
import { apiOrNull, type VideoDetail } from "@/lib/api";
import { FLAG_LABEL, FORMAT_LABEL, age, dateTime, decimal, duration, integer, shortDate, times } from "@/lib/format";

function Fact({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="border-l-2 border-line pl-3">
      <dt className="text-[0.8125rem] text-ink-3">{label}</dt>
      <dd className="mt-0.5 font-display text-[1.25rem] font-semibold">{children}</dd>
      {note && <dd className="text-[0.8125rem] text-ink-3">{note}</dd>}
    </div>
  );
}

export default async function VideoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const video = await apiOrNull<VideoDetail>(`/api/videos/${encodeURIComponent(id)}`);
  if (!video) notFound();
  const flags = [...new Set(video.intervals.flatMap((i) => i.flags))];
  return (
    <>
      <PageHeader title={video.title}>
        <SourceLink url={video.source_url} />
      </PageHeader>
      <StudyForm videoId={video.id} />
      <div className="mb-5 -mt-3 flex flex-wrap items-center gap-3 text-sm text-ink-2">
        <Thumb video={video} />
        <div className="space-y-1">
          <div><Link href={`/concorrentes/${video.channel_id}`} className="text-cobalt underline underline-offset-2">{video.channel_title}</Link></div>
          <div>Publicado em {shortDate(video.published_at)}, há {age(video.age_hours)}. {duration(video.duration_seconds)}.</div>
          <div className="flex items-center gap-1.5"><Value metric={{ ...video.format_label, value: 1 }} format={() => FORMAT_LABEL[video.format]} /><span className="text-ink-3">{video.format_label.source}</span></div>
        </div>
      </div>

      <Panel className="p-5">
        <dl className="grid grid-cols-2 gap-5 lg:grid-cols-4">
          <Fact label="Views" note={`Medido em ${dateTime(video.views.as_of)}`}><Value metric={video.views} format={integer} /></Fact>
          <Fact label="VPH observado" note="Velocidade entre os dois últimos snapshots"><Value metric={video.vph_observed} format={decimal} /></Fact>
          <Fact label="Média histórica" note="Views ÷ horas desde a publicação"><Value metric={video.vph_average} format={decimal} /></Fact>
          <Fact label="IDR" note="Comparação com o próprio canal"><Value metric={video.idr} format={times} /></Fact>
        </dl>
      </Panel>

      {video.derived_blocked ? (
        <div className="mt-4"><BlockedNotice reason={video.idr.reason ?? undefined} /></div>
      ) : (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel className="p-4">
              <div className="flex flex-wrap items-center gap-2"><SectionTitle>Desempenho relativo</SectionTitle><BandPill video={video} /><ConfidencePill level={video.outlier?.confidence ?? null} /></div>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{video.outlier_explanation}</p>
              {video.outlier?.robust_z != null && <p className="mt-1 text-[0.8125rem] text-ink-3">Desvio robusto: {decimal(video.outlier.robust_z)} (distância da mediana, em unidades de dispersão, escala log).</p>}
              {video.outlier?.warnings.map((warning) => <p key={warning} className="mt-1 text-[0.8125rem] text-warn">Atenção: {FLAG_LABEL[warning] ?? warning}.</p>)}
            </Panel>
            <Panel className="p-4">
              <div className="flex flex-wrap items-center gap-2"><SectionTitle>Velocidade recente</SectionTitle>{video.acceleration && <AccelerationPill status={video.acceleration.status} />}</div>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{video.acceleration_explanation}</p>
              {video.acceleration?.ratio != null && <p className="mt-1 text-[0.8125rem] text-ink-3">Razão entre janelas: {times(video.acceleration.ratio)}. Vídeos novos costumam desacelerar naturalmente.</p>}
            </Panel>
          </div>

          <Panel className="mt-4 p-4">
            <SectionTitle>Views por idade do vídeo</SectionTitle>
            <div className="mt-3">
              <ViewsChart
                target={video.snapshots.map((s) => ({ age: s.age_hours, views: s.views }))}
                peers={video.peer_curve.map((p) => ({ age: p.age_hours, views: p.median_views, sample: p.sample }))}
              />
            </div>
            {video.snapshots.length > 0 && video.snapshots[0].age_hours > 48 && (
              <p className="mt-2 text-[0.8125rem] text-ink-3">O monitoramento deste vídeo começou aos {age(video.snapshots[0].age_hours)}: antes disso não há medição.</p>
            )}
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-cobalt">Ver os {video.snapshots.length} snapshots em tabela</summary>
              <div className="mt-2 max-h-64 overflow-auto">
                <table className="data-table w-full">
                  <thead><tr><th scope="col">Medição</th><th scope="col" className="num">Idade</th><th scope="col" className="num">Views</th></tr></thead>
                  <tbody>{[...video.snapshots].reverse().map((s) => <tr key={s.captured_at}><td>{dateTime(s.captured_at)}</td><td className="num">{age(s.age_hours)}</td><td className="num">{integer(s.views)}</td></tr>)}</tbody>
                </table>
              </div>
            </details>
          </Panel>

          <Panel className="mt-4 p-4">
            <SectionTitle>VPH observado por intervalo</SectionTitle>
            <p className="mt-0.5 mb-3 text-sm text-ink-2">Últimos {video.intervals.length} intervalos entre snapshots. Lacuna indica intervalo sem valor confiável.</p>
            <Bars
              title="Views por hora em cada intervalo entre snapshots"
              unit="views/h"
              points={video.intervals.map((i) => ({
                label: dateTime(i.end),
                value: i.vph,
                note: i.flags.map((flag) => FLAG_LABEL[flag] ?? flag).join(", ") || undefined,
              }))}
            />
            {flags.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{flags.map((flag) => <Pill key={flag} tone="warn">{FLAG_LABEL[flag] ?? flag}</Pill>)}</div>}
          </Panel>
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
