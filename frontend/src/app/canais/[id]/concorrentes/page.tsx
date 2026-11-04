import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { BlockedNotice, Empty, PageHeader, Panel, Pill, SectionTitle, SourceLink } from "@/components/ui";
import { Notice, OriginPill } from "@/components/intel";
import { compact, decimal, duration, FORMAT_LABEL, percent, shortDate } from "@/lib/format";
import { intelGet, intelGetOrNull, type CompetitorOverview, type EditorialOpportunity } from "@/lib/intel";

import { addCompetitorRef, addOpportunity, discardOpportunity, linkCompetitor, opportunityToIdea } from "../../../intel-actions";

const STATUS: Record<string, string> = { aberta: "Aberta", virou_ideia: "Virou ideia", descartada: "Descartada" };

export default async function CompetitorsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await intelGetOrNull<CompetitorOverview>(`/channels/${id}/competitors`);
  if (!data) notFound();
  const { items: opportunities } = await intelGet<{ items: EditorialOpportunity[] }>(`/channels/${id}/opportunities`);
  const hidden = { channel_id: id };
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href={`/canais/${id}`}>Voltar a {data.channel.name}</Link></p>
      <PageHeader title="Concorrentes e referências" intro="Lista própria deste canal. Use como referência editorial, para encontrar assuntos e formatos que ainda não explorou.">
        <div className="flex flex-wrap items-center gap-2">
          {data.usable && <OriginPill fictional={data.fictional} />}
          <a href={`/canais/${id}/concorrentes/relatorio`} className="inline-flex min-h-9 items-center rounded-md border border-line bg-surface px-3.5 text-sm font-medium hover:bg-page">Baixar relatório com fontes</a>
        </div>
      </PageHeader>

      {!data.usable && <div className="mb-4"><Notice tone="warn" title="Sem dados neste modo">{data.mode === "demo" ? "No modo demonstração, canal real não recebe dados fictícios. Os nomes abaixo são os que você cadastrou." : "Canal fictício não recebe dados reais do YouTube."}</Notice></div>}

      <div className="grid gap-4 xl:grid-cols-[1fr_20rem]">
        <Panel>
          {data.items.length === 0 ? <Empty title="Nenhum concorrente neste canal.">Adicione o primeiro pelo link, @nome ou ID.</Empty> : (
            <ul className="divide-y divide-line">
              {data.items.map((item) => (
                <li key={item.id} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      {item.linked
                        ? <Link href={`/canais/${id}/concorrentes/${item.id}`} className="font-medium text-cobalt underline underline-offset-2">{item.channel?.title ?? item.name}</Link>
                        : <p className="font-medium">{item.name}</p>}
                      {item.notes && <p className="text-[0.8125rem] text-ink-2">{item.notes}</p>}
                    </div>
                    {item.channel ? <SourceLink url={item.channel.source_url} label="Canal no YouTube" /> : <Pill>Sem vínculo</Pill>}
                  </div>
                  {item.linked && item.channel && (
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem] text-ink-2">
                      <span><Value metric={item.channel.subscribers} format={compact} muted="Oculto" /> inscritos</span>
                      <span>{item.videos_collected} vídeos coletados</span>
                      <span>Último: {item.last_published_at ? shortDate(item.last_published_at) : "nenhum"}</span>
                      <span>{item.recent_days_uploads.length} publicados em 90 dias</span>
                    </p>
                  )}
                  {!item.linked && data.usable && (
                    <ActionForm action={linkCompetitor} submit="Vincular" tone="quiet" pending="Buscando..." hidden={{ ...hidden, competitor_id: item.id }} className="mt-2 flex flex-wrap items-end gap-2">
                      <label className="text-[0.8125rem] text-ink-2">Link, @nome ou ID<input name="reference" required className="field mt-1 block w-64 max-w-full" /></label>
                    </ActionForm>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel className="h-fit p-4">
          <SectionTitle>Adicionar concorrente</SectionTitle>
          {data.usable ? (
            <>
              <p className="mt-0.5 mb-3 text-[0.8125rem] text-ink-3">{data.mode === "demo" ? "Modo demonstração: só aceita os canais fictícios abaixo." : "Busca o canal e até 50 vídeos pela API oficial. Custa poucas unidades da cota padrão."}</p>
              <ActionForm action={addCompetitorRef} submit="Adicionar" pending="Buscando..." resetOnSuccess hidden={hidden} doneMessage="Adicionado.">
                <div className="mb-3 space-y-2">
                  {data.demo_options.length > 0 ? (
                    <label className="block text-[0.8125rem] text-ink-2">Canal fictício
                      <select name="reference" required className="field mt-1 w-full">{data.demo_options.map((o) => <option key={o.id} value={`@demo${Number(o.id.slice(-2))}`}>{o.title}</option>)}</select>
                    </label>
                  ) : <label className="block text-[0.8125rem] text-ink-2">Link, @nome ou ID<input name="reference" required placeholder="https://www.youtube.com/@canal" className="field mt-1 w-full" /></label>}
                  <label className="block text-[0.8125rem] text-ink-2">Seu nome para o canal (opcional)<input name="name" className="field mt-1 w-full" /></label>
                  <label className="block text-[0.8125rem] text-ink-2">Por que acompanhar<input name="notes" className="field mt-1 w-full" /></label>
                </div>
              </ActionForm>
              {data.mode === "live" && !data.has_api_key && <p className="mt-2 text-[0.8125rem] text-warn">Configure YOUTUBE_API_KEY para buscar canais.</p>}
            </>
          ) : <p className="mt-1 text-sm text-ink-3">Indisponível neste modo.</p>}
        </Panel>
      </div>

      <SectionTitle><span className="mt-6 block">Comparação editorial</span></SectionTitle>
      <div className="mt-3">
        {data.comparison_blocked ? <BlockedNotice reason={data.reason ?? undefined} /> : !data.comparison?.length ? (
          <Panel><Empty title="Nada para comparar ainda.">Adicione um concorrente com vínculo ao YouTube.</Empty></Panel>
        ) : (
          <Panel>
            <div className="overflow-x-auto">
              <table className="data-table w-full min-w-[46rem]">
                <thead><tr><th>Canal</th><th>Formato</th><th className="num">Vídeos</th><th className="num">Por semana</th><th className="num">Duração típica</th><th className="num">Títulos em pergunta</th><th>Dia mais comum</th></tr></thead>
                <tbody>
                  {data.comparison.flatMap((row) => Object.entries(row.formats).map(([format, values]) => (
                    <tr key={`${row.research_id}-${format}`}>
                      <td>{row.name}</td><td>{FORMAT_LABEL[format]}</td><td className="num">{values.sample_size}</td>
                      <td className="num">{values.uploads_per_week === null ? "Sem dado" : decimal(values.uploads_per_week)}</td>
                      <td className="num">{values.median_duration_seconds === null ? "Sem dado" : duration(values.median_duration_seconds)}</td>
                      <td className="num">{values.question_title_share === null ? "Sem dado" : percent(values.question_title_share * 100)}</td>
                      <td>{values.top_weekday ?? "Sem dado"}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
            <p className="border-t border-line p-3 text-[0.8125rem] text-ink-3">Mostra hábitos de publicação, sem declarar qual canal é melhor. Dia mais comum é hábito observado, não melhor horário. {data.origin_note}</p>
          </Panel>
        )}
      </div>

      <SectionTitle><span className="mt-6 block">Oportunidades editoriais</span></SectionTitle>
      <div className="mt-3 grid gap-4 xl:grid-cols-[1fr_20rem]">
        <Panel>
          {opportunities.length === 0 ? <Empty title="Nenhuma oportunidade registrada.">Anote aqui os ângulos que os concorrentes ainda não exploraram.</Empty> : (
            <ul className="divide-y divide-line">
              {opportunities.map((item) => (
                <li key={item.id} className={`p-3 ${item.status === "descartada" ? "opacity-60" : ""}`}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0"><p className="text-sm font-medium">{item.title}</p>{item.note && <p className="text-[0.8125rem] text-ink-2">{item.note}</p>}{item.video_title && <p className="text-[0.8125rem] text-ink-3">Referência: <Link className="underline" href={`/videos/${item.video_id}`}>{item.video_title}</Link></p>}</div>
                    <Pill tone={item.status === "aberta" ? "info" : "neutral"}>{STATUS[item.status]}</Pill>
                  </div>
                  {item.status === "aberta" && (
                    <div className="mt-2 flex flex-wrap items-end gap-2">
                      <ActionForm action={opportunityToIdea} submit="Virar ideia" tone="quiet" hidden={{ ...hidden, opportunity_id: item.id }} className="flex flex-wrap items-end gap-2">
                        <select name="format" aria-label="Formato da ideia" className="field"><option value="long">Vídeo longo</option><option value="short">Short</option></select>
                      </ActionForm>
                      <ActionForm action={discardOpportunity} submit="Descartar" tone="quiet" hidden={{ ...hidden, opportunity_id: item.id }} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel className="h-fit p-4">
          <SectionTitle>Registrar oportunidade</SectionTitle>
          <ActionForm action={addOpportunity} submit="Registrar" resetOnSuccess hidden={hidden} className="mt-3" doneMessage="Registrada.">
            <div className="mb-3 space-y-2">
              <label className="block text-[0.8125rem] text-ink-2">Oportunidade<input name="title" required minLength={3} maxLength={200} className="field mt-1 w-full" /></label>
              <label className="block text-[0.8125rem] text-ink-2">Por quê<input name="note" maxLength={1000} className="field mt-1 w-full" /></label>
            </div>
          </ActionForm>
        </Panel>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
