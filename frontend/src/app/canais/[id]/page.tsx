import Link from "next/link";
import { notFound } from "next/navigation";

import { ActionForm } from "@/components/ActionForm";
import { AuthPill, ChannelFields, ClaudePanel, JobCard, OriginPill } from "@/components/studio";
import { Empty, PageHeader, Panel, Pill, SectionTitle, str } from "@/components/ui";
import { duration, integer, shortDate } from "@/lib/format";
import {
  CALENDAR_STATUS, LANGUAGE_LABEL, studioGet, studioGetOrNull,
  type CalendarEntry, type ChannelDetail, type Job, type Recommendation, type Source,
} from "@/lib/studio";

import {
  addCalendarEntry, addCompetitor, addHistory, deleteChannel, generateRecommendations, produceSimulated, removeItem,
  setRecommendationStatus, updateAutomation, updateCalendarEntry, updateChannel,
} from "../actions";

const TABS = [
  { key: "visao", label: "Visão geral" },
  { key: "recomendacoes", label: "Recomendações" },
  { key: "fila", label: "Fila" },
  { key: "calendario", label: "Calendário" },
  { key: "historico", label: "Histórico" },
  { key: "concorrentes", label: "Concorrentes" },
  { key: "configuracoes", label: "Configurações" },
];
const day = (iso: string) => shortDate(`${iso}T12:00:00Z`);

