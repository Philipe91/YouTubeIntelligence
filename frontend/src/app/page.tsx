import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { OpportunityCard } from "@/components/OpportunityCard";
import { BlockedNotice, Empty, FormatTabs, PageHeader, Panel, Pill, SectionTitle, formatParam, str } from "@/components/ui";
import { Notice, OriginPill, VideoResults } from "@/components/intel";
import type { OpportunityRow, TrendTerm, VideoRow } from "@/lib/api";
import { dateTime, FORMAT_LABEL, integer, shortDate } from "@/lib/format";
import { intelGet, type Idea, type Run } from "@/lib/intel";

import { generateIdeas } from "./intel-actions";

interface Feed {
  mode: string; fictional: boolean; format: string; generated_at: string;
  selected_channel: { id: string; name: string; is_demo: boolean } | null;
  channels: { id: string; name: string; is_demo: boolean; niche: string; language: string; compatible: boolean; new_ideas: number; saved_ideas: number; competitors: number; awaiting: number; next_scheduled: { scheduled_on: string; title: string } | null }[];
  pending: { kind: string; label: string; title: string; channel: string; href: string }[];
  recent_searches: Run[];
  recent_keywords: { id: number; term: string; managed_channel_id: string | null; looked_up_at: string }[];
  research: { opportunities: OpportunityRow[]; videos: VideoRow[]; trends: TrendTerm[]; unavailable_reason: string | null };
  open_opportunities: { id: string; title: string; note: string; channel_id: string; channel: string }[];
  title_suggestions: { title: string; subject: string; channel: string; review_score: number; characters: number; href: string }[];
  saved_ideas: (Idea & { channel: string })[];
  collection: { jobs: { name: string; label: string; last_run_at: string | null; last_status: string | null; last_error: string | null; note: string | null }[]; counts: Record<string, number>; quota: { bucket: string; label: string; used: number; limit: number }[] };
  availability: { label: string; state: string; detail: string }[];
  compliance: { state: string; derived_allowed: boolean; description: string; stats_retention: string; text_retention_days: number; blocked: string[]; reason: string | null };
}

const PENDING_TONE: Record<string, "bad" | "warn" | "good" | "info" | "neutral"> = { failed: "bad", awaiting_authorization: "warn", package_ready: "good", calendar: "info", ideas: "neutral" };
const AVAILABLE_TONE: Record<string, "good" | "warn" | "neutral" | "info"> = { "disponível": "good", "com Claude": "good", "falta chave": "warn", "falta autorização": "warn", "fictício": "warn", "indisponível": "neutral", "por regras": "info" };

function Heading({ title, href, action }: { title: string; href?: string; action?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <SectionTitle>{title}</SectionTitle>
      {href && <Link className="shrink-0 text-sm text-cobalt underline underline-offset-2" href={href}>{action ?? "Ver tudo"}</Link>}
    </div>
  );
}

