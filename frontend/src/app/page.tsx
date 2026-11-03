import Link from "next/link";

import { Value } from "@/components/Mark";
import { OpportunityCard } from "@/components/OpportunityCard";
import { VideoTable } from "@/components/VideoTable";
import { AccelerationPill, BandPill, BlockedNotice, Empty, FormatTabs, PageHeader, Panel, SectionTitle, Thumb, formatParam } from "@/components/ui";
import { api, type Overview, type VideoRow } from "@/lib/api";
import { age, decimal, integer, times } from "@/lib/format";

function VideoLine({ video, metric }: { video: VideoRow; metric: "vph" | "idr" }) {
  return (
    <li className="flex items-center gap-3 py-2.5">
      <Thumb video={video} size="sm" />
      <div className="min-w-0 flex-1">
        <Link href={`/videos/${video.id}`} className="line-clamp-1 text-sm font-medium hover:text-cobalt hover:underline">{video.title}</Link>
        <div className="truncate text-[0.8125rem] text-ink-3">{video.channel_title}, {age(video.age_hours)}</div>
      </div>
      <div className="shrink-0 text-right text-sm">
        {metric === "vph" ? (
          <>
            <Value metric={video.vph_observed} format={(v) => `${decimal(v)}/h`} />
            <div className="mt-0.5">{video.acceleration && <AccelerationPill status={video.acceleration.status} />}</div>
          </>
        ) : (
          <>
            <Value metric={video.idr} format={times} />
            <div className="mt-0.5"><BandPill video={video} /></div>
          </>
        )}
      </div>
    </li>
  );
}

export default async function Today({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = formatParam(params.f);
  const data = await api<Overview>("/api/overview", { format });
  const label = format === "short" ? "Shorts" : "vídeos longos";

  if (data.blocked) {
    return (
      <>
        <PageHeader title="Hoje" intro="Últimos vídeos coletados, sem cálculos."><FormatTabs current={format} basePath="/" /></PageHeader>
        <BlockedNotice reason={data.reason} />
        <Panel className="mt-6"><VideoTable videos={data.recent ?? []} /></Panel>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={`O que olhar agora em ${label}`}
        intro={`${integer(data.health.rising)} vídeos ganhando velocidade e ${integer(data.health.outliers)} bem acima do típico para o próprio canal, entre ${integer(data.health.videos)} monitorados.`}
      >
        <FormatTabs current={format} basePath="/" />
      </PageHeader>

      <div className="flex items-baseline justify-between gap-4">
        <SectionTitle>Temas para avaliar</SectionTitle>
        <Link href={`/oportunidades?f=${format}`} className="text-sm text-cobalt underline underline-offset-2">Ver o ranking completo</Link>
      </div>
      <p className="mt-1 mb-3 text-sm text-ink-2">Ranking experimental: mostra onde vale pesquisar, não o resultado de um vídeo.</p>
      {data.top_opportunities.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {data.top_opportunities.map((item, index) => (
            <OpportunityCard key={item.topic} item={item} rank={item.score.value === null ? undefined : index + 1} />
          ))}
        </div>
      ) : (
        <Panel><Empty title="Nenhuma busca registrada.">Rode uma pesquisa de nicho para gerar temas.</Empty></Panel>
      )}

      <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel className="p-4">
          <SectionTitle>Ganhando velocidade</SectionTitle>
          <p className="mt-0.5 text-sm text-ink-2">Views por hora nas últimas 24 h maiores que nas 24 h anteriores.</p>
          {data.rising.length ? (
            <ul className="mt-2 divide-y divide-line">{data.rising.map((video) => <VideoLine key={video.id} video={video} metric="vph" />)}</ul>
          ) : (
            <Empty title="Nenhum vídeo acelerando.">São necessários snapshots cobrindo as duas últimas janelas.</Empty>
          )}
        </Panel>
        <Panel className="p-4">
          <SectionTitle>Muito acima do próprio canal</SectionTitle>
          <p className="mt-0.5 text-sm text-ink-2">Comparados a vídeos do mesmo canal e formato, na mesma idade.</p>
          {data.outliers.length ? (
            <ul className="mt-2 divide-y divide-line">{data.outliers.map((video) => <VideoLine key={video.id} video={video} metric="idr" />)}</ul>
          ) : (
            <Empty title="Nenhum vídeo fora do padrão neste formato." />
          )}
        </Panel>
      </div>

      <Panel className="mt-4 p-4">
        <div className="flex items-baseline justify-between gap-4">
          <SectionTitle>Termos em alta</SectionTitle>
          <Link href={`/tendencias?f=${format}`} className="text-sm text-cobalt underline underline-offset-2">Ver tendências</Link>
        </div>
        {data.trends.length ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {data.trends.map((term) => (
              <li key={term.term} className="rounded-md border border-line px-2.5 py-1 text-sm">
                {term.term} <span className="text-ink-3">{term.accelerating} de {term.videos} vídeos, {term.channels} canais</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-ink-3">Nenhum termo com vídeos suficientes em mais de um canal.</p>
        )}
        <p className="mt-3 text-[0.8125rem] text-ink-3">{integer(data.health.insufficient_sample)} vídeos sem IDR por amostra insuficiente. {data.origin_note}</p>
      </Panel>
    </>
  );
}

export const dynamic = "force-dynamic";
