import Link from "next/link";

import { Value } from "@/components/Mark";
import { opportunityHref } from "@/components/OpportunityCard";
import { BlockedNotice, Empty, FormatTabs, PageHeader, Panel, Pill, formatParam, str } from "@/components/ui";
import { api, type Filters, type OpportunityRow } from "@/lib/api";
import { integer } from "@/lib/format";

interface Response { blocked: boolean; reason?: string; notice?: string; origin_note?: string; items: OpportunityRow[] }

export default async function Opportunities({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = formatParam(params.f);
  const niche = str(params.niche_id);
  const language = str(params.language);
  const country = str(params.country);
  const [data, filters] = await Promise.all([
    api<Response>("/api/opportunities", { format, niche_id: niche, language, country }),
    api<Filters>("/api/filters"),
  ]);
  return (
    <>
      <PageHeader title="Oportunidades" intro={data.notice ?? "Temas das buscas registradas, com indicadores separados."}>
        <FormatTabs current={format} basePath="/oportunidades" params={{ niche_id: niche, language, country }} />
      </PageHeader>
      {data.blocked ? <BlockedNotice reason={data.reason} /> : (
        <>
          <form className="mb-4 flex flex-wrap items-end gap-2">
            <input type="hidden" name="f" value={format} />
            <label className="text-[0.8125rem] text-ink-2">Nicho<br />
              <select name="niche_id" defaultValue={niche ?? ""} className="field"><option value="">Todos</option>{filters.niches.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}</select>
            </label>
            <label className="text-[0.8125rem] text-ink-2">Idioma<br />
              <select name="language" defaultValue={language ?? ""} className="field"><option value="">Todos</option>{filters.languages.map((l) => <option key={l} value={l}>{l}</option>)}</select>
            </label>
            <label className="text-[0.8125rem] text-ink-2">País<br />
              <select name="country" defaultValue={country ?? ""} className="field"><option value="">Todos</option>{filters.countries.map((c) => <option key={c} value={c}>{c}</option>)}</select>
            </label>
            <button className="min-h-9 rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Aplicar filtros</button>
          </form>
          <Panel>
            {data.items.length === 0 ? <Empty title="Nenhum tema com esses filtros.">Rode uma pesquisa de nicho ou altere os filtros.</Empty> : (
              <div className="overflow-x-auto">
                <table className="data-table w-full min-w-[50rem]">
                  <thead>
                    <tr>
                      <th scope="col">Tema</th>
                      <th scope="col" className="num">Pontuação</th>
                      <th scope="col" className="num">Demanda (proxy)</th>
                      <th scope="col" className="num">Concorrência</th>
                      <th scope="col" className="num">Relevância</th>
                      <th scope="col" className="num">Confiança</th>
                      <th scope="col" className="num">Volume de busca</th>
                      <th scope="col" className="num">Amostra</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.topic}>
                        <td>
                          <Link href={opportunityHref(item)} className="font-medium hover:text-cobalt hover:underline">{item.topic}</Link>
                          {item.status !== "ok" && <div className="mt-0.5"><Pill>Amostra insuficiente</Pill></div>}
                        </td>
                        <td className="num"><Value metric={item.score} format={integer} muted="Sem pontuação" /></td>
                        <td className="num"><Value metric={item.demand} format={integer} /></td>
                        <td className="num"><Value metric={item.competition} format={integer} /></td>
                        <td className="num"><Value metric={item.relevance} format={integer} /></td>
                        <td className="num"><Value metric={item.confidence} format={integer} /></td>
                        <td className="num"><Value metric={item.search_volume} format={integer} muted="Indisponível" /></td>
                        <td className="num">{item.sample_size} vídeos, {item.distinct_channels} canais</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <p className="mt-3 text-[0.8125rem] text-ink-3">{data.origin_note}</p>
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
