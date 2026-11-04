import Link from "next/link";

import { Value } from "@/components/Mark";
import { Empty, PageHeader, Panel, Pill, SourceLink, str, Thumb } from "@/components/ui";
import { Notice } from "@/components/intel";
import { compact, duration, FORMAT_LABEL, shortDate, times } from "@/lib/format";
import { intelGet, type StudyComparison } from "@/lib/intel";

export default async function CompareVideos({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const channel = str(params.canal);
  const ids = Array.isArray(params.ids) ? params.ids : params.ids ? [params.ids] : [];
  const back = `/explorer?aba=estudo${channel ? `&canal=${channel}` : ""}`;
  let data: StudyComparison;
  try {
    data = await intelGet<StudyComparison>(`/channels/${channel}/study/compare`, { ids: ids.join(",") });
  } catch (error) {
    return (
      <Panel>
        <Empty title="Não dá para comparar esta seleção.">{(error as { message_api?: string }).message_api ?? "Volte e marque de 2 a 6 vídeos."}</Empty>
        <p className="pb-6 text-center text-sm"><Link className="text-cobalt underline underline-offset-2" href={back}>Voltar à lista de estudo</Link></p>
      </Panel>
    );
  }
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href={back}>Voltar à lista de estudo</Link></p>
      <PageHeader title="Comparar títulos e abordagens" intro={data.note} />
      {data.features_blocked && <div className="mb-4"><Notice tone="warn" title="Leitura dos títulos bloqueada">{data.reason} Os dados crus e as suas notas continuam aqui.</Notice></div>}
      {data.shared_words.length > 0 && <p className="mb-3 text-sm text-ink-2">Palavras em todos os títulos: {data.shared_words.join(", ")}.</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.columns.map(({ video, note, features }) => (
          <Panel key={video.id} className="p-4">
            <Thumb video={video} />
            <h2 className="mt-3 text-[0.9375rem] leading-snug font-semibold">{video.title}</h2>
            <dl className="mt-3 space-y-1.5 text-sm">
              <div className="flex justify-between gap-3"><dt className="text-ink-3">Canal</dt><dd className="text-right">{video.channel_title}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-3">Publicado</dt><dd>{shortDate(video.published_at)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-3">Formato</dt><dd>{FORMAT_LABEL[video.format] ?? video.format}, {duration(video.duration_seconds)}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-3">Views</dt><dd><Value metric={video.views} format={compact} /></dd></div>
              {!video.derived_blocked && <div className="flex justify-between gap-3"><dt className="text-ink-3">IDR</dt><dd><Value metric={video.idr} format={times} /></dd></div>}
              {features && (
                <>
                  <div className="flex justify-between gap-3"><dt className="text-ink-3">Abordagem, por regra</dt><dd className="text-right"><Pill tone="info">{features.approach_label}</Pill></dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-ink-3">Tamanho</dt><dd>{features.characters} caracteres, {features.words} palavras</dd></div>
                </>
              )}
            </dl>
            <p className="mt-3 text-sm"><span className="text-ink-3">Sua nota:</span> {note || "Ainda sem nota."}</p>
            <div className="mt-2"><SourceLink url={video.source_url} /></div>
          </Panel>
        ))}
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
