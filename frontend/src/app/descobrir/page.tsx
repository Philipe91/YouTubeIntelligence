import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { ChannelSelect, Notice, OriginPill, Pagination, RealChannelsNote, Tabs } from "@/components/intel";
import { Empty, PageHeader, Panel, Pill, SectionTitle, SourceLink, str } from "@/components/ui";
import { dateTime, shortDate } from "@/lib/format";
import { intelGet, LANGUAGES, PERIODS, type DiscoveryCatalog, type EditorialOpportunity, type IntelContext, type Page, type Run } from "@/lib/intel";

import { discardOpportunity, opportunityToIdea, runDiscovery } from "../intel-actions";

const TABS = [{ key: "nova", label: "Nova descoberta" }, { key: "historico", label: "Histórico" }, { key: "salvos", label: "Salvos" }];
const FIELD = "text-sm text-ink-2";
const ITEM_LABEL: Record<string, string> = { video: "Vídeo", titulo: "Título de referência", canal: "Canal", tema: "Tema" };

function DiscoveryForm({ context, catalog, channel }: { context: IntelContext; catalog: DiscoveryCatalog; channel?: string }) {
  return (
    <Panel className="p-4">
      <ActionForm action={runDiscovery} submit="Descobrir" pending="Pesquisando..." className="grid gap-3 md:grid-cols-3">
        <label className={FIELD}>Nicho e subnicho
          <select name="topic" className="field mt-1 w-full">
            <option value="">Só o que eu digitar</option>
            {catalog.niches.map((niche) => (
              <optgroup key={niche.key} label={niche.label}>
                {niche.subniches.map((sub) => <option key={sub.key} value={`${niche.key}/${sub.key}`}>{sub.label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <label className={`${FIELD} md:col-span-2`}>Assunto, para afinar o recorte
          <input name="text" maxLength={80} placeholder="Ex.: queda de Roma" className="field mt-1 w-full" />
        </label>
        <label className={FIELD}>O que procurar
          <select name="target" className="field mt-1 w-full">{catalog.targets.map((target) => <option key={target.key} value={target.key}>{target.label}</option>)}</select>
        </label>
        <label className={FIELD}>Idioma
          <select name="language" defaultValue="pt" className="field mt-1 w-full"><option value="">Qualquer</option>{LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
        </label>
        <label className={FIELD}>País (sigla)
          <input name="country" maxLength={2} placeholder="BR" className="field mt-1 w-full uppercase" />
        </label>
        <label className={FIELD}>Período
          <select name="days" defaultValue="30" className="field mt-1 w-full"><option value="">Qualquer data</option>{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select>
        </label>
        <label className={FIELD}>Formato do vídeo
          <select name="format" className="field mt-1 w-full"><option value="">Todos</option><option value="short">Shorts</option><option value="long">Vídeos longos</option><option value="indeterminate">Indeterminado</option></select>
        </label>
        <label className={FIELD}>Máximo de inscritos (canais pequenos)
          <input name="max_subscribers" type="number" min={1} placeholder="100000" className="field mt-1 w-full" />
        </label>
        <label className={`${FIELD} md:col-span-3`}>Para qual canal
          <div className="mt-1"><ChannelSelect context={context} value={channel} emptyLabel="Sem canal: só pesquisar" /></div>
        </label>
        <div className="md:col-span-3" />
      </ActionForm>
      <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-3">
        {context.mode === "demo"
          ? "Modo demonstração: procura só nos dados fictícios, sem internet e sem gastar cota. A busca é mais solta do que a real, porque há poucos vídeos fictícios."
          : `Cada descoberta nova usa 1 das 100 buscas diárias do YouTube e algumas unidades gerais. Repetir o mesmo pedido em até 6 horas usa o cache.${context.derived_allowed ? "" : " VPH, outliers e rankings seguem bloqueados."}`}
      </p>
      <p className="mt-1 text-[0.8125rem] text-ink-3">{catalog.note}</p>
    </Panel>
  );
}

function History({ data, href }: { data: Page<Run>; href: (offset: number) => string }) {
  const items = data.items.filter((run) => run.filters.discovery);
  if (!items.length) return <Panel><Empty title="Nenhuma descoberta ainda.">Comece pela aba Nova descoberta.</Empty></Panel>;
  return (
    <Panel>
      <ul className="divide-y divide-line">
        {items.map((run) => (
          <li key={run.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <span className="min-w-0">
              <Link className="font-medium text-cobalt underline underline-offset-2" href={`/descobrir/${run.id}`}>{run.query}</Link>
              <span className="ml-2 text-ink-3">{[run.filters.niche, run.filters.subniche, run.kind_label].filter(Boolean).join(", ")}. {run.result_count} resultados.</span>
            </span>
            <span className="flex items-center gap-2 text-ink-3">{dateTime(run.executed_at)}<OriginPill fictional={run.fictional} simulated={run.simulated} /></span>
          </li>
        ))}
      </ul>
      <Pagination total={data.total} limit={data.limit} offset={data.offset} href={href} />
    </Panel>
  );
}

function Saved({ items, channel }: { items: EditorialOpportunity[]; channel: string }) {
  if (!items.length) return <Panel><Empty title="Nada salvo neste canal.">Salve vídeos, títulos, canais e temas nos resultados de uma descoberta.</Empty></Panel>;
  return (
    <Panel>
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <li key={item.id} className="p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Pill>{ITEM_LABEL[item.item_type] ?? item.item_type}</Pill>
              {item.status !== "aberta" && <Pill tone="neutral">{item.status === "virou_ideia" ? "Virou ideia" : "Descartado"}</Pill>}
              <span className={`font-medium ${item.removed ? "text-ink-3" : ""}`}>{item.title}</span>
              {item.source_url && !item.removed && <SourceLink url={item.source_url} />}
            </div>
            <p className="mt-1 text-[0.8125rem] text-ink-3">{[item.niche, item.subniche, `salvo em ${shortDate(item.created_at)}`].filter(Boolean).join(", ")}.{item.note && ` Sua nota: ${item.note}`}</p>
            {item.status === "aberta" && (
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <ActionForm action={opportunityToIdea} submit="Virar ideia" tone="quiet" hidden={{ channel_id: channel, opportunity_id: item.id }} className="flex flex-wrap items-end gap-2">
                  {item.item_type !== "tema" && <label className="text-[0.8125rem] text-ink-2">Assunto, com as suas palavras<input name="subject" required minLength={3} maxLength={200} className="field mt-1 block w-64 max-w-full" /></label>}
                  <label className="text-[0.8125rem] text-ink-2">Formato<select name="format" className="field mt-1 block"><option value="long">Longo</option><option value="short">Short</option></select></label>
                </ActionForm>
                <ActionForm action={discardOpportunity} submit="Descartar" tone="quiet" hidden={{ channel_id: channel, opportunity_id: item.id }} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default async function Discover({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const tab = TABS.some((t) => t.key === params.aba) ? String(params.aba) : "nova";
  const offset = Number(str(params.inicio)) || 0;
  const [context, catalog] = await Promise.all([intelGet<IntelContext>("/context"), intelGet<DiscoveryCatalog>("/discovery/catalog")]);
  const channel = context.channels.some((c) => c.id === str(params.canal)) ? str(params.canal) : context.channels[0]?.id;
  const runs = tab === "historico" ? await intelGet<Page<Run>>("/research/runs", { limit: "30", offset: String(offset) }) : null;
  const saved = tab === "salvos" && channel ? (await intelGet<{ items: EditorialOpportunity[] }>(`/channels/${channel}/opportunities`)).items : null;
  return (
    <>
      <PageHeader title="Descobrir oportunidades" intro="Pesquise por nicho, país, idioma, recência e formato. Os resultados separam o que foi observado, o que é estimado e o que é hipótese.">
        <Pill tone={context.mode === "demo" || context.api_target === "simulada" ? "warn" : "good"}>{context.mode === "demo" ? "Modo demonstração" : context.api_target === "simulada" ? "API simulada de teste" : "API do YouTube"}</Pill>
      </PageHeader>
      <Tabs items={TABS} current={tab} href={(key) => `/descobrir?aba=${key}${channel ? `&canal=${channel}` : ""}`} />
      {context.mode === "live" && !context.has_api_key && <div className="mb-4"><Notice tone="warn" title="Sem chave da API do YouTube">Novas pesquisas não vão funcionar até você configurar a chave. <Link className="underline" href="/sistema">Ver os passos</Link></Notice></div>}
      {tab === "nova" && <DiscoveryForm context={context} catalog={catalog} channel={channel} />}
      {runs && <History data={runs} href={(next) => `/descobrir?aba=historico&inicio=${next}`} />}
      {tab === "salvos" && (
        <>
          <form action="/descobrir" className="mb-3 flex flex-wrap items-center gap-2">
            <input type="hidden" name="aba" value="salvos" />
            <label htmlFor="canal-salvos" className="text-sm text-ink-2">Canal</label>
            <select id="canal-salvos" name="canal" defaultValue={channel} className="field max-w-72">{context.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
            <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
          </form>
          <SectionTitle><span className="sr-only">Itens salvos</span></SectionTitle>
          {saved && channel ? <Saved items={saved} channel={channel} /> : <Panel><Empty title="Nenhum canal pode receber estes dados.">No modo atual, só canais compatíveis aparecem aqui.</Empty></Panel>}
        </>
      )}
      <div className="mt-3"><RealChannelsNote context={context} /></div>
    </>
  );
}

export const dynamic = "force-dynamic";