function Tabs({ channelId, current, counts }: { channelId: string; current: string; counts: Record<string, number> }) {
  return (
    <nav aria-label="Seções do canal" className="mb-5 flex gap-1 overflow-x-auto border-b border-line">
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          href={`/canais/${channelId}?aba=${tab.key}`}
          aria-current={current === tab.key ? "page" : undefined}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${current === tab.key ? "border-pine font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}
        >
          {tab.label}{counts[tab.key] ? <span className="ml-1.5 text-ink-3">{counts[tab.key]}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

function SourceLine({ source }: { source: Source }) {
  const note = source.fictional ? " (fictícia)" : source.verified === false ? " (não verificada)" : "";
  if (source.url?.startsWith("/")) return <li><Link href={source.url} className="text-cobalt underline underline-offset-2">{source.label}</Link>{note}</li>;
  if (source.url) return <li><a href={source.url} target="_blank" rel="noreferrer noopener" className="text-cobalt underline underline-offset-2">{source.label}</a>{note}</li>;
  return <li>{source.label}{note}</li>;
}

const BASIS: Record<string, { label: string; tone: "warn" | "neutral" | "info"; title: string }> = {
  demo_metrics: { label: "Dados fictícios", tone: "warn", title: "Calculado sobre a pesquisa fictícia de demonstração." },
  editorial: { label: "Editorial, sem métricas", tone: "neutral", title: "Baseado no perfil, no backlog e no histórico do canal. Não usa nenhum score." },
  approved_metrics: { label: "Métrica própria", tone: "info", title: "Calculada por este aplicativo com uso autorizado. Não é dado do YouTube." },
};
const PRIORITY: Record<string, { label: string; tone: "ochre" | "info" | "neutral" }> = {
  alta: { label: "Prioridade alta", tone: "ochre" }, media: { label: "Prioridade média", tone: "info" }, baixa: { label: "Prioridade baixa", tone: "neutral" },
};
const REC_STATUS: Record<string, string> = { nova: "Nova", aceita: "Aceita por você", descartada: "Descartada", em_producao: "Em produção", concluida: "Concluída" };

function RecommendationCard({ item, canProduce }: { item: Recommendation; canProduce: boolean }) {
  const basis = BASIS[item.data_basis];
  const priority = PRIORITY[item.editorial_priority];
  const hidden = { channel_id: item.channel_id, recommendation_id: item.id };
  return (
    <article className={`rounded-lg border border-line bg-surface p-4 ${item.status === "descartada" ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-display text-[1.0625rem] leading-snug font-semibold">{item.subject}</h3>
        <div className="flex flex-wrap gap-1.5">
          <Pill tone={basis.tone} title={basis.title}>{basis.label}</Pill>
          <Pill tone={priority.tone}>{priority.label}</Pill>
          <Pill>{REC_STATUS[item.status]}</Pill>
        </div>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">{item.justification}</p>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-2">
        <div><dt className="text-ink-3">Títulos sugeridos</dt><dd><ol className="list-decimal pl-4">{item.titles.map((title) => <li key={title}>{title}</li>)}</ol></dd></div>
        <div><dt className="text-ink-3">Hook inicial</dt><dd>{item.hook}</dd></div>
        <div><dt className="text-ink-3">Ideia de thumbnail</dt><dd>{item.thumbnail_idea}</dd></div>
        <div><dt className="text-ink-3">Formato e duração</dt><dd>{item.format === "short" ? "Short" : "Vídeo longo"}, {duration(item.duration_seconds)}</dd></div>
        <div><dt className="text-ink-3">Público-alvo</dt><dd>{item.target_audience}</dd></div>
        <div><dt className="text-ink-3">Fontes</dt><dd><ul className="list-disc pl-4">{item.sources.map((source) => <SourceLine key={source.label} source={source} />)}</ul></dd></div>
      </dl>
      <p className="mt-2 rounded-md bg-warn-soft px-2.5 py-1.5 text-[0.8125rem] text-warn">{item.facts_to_verify.join(" ")}</p>
      <div className="mt-3 flex flex-wrap items-start gap-2">
        <span className="self-center text-[0.8125rem] text-ink-3">{item.origin === "agente" ? "Escrita por agente." : "Rascunho por regras, para você editar."}</span>
        {item.status === "nova" && <ActionForm action={setRecommendationStatus} submit="Aceitar" tone="quiet" hidden={{ ...hidden, status: "aceita" }} />}
        {["nova", "aceita"].includes(item.status) && <ActionForm action={setRecommendationStatus} submit="Descartar" tone="quiet" hidden={{ ...hidden, status: "descartada" }} />}
        {item.status === "descartada" && <ActionForm action={setRecommendationStatus} submit="Reabrir" tone="quiet" hidden={{ ...hidden, status: "nova" }} />}
        {["nova", "aceita"].includes(item.status) && (canProduce
          ? <ActionForm action={produceSimulated} submit="Enviar para produção simulada" pending="Enviando..." hidden={{ ...hidden, form_key: `ui:${item.id}:${item.updated_at}` }} />
          : <span className="self-center text-[0.8125rem] text-ink-3">Produção desligada neste canal.</span>)}
      </div>
    </article>
  );
}

function monthBounds(value: string | undefined) {
  const today = new Date();
  const match = value?.match(/^(\d{4})-(\d{2})$/);
  const year = match ? Number(match[1]) : today.getFullYear();
  const month = match ? Number(match[2]) - 1 : today.getMonth();
  const pad = (n: number) => String(n).padStart(2, "0");
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const shift = (delta: number) => { const d = new Date(Date.UTC(year, month + delta, 1)); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`; };
  return {
    year, month, lastDay, start: `${year}-${pad(month + 1)}-01`, end: `${year}-${pad(month + 1)}-${pad(lastDay)}`,
    previous: shift(-1), next: shift(1), firstWeekday: new Date(Date.UTC(year, month, 1)).getUTCDay(),
    title: new Date(Date.UTC(year, month, 15)).toLocaleDateString("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" }),
    iso: (d: number) => `${year}-${pad(month + 1)}-${pad(d)}`,
  };
}

function Calendar({ channel, entries, bounds }: { channel: ChannelDetail; entries: CalendarEntry[]; bounds: ReturnType<typeof monthBounds> }) {
  const cells = [...Array(bounds.firstWeekday).fill(null), ...Array.from({ length: bounds.lastDay }, (_, i) => i + 1)];
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_20rem]">
      <div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-display text-[1.1875rem] font-semibold first-letter:uppercase">{bounds.title}</h2>
          <div className="flex gap-3 text-sm">
            <Link className="text-cobalt underline underline-offset-2" href={`/canais/${channel.id}?aba=calendario&m=${bounds.previous}`}>Mês anterior</Link>
            <Link className="text-cobalt underline underline-offset-2" href={`/canais/${channel.id}?aba=calendario&m=${bounds.next}`}>Próximo mês</Link>
          </div>
        </div>
        <Panel className="hidden overflow-hidden md:block">
          <div className="grid grid-cols-7 border-b border-line bg-page text-center text-[0.8125rem] text-ink-3">
            {["dom", "seg", "ter", "qua", "qui", "sex", "sáb"].map((name) => <div key={name} className="py-1.5">{name}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {cells.map((value, index) => (
              <div key={index} className={`min-h-24 border-b border-r border-line p-1.5 text-[0.8125rem] ${value === null ? "bg-page/50" : ""}`}>
                {value !== null && (
                  <>
                    <span className={bounds.iso(value) === today ? "inline-block rounded bg-pine px-1.5 font-medium text-white" : "text-ink-3"}>{value}</span>
                    {entries.filter((e) => e.scheduled_on === bounds.iso(value)).map((entry) => (
                      <div key={entry.id} title={`${entry.title}. ${CALENDAR_STATUS[entry.status]}.`} className={`mt-1 line-clamp-2 rounded px-1.5 py-0.5 ${entry.status === "cancelado" ? "bg-page text-ink-3 line-through" : entry.format === "short" ? "bg-cobalt-soft text-cobalt" : "bg-ochre-soft text-ochre"}`}>
                        {entry.title}
                      </div>
                    ))}
                  </>
                )}
              </div>
            ))}
          </div>
        </Panel>
        <div className="mt-2 hidden gap-4 text-[0.8125rem] text-ink-2 md:flex">
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ochre-soft ring-1 ring-ochre" /> Vídeo longo</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-cobalt-soft ring-1 ring-cobalt" /> Short</span>
        </div>
        <Panel className="mt-4">
          {entries.length === 0 ? <Empty title="Nada planejado neste mês." /> : (
            <ul className="divide-y divide-line">
              {entries.map((entry) => (
                <li key={entry.id} className="p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium">{entry.title}</span>
                    <span className="text-ink-2">{day(entry.scheduled_on)}, {entry.format === "short" ? "Short" : "longo"}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-end gap-2">
                    <ActionForm action={updateCalendarEntry} submit="Salvar" tone="quiet" className="flex flex-wrap items-end gap-2" hidden={{ channel_id: channel.id, entry_id: entry.id }}>
                      <label className="text-[0.8125rem] text-ink-2">Data<br /><input type="date" name="scheduled_on" defaultValue={entry.scheduled_on} className="field" /></label>
                      <label className="text-[0.8125rem] text-ink-2">Situação<br />
                        <select name="status" defaultValue={entry.status} className="field">{Object.entries(CALENDAR_STATUS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
                      </label>
                    </ActionForm>
                    <ActionForm action={removeItem} submit="Remover" tone="danger" pending="Removendo..." hidden={{ channel_id: channel.id, kind: "calendar", item_id: entry.id }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <Panel className="h-fit p-4">
        <SectionTitle>Planejar publicação</SectionTitle>
        <p className="mt-0.5 mb-3 text-[0.8125rem] text-ink-3">Planejamento interno. Nada é agendado no YouTube.</p>
        <ActionForm action={addCalendarEntry} submit="Adicionar ao calendário" resetOnSuccess hidden={{ channel_id: channel.id }}>
          <div className="mb-3 space-y-2">
            <label className="block text-[0.8125rem] text-ink-2">Título<input name="title" required className="field mt-1 w-full" /></label>
            <label className="block text-[0.8125rem] text-ink-2">Data<input type="date" name="scheduled_on" required defaultValue={today} className="field mt-1 w-full" /></label>
            <label className="block text-[0.8125rem] text-ink-2">Formato
              <select name="format" defaultValue={channel.formats[0]} className="field mt-1 w-full"><option value="long">Vídeo longo</option><option value="short">Short</option></select>
            </label>
            <label className="block text-[0.8125rem] text-ink-2">Notas<input name="notes" className="field mt-1 w-full" /></label>
          </div>
        </ActionForm>
      </Panel>
    </div>
  );
}

function AutomationPanel({ channel }: { channel: ChannelDetail }) {
  const automation = channel.automation;
  const select = (name: keyof typeof automation, label: string, help: string, options: [string, string][]) => (
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <span className="block text-[0.8125rem] text-ink-3">{help}</span>
      <select name={name} defaultValue={automation[name]} className="field mt-1 w-full">{options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select>
    </label>
  );
  const onOff: [string, string][] = [["on", "Ligada"], ["off", "Desligada"]];
  return (
    <Panel className="p-5">
      <SectionTitle>Automação deste canal</SectionTitle>
      <p className="mt-0.5 mb-3 text-sm text-ink-2">O que os agentes podem fazer aqui. O contrato recusa o que estiver desligado.</p>
      <ActionForm action={updateAutomation} submit="Salvar automação" doneMessage="Automação salva." hidden={{ channel_id: channel.id }}>
        <div className="mb-3 space-y-3">
          {select("auto_research", "Recomendações por agente", "Permite registrar novas recomendações.", onOff)}
          {select("auto_briefing", "Briefing por agente", "Permite solicitar o briefing do próximo vídeo.", onOff)}
          {select("auto_production", "Produção", "Tarefa real sempre exige sua autorização.", [["manual", "Sempre com minha autorização"], ["auto_simulated", "Simulações sem autorização"], ["off", "Desligada"]])}
          {select("auto_package", "Pacote de publicação", "Prepara título, descrição e arquivos para sua revisão.", onOff)}
          <div className="flex items-center justify-between gap-3 border-t border-line pt-3 text-sm">
            <span><span className="font-medium">Publicação</span><span className="block text-[0.8125rem] text-ink-3">Não existe nesta versão: você publica no YouTube Studio.</span></span>
            <Pill>Desativada</Pill>
          </div>
        </div>
      </ActionForm>
    </Panel>
  );
}

export default async function ChannelPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const query = await searchParams;
  const tab = TABS.some((item) => item.key === query.aba) ? String(query.aba) : "visao";
  const encoded = encodeURIComponent(id);
  const channel = await studioGetOrNull<ChannelDetail>(`/channels/${encoded}`);
  if (!channel) notFound();
  const bounds = monthBounds(str(query.m));
  const [recommendations, jobs, calendar] = await Promise.all([
    studioGet<{ items: Recommendation[] }>(`/channels/${encoded}/recommendations`),
    studioGet<{ jobs: Job[] }>("/jobs", { channel_id: id }),
    studioGet<{ entries: CalendarEntry[] }>("/calendar", { start: bounds.start, end: bounds.end, channel_id: id }),
  ]);
  const open = recommendations.items.filter((item) => ["nova", "aceita"].includes(item.status));
  const canProduce = channel.automation.auto_production !== "off";
  const activeJobs = jobs.jobs.filter((job) => !["cancelled", "package_ready"].includes(job.state));
  const generateNote = channel.is_demo && channel.mode === "demo"
    ? "Cruza a pesquisa fictícia com o perfil deste canal fictício."
    : !channel.is_demo && channel.mode === "live" && channel.policy.derived_allowed
      ? "Cruza suas pesquisas com o perfil. Pontuações são cálculos deste aplicativo."
      : "Usa perfil, ideias e histórico do canal. Nenhum score, porque as métricas não estão liberadas para canais reais.";

  return (
    <>
      <PageHeader title={channel.name} intro={channel.positioning || undefined}>
        <div className="flex flex-wrap items-center gap-2"><OriginPill isDemo={channel.is_demo} /><AuthPill auth={channel.youtube_auth} /></div>
      </PageHeader>
      <Tabs channelId={channel.id} current={tab} counts={{ recomendacoes: open.length, fila: activeJobs.length, historico: channel.history.length, concorrentes: channel.competitors.length }} />

      {tab === "visao" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div className="space-y-4">
            <Panel className="p-5">
              <SectionTitle>Contexto estratégico</SectionTitle>
              <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                <div><dt className="text-ink-3">Nicho</dt><dd>{channel.niche || "Não definido"}</dd></div>
                <div><dt className="text-ink-3">Idioma e país</dt><dd>{[LANGUAGE_LABEL[channel.language] ?? channel.language, channel.country].filter(Boolean).join(", ")}</dd></div>
                <div><dt className="text-ink-3">Público</dt><dd>{channel.audience || "Não definido"}</dd></div>
                <div><dt className="text-ink-3">Tom de voz</dt><dd>{channel.tone || "Não definido"}</dd></div>
                <div><dt className="text-ink-3">Formatos</dt><dd>{channel.formats.map((f) => (f === "short" ? `Shorts de ${duration(channel.short_target_seconds)}` : `Longos de ${duration(channel.long_target_seconds)}`)).join("; ")}</dd></div>
                <div><dt className="text-ink-3">Ritmo planejado</dt><dd>{channel.cadence_per_week ? `${channel.cadence_per_week} por semana` : "Não definido"}</dd></div>
                <div className="sm:col-span-2"><dt className="text-ink-3">Palavras do perfil</dt><dd>{channel.keywords.join(", ") || "Nenhuma"}</dd></div>
                <div className="sm:col-span-2"><dt className="text-ink-3">Temas a evitar</dt><dd>{channel.avoid.join(", ") || "Nenhum"}</dd></div>
              </dl>
            </Panel>
            <section>
              <h2 className="mb-2 font-display text-[1.1875rem] font-semibold">Próxima recomendação</h2>
              {open[0] ? <RecommendationCard item={open[0]} canProduce={canProduce} /> : (
                <Panel><Empty title="Nenhuma recomendação aberta."><Link href={`/canais/${channel.id}?aba=recomendacoes`} className="text-cobalt underline">Gerar recomendações</Link></Empty></Panel>
              )}
            </section>
          </div>
          <div className="space-y-4">
            <Panel className="p-4">
              <SectionTitle>YouTube</SectionTitle>
              <p className="mt-2 text-sm"><AuthPill auth={channel.youtube_auth} /></p>
              <p className="mt-1.5 text-sm text-ink-2">{channel.youtube_auth.detail}</p>
            </Panel>
            <Panel className="p-4"><ClaudePanel claude={channel.claude} /></Panel>
            <Panel className="p-4">
              <SectionTitle>Em andamento</SectionTitle>
              {activeJobs.length ? <ul className="mt-2 space-y-1 text-sm">{activeJobs.slice(0, 4).map((job) => <li key={job.id}><Link className="text-cobalt underline underline-offset-2" href={`/canais/${channel.id}/tarefas/${job.id}`}>{job.title}</Link></li>)}</ul> : <p className="mt-2 text-sm text-ink-3">Nenhuma tarefa ativa.</p>}
              {channel.next_scheduled && <p className="mt-2 text-sm text-ink-2">Próxima publicação planejada: {channel.next_scheduled.title}, {day(channel.next_scheduled.scheduled_on)}.</p>}
            </Panel>
          </div>
        </div>
      )}

      {tab === "recomendacoes" && (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-2xl text-sm text-ink-2">{generateNote}</p>
            <ActionForm action={generateRecommendations} submit="Gerar recomendações" pending="Gerando..." hidden={{ channel_id: channel.id }} />
          </div>
          {recommendations.items.length ? (
            <div className="space-y-3">{recommendations.items.map((item) => <RecommendationCard key={item.id} item={item} canProduce={canProduce} />)}</div>
          ) : <Panel><Empty title="Nenhuma recomendação ainda.">Preencha o perfil em Configurações e gere as primeiras.</Empty></Panel>}
        </>
      )}

      {tab === "fila" && (
        jobs.jobs.length
          ? <div className="space-y-3">{jobs.jobs.map((job) => <JobCard key={job.id} job={job} />)}</div>
          : <Panel><Empty title="Nenhuma tarefa neste canal.">Envie uma recomendação para produção simulada.</Empty></Panel>
      )}

      {tab === "calendario" && <Calendar channel={channel} entries={calendar.entries} bounds={bounds} />}

      {tab === "historico" && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_20rem]">
          <Panel>
            {channel.history.length === 0 ? <Empty title="Nenhum vídeo registrado.">Registre vídeos publicados para o sistema evitar temas já cobertos.</Empty> : (
              <div className="overflow-x-auto">
                <table className="data-table w-full min-w-[38rem]">
                  <thead><tr><th scope="col">Vídeo</th><th scope="col">Publicação</th><th scope="col" className="num">Views</th><th scope="col">Resultado</th><th scope="col"><span className="sr-only">Ações</span></th></tr></thead>
                  <tbody>
                    {channel.history.map((video) => (
                      <tr key={video.id}>
                        <td>
                          {video.url ? <a href={video.url} target="_blank" rel="noreferrer noopener" className="font-medium text-cobalt underline underline-offset-2">{video.title}</a> : <span className="font-medium">{video.title}</span>}
                          <div className="text-[0.8125rem] text-ink-3">{video.format === "short" ? "Short" : "Vídeo longo"}</div>
                        </td>
                        <td>{day(video.published_on)}</td>
                        <td className="num">
                          {video.views === null ? <span className="text-ink-3">Não informado</span> : integer(video.views)}
                          <div className="text-[0.8125rem] text-ink-3">{video.source === "demo" ? "Fictício" : "Informado por você"}</div>
                        </td>
                        <td className="text-ink-2">{video.result_notes || <span className="text-ink-3">Sem notas</span>}</td>
                        <td><ActionForm action={removeItem} submit="Remover" tone="danger" pending="Removendo..." hidden={{ channel_id: channel.id, kind: "history", item_id: video.id }} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <Panel className="h-fit p-4">
            <SectionTitle>Registrar vídeo</SectionTitle>
            <p className="mt-0.5 mb-3 text-[0.8125rem] text-ink-3">Os números são os que você informar, e ficam rotulados assim.</p>
            <ActionForm action={addHistory} submit="Registrar vídeo" resetOnSuccess hidden={{ channel_id: channel.id }}>
              <div className="mb-3 space-y-2">
                <label className="block text-[0.8125rem] text-ink-2">Título<input name="title" required className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Publicação<input type="date" name="published_on" required className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Formato
                  <select name="format" defaultValue={channel.formats[0]} className="field mt-1 w-full"><option value="long">Vídeo longo</option><option value="short">Short</option></select>
                </label>
                <label className="block text-[0.8125rem] text-ink-2">Link<input type="url" name="url" className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Views (opcional)<input inputMode="numeric" name="views" className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Observações<input name="result_notes" className="field mt-1 w-full" /></label>
              </div>
            </ActionForm>
          </Panel>
        </div>
      )}

      {tab === "concorrentes" && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_20rem]">
          <Panel>
            {channel.competitors.length === 0 ? <Empty title="Nenhum concorrente associado." /> : (
              <ul className="divide-y divide-line">
                {channel.competitors.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
                    <div><p className="font-medium">{item.name}</p><p className="text-[0.8125rem] text-ink-3">{[item.youtube_ref, item.notes].filter(Boolean).join(". ") || "Sem observações"}</p></div>
                    <ActionForm action={removeItem} submit="Remover" tone="danger" pending="Removendo..." hidden={{ channel_id: channel.id, kind: "competitor", item_id: item.id }} />
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel className="h-fit p-4">
            <SectionTitle>Associar concorrente</SectionTitle>
            <p className="mt-0.5 mb-3 text-[0.8125rem] text-ink-3">Só guarda a referência. Para coletar dados, use add-channel no modo real.</p>
            <ActionForm action={addCompetitor} submit="Associar concorrente" resetOnSuccess hidden={{ channel_id: channel.id }}>
              <div className="mb-3 space-y-2">
                <label className="block text-[0.8125rem] text-ink-2">Nome<input name="name" required className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Handle ou ID<input name="youtube_ref" className="field mt-1 w-full" placeholder="@canal" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Observações<input name="notes" className="field mt-1 w-full" /></label>
              </div>
            </ActionForm>
          </Panel>
        </div>
      )}

      {tab === "configuracoes" && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
          <Panel className="p-5">
            <SectionTitle>Perfil do canal</SectionTitle>
            <ActionForm action={updateChannel} submit="Salvar perfil" doneMessage="Perfil salvo." className="mt-3" hidden={{ channel_id: channel.id }}>
              <ChannelFields channel={channel} />
              <div className="h-4" />
            </ActionForm>
          </Panel>
          <div className="space-y-4">
            <AutomationPanel channel={channel} />
            <Panel className="border-bad/30 p-5">
              <SectionTitle>Remover canal</SectionTitle>
              <p className="mt-1 mb-3 text-sm text-ink-2">Apaga perfil, recomendações, calendário, histórico e tarefas deste canal aqui. Nada muda no YouTube.</p>
              <ActionForm action={deleteChannel} submit="Remover canal" tone="danger" pending="Removendo..." hidden={{ channel_id: channel.id }}>
                <label className="mb-3 block text-[0.8125rem] text-ink-2">Digite o nome do canal para confirmar<input name="confirm_name" autoComplete="off" className="field mt-1 w-full" /></label>
              </ActionForm>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
