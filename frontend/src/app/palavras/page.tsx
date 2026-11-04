import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Value } from "@/components/Mark";
import { BlockedNotice, Empty, PageHeader, Panel, Pill, SectionTitle, SourceLink, str } from "@/components/ui";
import { ChannelSelect, Notice, OriginPill, Pagination, RealChannelsNote, Tabs, VideoResults } from "@/components/intel";
import { compact, dateTime, FORMAT_LABEL, integer } from "@/lib/format";
import { intelGet, type Favorite, type ForYou, type IntelContext, type KeywordAnalysis, type KeywordHistoryItem, type OwnTerms, type Page } from "@/lib/intel";

import { addFavorite, lookupKeyword, removeFavorite } from "../intel-actions";

const TERM_TABS = [
  { key: "visao", label: "Visão geral" }, { key: "relacionados", label: "Relacionados" }, { key: "variacoes", label: "Variações" },
  { key: "perguntas", label: "Perguntas" }, { key: "ascensao", label: "Em ascensão" }, { key: "videos", label: "Vídeos encontrados" },
];
const CHANNEL_TABS = [{ key: "para-voce", label: "Para este canal" }, { key: "descoberta", label: "Termos de descoberta" }, { key: "favoritos", label: "Favoritas" }, { key: "historico", label: "Histórico" }];
const ORIGIN_LABEL: Record<string, string> = { analytics: "YouTube Analytics", favorito: "Favorita", perfil: "Perfil do canal", backlog: "Backlog", tendencia: "Tendência" };

function TermLink({ term, channel }: { term: string; channel?: string }) {
  return <Link className="text-cobalt underline underline-offset-2" href={`/palavras?termo=${encodeURIComponent(term)}${channel ? `&canal=${channel}` : ""}`}>{term}</Link>;
}

