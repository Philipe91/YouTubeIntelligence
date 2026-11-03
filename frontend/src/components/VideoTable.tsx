import Link from "next/link";

import { Value } from "@/components/Mark";
import { AccelerationPill, BandPill, ConfidencePill, Empty, Thumb } from "@/components/ui";
import type { VideoRow } from "@/lib/api";
import { age, compact, decimal, duration, integer, times } from "@/lib/format";

export function VideoTable({ videos, showChannel = true }: { videos: VideoRow[]; showChannel?: boolean }) {
  if (videos.length === 0) {
    return <Empty title="Nenhum vídeo com esses filtros.">Amplie o período ou remova um filtro.</Empty>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table w-full min-w-[56rem]">
        <thead>
          <tr>
            <th scope="col">Vídeo</th>
            <th scope="col" className="num">Views</th>
            <th scope="col" className="num" title="Diferença de views entre os dois últimos snapshots, por hora">VPH observado</th>
            <th scope="col" className="num" title="Views divididas pelas horas desde a publicação. Não é velocidade recente">Média histórica</th>
            <th scope="col" className="num" title="Views ÷ mediana de vídeos do mesmo canal e formato na mesma idade">IDR</th>
            <th scope="col">Leitura</th>
            <th scope="col">Velocidade</th>
          </tr>
        </thead>
        <tbody>
          {videos.map((video) => (
            <tr key={video.id}>
              <td className="max-w-[26rem]">
                <div className="flex items-center gap-3">
                  <Thumb video={video} size="sm" />
                  <div className="min-w-0">
                    <Link href={`/videos/${video.id}`} className="line-clamp-2 font-medium text-ink hover:text-cobalt hover:underline">{video.title}</Link>
                    <div className="mt-0.5 text-[0.8125rem] text-ink-3">
                      {showChannel && <><Link href={`/concorrentes/${video.channel_id}`} className="hover:underline">{video.channel_title}</Link>, </>}
                      {age(video.age_hours)}, {duration(video.duration_seconds)}
                    </div>
                  </div>
                </div>
              </td>
              <td className="num"><Value metric={video.views} format={compact} /></td>
              <td className="num"><Value metric={video.vph_observed} format={decimal} /></td>
              <td className="num"><Value metric={video.vph_average} format={decimal} /></td>
              <td className="num"><Value metric={video.idr} format={times} /></td>
              <td>
                <BandPill video={video} />
                {video.outlier?.status === "ok" && <div className="mt-0.5"><ConfidencePill level={video.outlier.confidence} /></div>}
                {video.outlier?.status === "insufficient_sample" && <div className="mt-0.5 text-[0.8125rem] text-ink-3">n = {integer(video.outlier.sample_size)}</div>}
              </td>
              <td>{video.acceleration ? <AccelerationPill status={video.acceleration.status} /> : <span className="text-ink-3">Bloqueado</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
