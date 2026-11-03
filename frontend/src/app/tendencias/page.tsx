import { BlockedNotice, Empty, FormatTabs, PageHeader, Panel, formatParam, str } from "@/components/ui";
import { api, type Filters, type TrendTerm } from "@/lib/api";
import { decimal, integer, percent, times } from "@/lib/format";

interface Response { blocked: boolean; reason?: string; items: TrendTerm[]; origin_note?: string; window_hours?: number }

export default async function Trends({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = formatParam(params.f);
  const niche = str(params.niche_id);
  const [data, filters] = await Promise.all([api<Response>("/api/trends", { format, niche_id: niche }), api<Filters>("/api/filters")]);
  return (
    <>
      <PageHeader title="Tendências" intro={`Termos de títulos cujos vídeos ganharam velocidade, comparando as últimas ${data.window_hours ?? 24} h com as ${data.window_hours ?? 24} h anteriores. Exige mais de um canal.`}>
        <FormatTabs current={format} basePath="/tendencias" params={{ niche_id: niche }} />
      </PageHeader>
      {data.blocked ? <BlockedNotice reason={data.reason} /> : (
        <>
          <form className="mb-4 flex items-end gap-2">
            <input type="hidden" name="f" value={format} />
            <label className="text-[0.8125rem] text-ink-2">Nicho<br />
              <select name="niche_id" defaultValue={niche ?? ""} className="field"><option value="">Todos</option>{filters.niches.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}</select>
            </label>
            <button className="min-h-9 rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Aplicar filtro</button>
          </form>
          <Panel>
            {data.items.length === 0 ? <Empty title="Nenhum termo em alta neste formato.">Os snapshots precisam cobrir as duas últimas janelas em mais de um canal.</Empty> : (
              <div className="overflow-x-auto">
                <table className="data-table w-full min-w-[42rem]">
                  <thead>
                    <tr>
                      <th scope="col">Termo</th>
                      <th scope="col" className="num">Vídeos acelerando</th>
                      <th scope="col" className="num">Canais</th>
                      <th scope="col" className="num">Views/h agora</th>
                      <th scope="col" className="num">Views/h antes</th>
                      <th scope="col" className="num">Razão</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((term) => (
                      <tr key={term.term}>
                        <td className="font-medium">{term.term}</td>
                        <td className="num">{term.accelerating} de {term.videos} ({percent(term.accelerating_share * 100)})</td>
                        <td className="num">{integer(term.channels)}</td>
                        <td className="num">{decimal(term.recent_vph_sum)}</td>
                        <td className="num">{decimal(term.previous_vph_sum)}</td>
                        <td className="num">{term.velocity_ratio === null ? "Sem base" : times(term.velocity_ratio)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <p className="mt-3 text-[0.8125rem] text-ink-3">Termos são contados nos títulos, sem interpretar o significado. {data.origin_note}</p>
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
