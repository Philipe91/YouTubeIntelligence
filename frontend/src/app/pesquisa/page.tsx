import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { BlockedNotice, Empty, PageHeader, Panel, Pill, SectionTitle, str } from "@/components/ui";
import { ChannelFilter, ChannelSelect, Notice, OriginPill, Pagination, RealChannelsNote, Tabs } from "@/components/intel";
import { dateTime, FORMAT_LABEL } from "@/lib/format";
import { intelGet, LANGUAGES, PERIODS, type GrowingTopics, type IntelContext, type Page, type Run } from "@/lib/intel";

import { runResearch } from "../intel-actions";

const TABS = [{ key: "nova", label: "Nova pesquisa" }, { key: "historico", label: "Histórico" }, { key: "salvas", label: "Salvas" }, { key: "crescimento", label: "Assuntos em crescimento" }];
const FIELD = "text-sm text-ink-2";

function SearchForm({ context, channel }: { context: IntelContext; channel?: string }) {
  return (
    <Panel className="p-4">
      <ActionForm action={runResearch} submit="Pesquisar" pending="Pesquisando..." className="grid gap-3 md:grid-cols-4">
        <label className={`${FIELD} md:col-span-3`}>Palavra, tema ou nicho
          <input name="query" required minLength={2} maxLength={120} placeholder="Ex.: história de Roma" className="field mt-1 w-full" />
        </label>
        <label className={FIELD}>O que procurar
          <select name="kind" className="field mt-1 w-full">
            <option value="videos">Vídeos por tema</option>
            <option value="recent">Vídeos recentes</option>
            <option value="channels">Canais por nicho</option>
            <option value="emerging">Canais pequenos em atividade</option>
          </select>
        </label>
        <label className={FIELD}>Associar ao canal<div className="mt-1"><ChannelSelect context={context} value={channel} /></div></label>
        <label className={FIELD}>Idioma
          <select name="language" className="field mt-1 w-full"><option value="">Qualquer</option>{LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
        </label>
        <label className={FIELD}>País (sigla)
          <input name="country" maxLength={2} placeholder="BR" className="field mt-1 w-full uppercase" />
        </label>
        <label className={FIELD}>Período
          <select name="days" className="field mt-1 w-full"><option value="">Qualquer data</option>{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select>
        </label>
        <label className={FIELD}>Formato
          <select name="format" className="field mt-1 w-full"><option value="">Todos</option><option value="short">Shorts</option><option value="long">Vídeos longos</option></select>
        </label>
        <label className={FIELD}>Ordem
          <select name="order" className="field mt-1 w-full"><option value="relevance">Relevância</option><option value="date">Mais recentes</option><option value="viewCount">Mais views</option></select>
        </label>
        <label className={FIELD}>Máximo de inscritos (canais pequenos)
          <input name="max_subscribers" type="number" min={1} placeholder="100000" className="field mt-1 w-full" />
        </label>
        <div className="md:col-span-4" />
      </ActionForm>
      <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-3">
        {context.mode === "demo"
          ? "Modo demonstração: procura só nos dados fictícios, sem acessar a internet e sem gastar cota."
          : "Cada pesquisa nova usa uma das 100 chamadas de busca diárias da API. Repetir o mesmo pedido em até 6 horas usa o cache."}
      </p>
    </Panel>
  );
}

function RunTable({ data, channels, href }: { data: Page<Run>; channels: Map<string, string>; href: (offset: number) => string }) {
  if (!data.items.length) return <Panel><Empty title="Nenhuma pesquisa aqui ainda.">Faça uma pesquisa na aba Nova pesquisa.</Empty></Panel>;
  return (
    <Panel>
      <div className="overflow-x-auto">
        <table className="data-table w-full">
          <thead><tr><th>Pesquisa</th><th>Tipo</th><th>Canal</th><th>Filtros</th><th className="num">Resultados</th><th>Quando</th><th>Dados</th></tr></thead>
          <tbody>
            {data.items.map((run) => (
              <tr key={run.id}>
                <td>
                  <Link className="font-medium text-cobalt underline underline-offset-2" href={`/pesquisa/${run.id}`}>{run.query}</Link>
                  {run.saved_name && <div className="text-[0.8125rem] text-ink-3">Salva como {run.saved_name}</div>}
                </td>
                <td className="whitespace-nowrap">{run.kind_label}</td>
                <td>{run.managed_channel_id ? channels.get(run.managed_channel_id) ?? "Canal removido" : "Sem canal"}</td>
                <td className="text-[0.8125rem] text-ink-3">{[run.filters.language, run.filters.country, run.filters.days && `${run.filters.days} dias`, run.filters.format && FORMAT_LABEL[run.filters.format]].filter(Boolean).join(", ") || "Nenhum"}</td>
                <td className="num">{run.result_count}</td>
                <td className="whitespace-nowrap">{dateTime(run.executed_at)}</td>
                <td><OriginPill fictional={run.fictional} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination total={data.total} limit={data.limit} offset={data.offset} href={href} />
    </Panel>
  );
}

function Growing({ data, q }: { data: GrowingTopics; q?: string }) {
  if (data.blocked) return <BlockedNotice reason={data.reason} />;
  return (
    <>
      <form action="/pesquisa" className="mb-3 flex flex-wrap gap-2">
        <input type="hidden" name="aba" value="crescimento" />
        <input name="q" defaultValue={q} placeholder="Filtrar por palavra" className="field" />
        <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Filtrar</button>
      </form>
      <Panel>
        {data.items.length ? (
          <div className="overflow-x-auto">
            <table className="data-table w-full">
              <thead><tr><th>Termo</th><th>Formato</th><th className="num">Vídeos ganhando velocidade</th><th className="num">Canais</th><th /></tr></thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={`${item.term}-${item.format}`}>
                    <td className="font-medium">{item.term}</td>
                    <td>{FORMAT_LABEL[item.format] ?? item.format}</td>
                    <td className="num">{item.accelerating} de {item.videos}</td>
                    <td className="num">{item.channels}</td>
                    <td><Link className="text-sm text-cobalt underline underline-offset-2" href={`/palavras?termo=${encodeURIComponent(item.term)}`}>Analisar termo</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty title="Nenhum assunto em crescimento com esse filtro." />}
      </Panel>
      <p className="mt-2 text-[0.8125rem] text-ink-3">Termos dos títulos cujos vídeos monitorados ganham velocidade. Não é volume de busca. {data.origin_note}</p>
    </>
  );
}

export default async function ResearchCenter({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const tab = TABS.some((t) => t.key === params.aba) ? String(params.aba) : "nova";
  const channel = str(params.canal);
  const offset = Number(str(params.inicio)) || 0;
  const context = await intelGet<IntelContext>("/context");
  const names = new Map(context.channels.map((c) => [c.id, c.name]));
  const link = (key: string) => `/pesquisa?aba=${key}${channel ? `&canal=${channel}` : ""}`;
  const runs = tab === "historico" || tab === "salvas"
    ? await intelGet<Page<Run>>("/research/runs", { channel_id: channel, saved: tab === "salvas" ? "true" : undefined, limit: "30", offset: String(offset) })
    : null;
  const growing = tab === "crescimento" ? await intelGet<GrowingTopics>("/research/growing", { q: str(params.q) }) : null;

  return (
    <>
      <PageHeader title="Central de pesquisa" intro="Procure vídeos e canais, guarde o que encontrou, compare e exporte. Tudo fica associado ao canal que você escolher.">
        <Pill tone={context.mode === "demo" ? "warn" : "good"}>{context.mode === "demo" ? "Modo demonstração" : "API do YouTube"}</Pill>
      </PageHeader>
      <Tabs items={TABS} current={tab} href={link} />
      {context.mode === "live" && !context.has_api_key && (
        <div className="mb-4"><Notice tone="warn" title="Sem chave da API do YouTube">Novas pesquisas não vão funcionar até você configurar YOUTUBE_API_KEY. O histórico continua disponível.</Notice></div>
      )}
      {tab === "nova" && <SearchForm context={context} channel={channel} />}
      {runs && (
        <>
          <div className="mb-3"><ChannelFilter context={context} value={channel} action="/pesquisa" keep={{ aba: tab }} /></div>
          <RunTable data={runs} channels={names} href={(next) => `${link(tab)}&inicio=${next}`} />
        </>
      )}
      {growing && <><SectionTitle>Assuntos em crescimento</SectionTitle><div className="mt-3"><Growing data={growing} q={str(params.q)} /></div></>}
      <div className="mt-3"><RealChannelsNote context={context} /></div>
    </>
  );
}

export const dynamic = "force-dynamic";
