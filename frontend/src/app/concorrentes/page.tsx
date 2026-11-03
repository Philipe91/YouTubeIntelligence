import Link from "next/link";

import { Value } from "@/components/Mark";
import { BlockedNotice, Empty, FormatTabs, PageHeader, Panel, Pill, formatParam } from "@/components/ui";
import { api, type CompareRow } from "@/lib/api";
import { compact, decimal, duration, integer, percent } from "@/lib/format";

interface Response { blocked: boolean; reason?: string; rows: CompareRow[]; origin_note?: string }

export default async function Competitors({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = formatParam(params.f);
  const data = await api<Response>("/api/channels/compare", { format });
  return (
    <>
      <PageHeader title="Concorrentes" intro="Padrões editoriais lado a lado, no mesmo formato. Para cadastrar um canal, use o comando add-channel descrito no README.">
        <FormatTabs current={format} basePath="/concorrentes" />
      </PageHeader>
      {data.blocked ? <BlockedNotice reason={data.reason} /> : (
        <>
          <Panel>
            {data.rows.length === 0 ? <Empty title="Nenhum canal monitorado.">Cadastre o primeiro com o comando add-channel.</Empty> : (
              <div className="overflow-x-auto">
                <table className="data-table w-full min-w-[56rem]">
                  <thead>
                    <tr>
                      <th scope="col">Canal</th>
                      <th scope="col" className="num">Inscritos</th>
                      <th scope="col" className="num">Vídeos</th>
                      <th scope="col" className="num">Por semana</th>
                      <th scope="col" className="num">Duração típica</th>
                      <th scope="col" className="num">Views típicas</th>
                      <th scope="col" className="num">Acima do típico</th>
                      <th scope="col" className="num">Títulos em pergunta</th>
                      <th scope="col">Dia mais comum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.channel_id}>
                        <td>
                          <Link href={`/concorrentes/${row.channel_id}`} className="font-medium hover:text-cobalt hover:underline">{row.title}</Link>
                          {row.is_own && <span className="ml-2"><Pill tone="info">Seu canal</Pill></span>}
                        </td>
                        <td className="num"><Value metric={row.subscribers} format={compact} muted="Oculto" /></td>
                        <td className="num">{integer(row.sample_size)}</td>
                        <td className="num">{row.uploads_per_week === null ? "Sem dado" : decimal(row.uploads_per_week)}</td>
                        <td className="num">{row.median_duration_seconds === null ? "Sem dado" : duration(row.median_duration_seconds)}</td>
                        <td className="num">{row.median_views === null ? "Sem dado" : compact(row.median_views)}</td>
                        <td className="num">{row.scored ? `${row.outliers} de ${row.scored}` : "Amostra insuficiente"}</td>
                        <td className="num">{row.question_title_share === null ? "Sem dado" : percent(row.question_title_share * 100)}</td>
                        <td>{row.top_weekday ?? "Sem dado"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <p className="mt-3 text-[0.8125rem] text-ink-3">Valores típicos são medianas. Views típicas misturam idades diferentes, então compare com cuidado; o IDR de cada vídeo corrige a idade. {data.origin_note}</p>
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