function Overview({ data }: { data: KeywordAnalysis }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel className="p-4">
        <SectionTitle>Volume de busca</SectionTitle>
        <dl className="mt-3 space-y-3 text-sm">
          <div><dt className="font-medium">Medido</dt><dd className="mt-0.5 text-ink-2"><Value metric={data.volume.measured} format={integer} muted="Indisponível" /> {data.volume.measured.reason}</dd></div>
          <div><dt className="font-medium">Estimativa de provedor</dt><dd className="mt-0.5 text-ink-2"><Value metric={data.volume.provider_estimate} format={integer} muted="Indisponível" /> {data.volume.provider_estimate.reason}</dd></div>
        </dl>
      </Panel>
      <Panel className="p-4">
        <SectionTitle>Índice experimental</SectionTitle>
        <p className="mt-1 text-[0.8125rem] leading-relaxed text-ink-3">{data.index.note}</p>
        {data.index.blocked ? <p className="mt-3 text-sm text-ink-2"><Pill tone="bad">Bloqueado</Pill> {data.index.reason}</p> : (
          <div className="mt-3 overflow-x-auto">
            <table className="data-table w-full">
              <thead><tr><th>Formato</th><th className="num">Índice</th><th className="num">Atenção</th><th className="num">Concorrência</th><th className="num">Confiança</th><th className="num">Amostra</th></tr></thead>
              <tbody>
                {data.index.formats.map((row) => (
                  <tr key={row.format}>
                    <td>{FORMAT_LABEL[row.format]}</td>
                    <td className="num"><Value metric={row.index} format={integer} /></td>
                    <td className="num"><Value metric={row.attention} format={integer} /></td>
                    <td className="num"><Value metric={row.competition} format={integer} /></td>
                    <td className="num"><Value metric={row.confidence} format={integer} /></td>
                    <td className="num">{row.sample_size} vídeos</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function Related({ data, channel }: { data: KeywordAnalysis; channel?: string }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel className="p-4">
        <SectionTitle>Aparecem juntos nos títulos</SectionTitle>
        {data.related.from_titles_blocked ? <p className="mt-3 text-sm text-ink-2"><Pill tone="bad">Bloqueado</Pill> {data.related.from_titles_reason}</p>
          : data.related.from_titles.length ? (
            <ul className="mt-3 divide-y divide-line text-sm">{data.related.from_titles.map((item) => <li key={item.term} className="flex justify-between gap-3 py-1.5"><TermLink term={item.term} channel={channel} /><span className="text-ink-3">em {item.videos} vídeos</span></li>)}</ul>
          ) : <p className="mt-3 text-sm text-ink-3">Nenhuma palavra se repete em pelo menos 2 vídeos encontrados.</p>}
        {!data.related.from_titles_blocked && <p className="mt-3 text-[0.8125rem] text-ink-3">Contagem em títulos coletados. Não indica sinônimo nem procura.</p>}
      </Panel>
      <Panel className="p-4">
        <SectionTitle>Do perfil do canal</SectionTitle>
        {data.related.from_profile.length ? (
          <ul className="mt-3 flex flex-wrap gap-2 text-sm">{data.related.from_profile.map((item) => <li key={item.term} className="rounded-md border border-line px-2.5 py-1"><TermLink term={item.term} channel={channel} /></li>)}</ul>
        ) : <p className="mt-3 text-sm text-ink-3">{channel ? "O perfil do canal não tem outras palavras." : "Escolha um canal para ver as palavras do perfil."}</p>}
      </Panel>
    </div>
  );
}

function Rising({ data, channel }: { data: KeywordAnalysis; channel?: string }) {
  if (data.rising.blocked) return <BlockedNotice reason={data.rising.reason} />;
  return (
    <Panel className="p-4">
      {data.rising.items.length ? (
        <ul className="divide-y divide-line text-sm">{data.rising.items.map((item) => <li key={`${item.term}-${item.format}`} className="flex flex-wrap justify-between gap-3 py-2"><span><TermLink term={item.term} channel={channel} /> <span className="text-ink-3">{FORMAT_LABEL[item.format]}</span></span><span className="text-ink-3">{item.accelerating} de {item.videos} vídeos ganhando velocidade, {item.channels} canais</span></li>)}</ul>
      ) : <Empty title="Nada em ascensão ligado a este termo.">A lista completa fica na central de pesquisa.</Empty>}
      <p className="mt-3 text-[0.8125rem] text-ink-3">Mede vídeos monitorados, não buscas. {data.rising.origin_note}</p>
    </Panel>
  );
}

function ChannelSection({ tab, channel, forYou, ownTerms, favorites, history, channels, offset }: {
  tab: string; channel?: string; forYou: ForYou | null; ownTerms: OwnTerms | null; favorites: Favorite[]; history: Page<KeywordHistoryItem> | null; channels: Map<string, string>; offset: number;
}) {
  if (tab === "historico") {
    if (!history?.items.length) return <Panel><Empty title="Nenhuma pesquisa de palavra ainda." /></Panel>;
    return (
      <Panel>
        <div className="overflow-x-auto">
          <table className="data-table w-full">
            <thead><tr><th>Termo</th><th>Canal</th><th>Quando</th><th>Dados</th></tr></thead>
            <tbody>{history.items.map((item) => (
              <tr key={item.id}>
                <td><TermLink term={item.term} channel={item.managed_channel_id ?? undefined} /></td>
                <td>{item.managed_channel_id ? channels.get(item.managed_channel_id) ?? "Canal removido" : "Sem canal"}</td>
                <td>{dateTime(item.looked_up_at)}</td>
                <td><OriginPill fictional={item.data_origin === "demo"} /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <Pagination total={history.total} limit={history.limit} offset={offset} href={(next) => `/palavras?aba=historico${channel ? `&canal=${channel}` : ""}&inicio=${next}`} />
      </Panel>
    );
  }
  if (!channel) return <Panel><Empty title="Escolha um canal.">Esta seção é específica de cada canal.</Empty></Panel>;
  if (tab === "favoritos") {
    return (
      <Panel>
        <div className="flex items-center justify-between gap-3 border-b border-line p-3">
          <p className="text-sm text-ink-2">{favorites.length} {favorites.length === 1 ? "palavra" : "palavras"}</p>
          {favorites.length > 0 && <a className="text-sm text-cobalt underline underline-offset-2" href={`/palavras/favoritas/${channel}`}>Exportar CSV</a>}
        </div>
        {favorites.length ? (
          <ul className="divide-y divide-line">{favorites.map((item) => (
            <li key={item.term} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
              <span><TermLink term={item.term} channel={channel} />{item.note && <span className="ml-2 text-ink-3">{item.note}</span>}</span>
              <ActionForm action={removeFavorite} submit="Remover" tone="quiet" hidden={{ channel_id: channel, term: item.term }} />
            </li>
          ))}</ul>
        ) : <Empty title="Nenhuma favorita neste canal.">Pesquise um termo e clique em Favoritar.</Empty>}
      </Panel>
    );
  }
  if (tab === "descoberta") {
    if (!ownTerms?.available) return <Panel><Empty title="Termos de descoberta indisponíveis.">{ownTerms?.reason}</Empty></Panel>;
    return (
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line p-3 text-sm">
          <span className="text-ink-2">Buscas no YouTube que levaram pessoas aos vídeos do canal. Fonte: {ownTerms.source}.</span>
          <OriginPill fictional={Boolean(ownTerms.fictional)} />
        </div>
        <div className="overflow-x-auto">
          <table className="data-table w-full">
            <thead><tr><th>Termo</th><th className="num">Views</th><th className="num">Minutos assistidos</th></tr></thead>
            <tbody>{ownTerms.items.map((item) => <tr key={item.term}><td><TermLink term={item.term} channel={channel} /></td><td className="num"><Value metric={item.views} format={integer} /></td><td className="num"><Value metric={item.minutes_watched} format={integer} /></td></tr>)}</tbody>
          </table>
        </div>
      </Panel>
    );
  }
  return (
    <Panel>
      {forYou?.trends_blocked && <div className="border-b border-line p-3"><Notice tone="warn" title="Tendências bloqueadas">Com dados reais, esta lista usa só o perfil, o backlog, as favoritas e o Analytics do canal.</Notice></div>}
      {forYou?.items.length ? (
        <ul className="divide-y divide-line">{forYou.items.map((item) => (
          <li key={item.term} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
            <span className="min-w-0"><TermLink term={item.term} channel={channel} /><span className="ml-2 text-ink-2">{item.reason}</span></span>
            <Pill>{ORIGIN_LABEL[item.origin] ?? item.origin}</Pill>
          </li>
        ))}</ul>
      ) : <Empty title="Sem sugestões para este canal.">Preencha as palavras e o backlog no perfil do canal.</Empty>}
    </Panel>
  );
}

export default async function Keywords({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const term = str(params.termo);
  const channel = str(params.canal);
  const warning = str(params.aviso);
  const offset = Number(str(params.inicio)) || 0;
  const context = await intelGet<IntelContext>("/context");
  const validChannel = context.channels.some((c) => c.id === channel) ? channel : undefined;
  const tabKeys = term ? TERM_TABS.map((t) => t.key) : CHANNEL_TABS.map((t) => t.key);
  const tab = tabKeys.includes(String(params.aba)) ? String(params.aba) : tabKeys[0];
  const names = new Map(context.channels.map((c) => [c.id, c.name]));
  const data = term ? await intelGet<KeywordAnalysis>("/keywords/analyze", { term, channel_id: validChannel, limit: "25", offset: tab === "videos" ? String(offset) : undefined }) : null;
  const [forYou, ownTerms, favorites, history] = term ? [null, null, { items: [] as Favorite[] }, null] : await Promise.all([
    validChannel && tab === "para-voce" ? intelGet<ForYou>(`/channels/${validChannel}/keywords/for-you`) : null,
    validChannel && tab === "descoberta" ? intelGet<OwnTerms>(`/channels/${validChannel}/keywords/own-terms`) : null,
    validChannel && tab === "favoritos" ? intelGet<{ items: Favorite[] }>(`/channels/${validChannel}/keywords/favorites`) : { items: [] as Favorite[] },
    tab === "historico" ? intelGet<Page<KeywordHistoryItem>>("/keywords/history", { channel_id: validChannel, limit: "30", offset: String(offset) }) : null,
  ]);
  const termLink = (key: string) => `/palavras?termo=${encodeURIComponent(term ?? "")}${validChannel ? `&canal=${validChannel}` : ""}&aba=${key}`;
  const channelLink = (key: string) => `/palavras?aba=${key}${validChannel ? `&canal=${validChannel}` : ""}`;

  return (
    <>
      <PageHeader title="Palavras-chave" intro="Analise um termo, veja variações e perguntas, e guarde favoritas por canal. O volume de busca só aparece com fonte de verdade." />
      <Panel className="mb-5 p-4">
        <ActionForm action={lookupKeyword} submit="Analisar" pending="Analisando..." className="flex flex-wrap items-end gap-3">
          <label className="min-w-56 flex-1 text-sm text-ink-2">Termo<input name="term" required minLength={2} maxLength={100} defaultValue={term} placeholder="Ex.: queda de cartago" className="field mt-1 w-full" /></label>
          <label className="min-w-48 text-sm text-ink-2">Associar ao canal<div className="mt-1"><ChannelSelect context={context} value={validChannel} /></div></label>
          {context.mode === "live" && context.has_api_key && (
            <label className="flex min-h-9 items-center gap-2 text-sm text-ink-2"><input type="checkbox" name="fetch" value="1" defaultChecked /> Buscar no YouTube (usa cota)</label>
          )}
          {context.mode === "live" && !context.has_api_key && <input type="hidden" name="fetch" value="0" />}
        </ActionForm>
        <div className="mt-2"><RealChannelsNote context={context} /></div>
      </Panel>
      {warning && <div className="mb-4"><Notice tone="warn" title="A busca no YouTube não foi feita">{warning} A análise abaixo usa só os vídeos já coletados.</Notice></div>}
      {data ? (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-[1.375rem] font-semibold">{data.term}</h2>
              <OriginPill fictional={data.fictional} />
              {data.is_favorite && <Pill tone="ochre">Favorita</Pill>}
            </div>
            {validChannel && !data.is_favorite && <ActionForm action={addFavorite} submit="Favoritar" tone="quiet" hidden={{ channel_id: validChannel, term: data.term }} />}
            {validChannel && data.is_favorite && <ActionForm action={removeFavorite} submit="Remover favorita" tone="quiet" hidden={{ channel_id: validChannel, term: data.term }} />}
          </div>
          <Tabs items={TERM_TABS} current={tab} href={termLink} />
          {tab === "visao" && <Overview data={data} />}
          {tab === "relacionados" && <Related data={data} channel={validChannel} />}
          {tab === "variacoes" && (
            <Panel className="p-4">
              <p className="mb-3 text-sm text-ink-2">{data.variations.note}</p>
              <ul className="divide-y divide-line text-sm">{data.variations.items.map((item) => <li key={item.term} className="flex flex-wrap justify-between gap-3 py-1.5"><TermLink term={item.term} channel={validChannel} /><span className="text-ink-3">{item.rule}</span></li>)}</ul>
            </Panel>
          )}
          {tab === "perguntas" && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Panel className="p-4">
                <SectionTitle>Ideias de pergunta</SectionTitle>
                <p className="mt-1 text-[0.8125rem] text-ink-3">{data.questions.model_note}</p>
                <ul className="mt-3 space-y-1.5 text-sm">{data.questions.from_model.map((q) => <li key={q}>{q}</li>)}</ul>
              </Panel>
              <Panel className="p-4">
                <SectionTitle>Títulos em forma de pergunta</SectionTitle>
                {data.questions.from_titles.length ? (
                  <ul className="mt-3 divide-y divide-line text-sm">{data.questions.from_titles.map((q) => <li key={q.id} className="py-2"><Link className="hover:underline" href={`/videos/${q.id}`}>{q.title}</Link><div className="flex flex-wrap gap-x-3 text-[0.8125rem] text-ink-3"><span>{q.channel_title}</span><SourceLink url={q.source_url} /></div></li>)}</ul>
                ) : <p className="mt-3 text-sm text-ink-3">Nenhum vídeo coletado com este termo tem título em forma de pergunta.</p>}
              </Panel>
            </div>
          )}
          {tab === "ascensao" && <Rising data={data} channel={validChannel} />}
          {tab === "videos" && (
            <>
              <p className="mb-2 text-sm text-ink-2">{data.sample.note} {data.last_youtube_search_at && `Última busca no YouTube: ${dateTime(data.last_youtube_search_at)}.`}</p>
              <Panel><VideoResults videos={data.sample.videos} empty="Nenhum vídeo coletado com este termo." /><Pagination total={data.sample.total} limit={data.sample.limit} offset={data.sample.offset} href={(next) => `${termLink("videos")}&inicio=${next}`} /></Panel>
            </>
          )}
          <p className="mt-4 text-[0.8125rem] text-ink-3">{compact(data.sample.total)} vídeos coletados com este termo. <Link className="underline" href={`/palavras${validChannel ? `?canal=${validChannel}` : ""}`}>Voltar às listas do canal</Link></p>
        </>
      ) : (
        <>
          <form action="/palavras" className="mb-3 flex flex-wrap items-center gap-2">
            <input type="hidden" name="aba" value={tab} />
            <label htmlFor="canal-palavras" className="text-sm text-ink-2">Ver listas do canal</label>
            <select id="canal-palavras" name="canal" defaultValue={validChannel ?? ""} className="field">
              <option value="">Todos</option>
              {context.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
          </form>
          <Tabs items={CHANNEL_TABS} current={tab} href={channelLink} />
          <ChannelSection tab={tab} channel={validChannel} forYou={forYou} ownTerms={ownTerms} favorites={favorites?.items ?? []} history={history} channels={names} offset={offset} />
        </>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