export default async function Today({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const format = formatParam(params.f);
  const canal = str(params.canal);
  let data: Feed;
  try {
    data = await intelGet<Feed>("/feed", { channel_id: canal, format });
  } catch (error) {
    if ((error as { status?: number }).status !== 404) throw error;
    data = await intelGet<Feed>("/feed", { format });
  }
  const selected = data.selected_channel;
  const query = selected ? `&canal=${selected.id}` : "";
  const scopedChannels = selected ? data.channels.filter((c) => c.id === selected.id) : data.channels;
  const { research } = data;

  return (
    <>
      <PageHeader title={selected ? `Hoje em ${selected.name}` : "Hoje nos seus canais"} intro={data.pending.length ? `${data.pending.length} ${data.pending.length === 1 ? "item espera" : "itens esperam"} uma decisão sua.` : "Nada espera uma decisão sua agora. Veja abaixo o que investigar."}>
        <div className="flex flex-wrap items-center gap-2">
          {data.fictional && <OriginPill fictional />}
          <FormatTabs current={format} basePath="/" params={{ canal: selected?.id }} />
        </div>
      </PageHeader>

      <form action="/" className="mb-5 flex flex-wrap items-center gap-2">
        <input type="hidden" name="f" value={format} />
        <label htmlFor="canal-feed" className="text-sm text-ink-2">Ver o feed de</label>
        <select id="canal-feed" name="canal" defaultValue={selected?.id ?? ""} className="field max-w-72">
          <option value="">Todos os canais</option>
          {data.channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
        </select>
        <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
      </form>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <section>
            <Heading title="Pendências editoriais" />
            <Panel>
              {data.pending.length ? (
                <ul className="divide-y divide-line">
                  {data.pending.map((item) => (
                    <li key={`${item.kind}-${item.href}-${item.title}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
                      <Link className="min-w-0 font-medium hover:text-cobalt hover:underline" href={item.href}>{item.title}{item.kind !== "ideas" && <span className="font-normal text-ink-3"> em {item.channel}</span>}</Link>
                      <Pill tone={PENDING_TONE[item.kind]}>{item.label}</Pill>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="Nenhuma pendência.">Gere ideias de um canal para começar.</Empty>}
            </Panel>
          </section>

          {research.unavailable_reason ? <Notice title="Sem dados de pesquisa neste canal">{research.unavailable_reason}</Notice> : (
            <>
              <section>
                <Heading title="Novas oportunidades" href={`/oportunidades?f=${format}`} action="Ver o ranking" />
                {data.compliance.derived_allowed ? (
                  research.opportunities.length ? (
                    <><div className="grid gap-3 md:grid-cols-2">{research.opportunities.map((item, index) => <OpportunityCard key={item.topic} item={item} rank={item.score.value === null ? undefined : index + 1} />)}</div>
                      <p className="mt-2 text-[0.8125rem] text-ink-3">Ranking experimental: mostra onde pesquisar, não o resultado de um vídeo.</p></>
                  ) : <Panel><Empty title="Nenhuma busca registrada."><Link className="text-cobalt underline" href="/pesquisa">Faça uma pesquisa</Link> para gerar temas.</Empty></Panel>
                ) : <BlockedNotice reason={data.compliance.reason ?? undefined} />}
              </section>

              <section>
                <Heading title={data.compliance.derived_allowed ? "Vídeos para investigar" : "Vídeos coletados mais recentes"} href={`/explorer?f=${format}${query}`} action="Abrir o Explorer" />
                <Panel><VideoResults videos={research.videos} empty={`Nenhum vídeo em ${FORMAT_LABEL[format]} para mostrar.`} /></Panel>
              </section>

              <section>
                <Heading title="Alertas de tendências" href="/pesquisa?aba=crescimento" />
                <Panel className="p-3">
                  {data.compliance.derived_allowed ? (
                    research.trends.length ? (
                      <ul className="flex flex-wrap gap-2">
                        {research.trends.map((term) => (
                          <li key={`${term.term}-${term.format}`}><Link className="block rounded-md border border-line px-2.5 py-1 text-sm hover:bg-page" href={`/palavras?termo=${encodeURIComponent(term.term)}${query}`}>{term.term} <span className="text-ink-3">{term.accelerating} de {term.videos} vídeos, {term.channels} canais</span></Link></li>
                        ))}
                      </ul>
                    ) : <p className="text-sm text-ink-3">Nenhum termo com vídeos suficientes em mais de um canal.</p>
                  ) : <p className="text-sm text-ink-2"><Pill tone="bad">Bloqueado</Pill> Depende de aprovação do Google.</p>}
                  <p className="mt-2 text-[0.8125rem] text-ink-3">Mede vídeos monitorados, não buscas.</p>
                </Panel>
              </section>
            </>
          )}

          <section>
            <Heading title="Recomendações de títulos" href={`/lab${selected ? `?canal=${selected.id}` : ""}`} action="Abrir o laboratório" />
            <Panel>
              {data.title_suggestions.length ? (
                <ul className="divide-y divide-line">
                  {data.title_suggestions.map((item) => (
                    <li key={`${item.channel}-${item.title}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
                      <Link className="min-w-0 hover:text-cobalt hover:underline" href={item.href}>{item.title}</Link>
                      <span className="text-[0.8125rem] text-ink-3">{item.channel}, revisão {item.review_score} de 100</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="Ainda sem títulos.">Gere ideias para receber sugestões.</Empty>}
            </Panel>
            <p className="mt-1.5 text-[0.8125rem] text-ink-3">A nota de revisão não prevê CTR.</p>
          </section>
        </div>

        <aside className="min-w-0 space-y-6">
          <section>
            <Heading title="Seus canais" href="/canais" />
            <Panel>
              {scopedChannels.length ? (
                <ul className="divide-y divide-line">
                  {scopedChannels.map((channel) => (
                    <li key={channel.id} className="p-3 text-sm">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <Link className="font-medium hover:text-cobalt hover:underline" href={`/canais/${channel.id}`}>{channel.name}</Link>
                        <Link className="text-[0.8125rem] text-cobalt underline underline-offset-2" href={`/?canal=${channel.id}&f=${format}`}>Ver feed</Link>
                      </div>
                      <p className="mt-0.5 text-[0.8125rem] text-ink-3">
                        {channel.new_ideas} ideias novas, {channel.saved_ideas} salvas, {channel.competitors} concorrentes.
                        {channel.next_scheduled && ` Próximo: ${shortDate(`${channel.next_scheduled.scheduled_on}T12:00:00Z`)}.`}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        <ActionForm action={generateIdeas} submit="Gerar ideias" pending="Gerando..." tone="quiet" hidden={{ channel_id: channel.id }} />
                        <Link className="text-[0.8125rem] text-cobalt underline underline-offset-2" href={`/coach?canal=${channel.id}`}>Perguntar ao Coach</Link>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <Empty title="Nenhum canal cadastrado."><Link className="text-cobalt underline" href="/canais/novo">Cadastre um canal</Link>.</Empty>}
            </Panel>
          </section>

          <section>
            <Heading title="Ideias salvas" href={`/ideias?filtro=salvas${query}`} />
            <Panel>
              {data.saved_ideas.length ? (
                <ul className="divide-y divide-line">
                  {data.saved_ideas.map((idea) => <li key={idea.id} className="px-3 py-2 text-sm"><Link className="hover:underline" href={`/ideias?canal=${idea.channel_id}&filtro=salvas`}>{idea.subject}</Link><span className="block text-[0.8125rem] text-ink-3">{idea.channel}</span></li>)}
                </ul>
              ) : <p className="p-3 text-sm text-ink-3">Nenhuma ideia salva.</p>}
            </Panel>
          </section>

          {data.open_opportunities.length > 0 && (
            <section>
              <Heading title="Oportunidades registradas" />
              <Panel>
                <ul className="divide-y divide-line">
                  {data.open_opportunities.map((item) => <li key={item.id} className="px-3 py-2 text-sm"><Link className="hover:underline" href={`/canais/${item.channel_id}/concorrentes`}>{item.title}</Link><span className="block text-[0.8125rem] text-ink-3">{item.channel}</span></li>)}
                </ul>
              </Panel>
            </section>
          )}

          <section>
            <Heading title="Pesquisas recentes" href={`/pesquisa?aba=historico${query}`} />
            <Panel>
              {data.recent_searches.length || data.recent_keywords.length ? (
                <ul className="divide-y divide-line">
                  {data.recent_searches.map((run) => <li key={run.id} className="px-3 py-2 text-sm"><Link className="hover:underline" href={`/pesquisa/${run.id}`}>{run.query}</Link><span className="block text-[0.8125rem] text-ink-3">{run.kind_label}, {dateTime(run.executed_at)}</span></li>)}
                  {data.recent_keywords.map((item) => <li key={item.id} className="px-3 py-2 text-sm"><Link className="hover:underline" href={`/palavras?termo=${encodeURIComponent(item.term)}${item.managed_channel_id ? `&canal=${item.managed_channel_id}` : ""}`}>{item.term}</Link><span className="block text-[0.8125rem] text-ink-3">Palavra-chave, {dateTime(item.looked_up_at)}</span></li>)}
                </ul>
              ) : <p className="p-3 text-sm text-ink-3">Nenhuma pesquisa ainda. <Link className="text-cobalt underline" href="/pesquisa">Fazer a primeira</Link>.</p>}
            </Panel>
          </section>

          <section>
            <Heading title="Disponibilidade de dados" href="/sistema" action="Sistema e cotas" />
            <Panel>
              <ul className="divide-y divide-line">
                {data.availability.map((item) => (
                  <li key={item.label} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-2"><span className="font-medium">{item.label}</span><Pill tone={AVAILABLE_TONE[item.state] ?? "neutral"}>{item.state}</Pill></div>
                    <p className="mt-0.5 text-[0.8125rem] text-ink-3">{item.detail}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          </section>

          <section>
            <Heading title="Status da coleta" href="/sistema" action="Detalhes" />
            <Panel className="p-3 text-sm">
              <p className="text-ink-2">Na base: {integer(data.collection.counts.videos)} em vídeos, {integer(data.collection.counts.channels)} em canais e {integer(data.collection.counts.snapshots)} em medições.</p>
              <ul className="mt-2 space-y-1 text-[0.8125rem]">
                {data.collection.jobs.map((job) => (
                  <li key={job.name} className="flex flex-wrap justify-between gap-2"><span>{job.label}</span><span className="text-ink-3">{job.note ?? (job.last_run_at ? `${job.last_status}, ${dateTime(job.last_run_at)}` : "Ainda não rodou")}</span></li>
                ))}
              </ul>
              <ul className="mt-2 space-y-1 border-t border-line pt-2 text-[0.8125rem]">
                {data.collection.quota.filter((item) => item.limit > 0).map((item) => <li key={item.bucket} className="flex justify-between gap-2"><span>{item.label}</span><span className="text-ink-3">{integer(item.used)} de {integer(item.limit)} hoje</span></li>)}
              </ul>
            </Panel>
          </section>

          <section>
            <Heading title="Limitações de conformidade" href="/metodologia" action="Como calculamos" />
            <Panel className="p-3 text-sm">
              <p className="text-ink-2">{data.compliance.description}</p>
              {data.compliance.blocked.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[0.8125rem] text-ink-2">{data.compliance.blocked.map((item) => <li key={item}><Value metric={{ value: null, kind: "blocked", source: "Política da API", reason: data.compliance.reason, as_of: null }} format={integer} /> {item}</li>)}</ul>}
              <p className="mt-2 text-[0.8125rem] text-ink-3">Estatísticas de terceiros: {data.compliance.stats_retention}. Textos da API: {data.compliance.text_retention_days} dias sem atualização. Nada é publicado por este aplicativo.</p>
            </Panel>
          </section>
        </aside>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
