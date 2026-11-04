import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Empty, PageHeader, Panel, Pill, str } from "@/components/ui";
import { OriginPill } from "@/components/intel";
import { dateTime, integer } from "@/lib/format";
import { intelGet, intelGetOrNull, type CoachConversation, type CoachList, type CoachMessage, type CoachSection, type CoachStatus } from "@/lib/intel";
import { studioGet, type StudioOverview } from "@/lib/studio";

import { askCoach, deleteConversation, renameConversation } from "../intel-actions";

function money(value: number): string {
  return `US$ ${value.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })}`;
}

function SourceAnchor({ source }: { source: { label: string; url: string | null } }) {
  if (source.url?.startsWith("/")) return <Link className="text-cobalt underline underline-offset-2" href={source.url}>{source.label}</Link>;
  if (source.url) return <a className="text-cobalt underline underline-offset-2" href={source.url} target="_blank" rel="noreferrer noopener">{source.label}</a>;
  return <>{source.label}</>;
}

function Block({ title, items, tone, sources }: { title: string; items?: CoachSection[]; tone: string; sources: Record<string, { label: string; url: string | null }> }) {
  if (!items?.length) return null;
  return (
    <section className={`border-l-2 pl-3 ${tone}`}>
      <h3 className="text-[0.8125rem] font-semibold text-ink">{title}</h3>
      <ul className="mt-1 space-y-2 text-sm leading-relaxed text-ink-2">
        {items.map((item) => (
          <li key={item.text}>
            {item.text}
            {item.why && <span className="mt-0.5 block text-[0.8125rem] text-ink-3">Por quê: {item.why}</span>}
            {item.refs.some((ref) => sources[ref]) && (
              <span className="mt-0.5 block text-[0.75rem] text-ink-3">Fonte: {item.refs.filter((ref) => sources[ref]).map((ref, index) => <span key={ref}>{index > 0 && ", "}<SourceAnchor source={sources[ref]} /></span>)}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Answer({ message }: { message: CoachMessage }) {
  const { content } = message;
  const sources = content.sources ?? {};
  const empty = !content.observations?.length && !content.hypotheses?.length && !content.recommendations?.length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {content.fictional && <OriginPill fictional />}
        {content.generated_by && <span title={content.generated_by.note}><Pill tone={content.generated_by.is_ai ? "info" : "neutral"}>{content.generated_by.label}</Pill></span>}
      </div>
      {content.generated_by && !content.generated_by.is_ai && <p className="text-[0.8125rem] text-ink-3">{content.generated_by.note}</p>}
      {empty && <p className="text-sm text-ink-2">Os dados deste canal não bastam para uma resposta fundamentada. Veja o que falta abaixo.</p>}
      <Block title="Observações" items={content.observations} tone="border-good" sources={sources} />
      <Block title="Hipóteses" items={content.hypotheses} tone="border-ochre" sources={sources} />
      <Block title="Recomendações" items={content.recommendations} tone="border-cobalt" sources={sources} />
      {content.limitations && content.limitations.length > 0 && (
        <section><h3 className="text-[0.8125rem] font-semibold text-ink">Limites desta resposta</h3><ul className="mt-1 list-disc space-y-0.5 pl-4 text-[0.8125rem] text-ink-3">{content.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>
      )}
      {content.data_used && content.data_used.length > 0 && (
        <section>
          <h3 className="text-[0.8125rem] font-semibold text-ink">Dados consultados</h3>
          <ul className="mt-1 space-y-0.5 text-[0.8125rem] text-ink-2">
            {content.data_used.map((item) => <li key={`${item.tool}-${item.summary}`}><span className={item.ok && item.items > 0 ? "text-good" : "text-ink-3"}>{item.ok ? (item.items > 0 ? "Com dados" : "Sem dados") : "Falhou"}:</span> {item.summary}</li>)}
          </ul>
        </section>
      )}
      <details className="rounded-md bg-page px-3 py-2 text-[0.8125rem] text-ink-2">
        <summary className="cursor-pointer">Ferramentas usadas ({message.tools.length}) e custo</summary>
        <ul className="mt-2 space-y-1">
          {message.tools.map((tool, index) => (
            <li key={`${tool.tool}-${index}`}><code>{tool.tool}</code>{tool.args.term && <span> ({tool.args.term})</span>}: {tool.summary}{!tool.ok && " Falhou."}</li>
          ))}
        </ul>
        <p className="mt-2">
          {message.is_ai ? `${message.provider}, ${message.model}. ` : "Regras, sem IA. Sem custo de IA. "}
          {message.input_tokens !== null && `${integer(message.input_tokens)} tokens de entrada e ${integer(message.output_tokens ?? 0)} de saída. `}
          {message.is_ai && (message.cost_usd !== null ? `Custo informado: ${money(message.cost_usd)}.` : "Custo em dólar não informado por este provedor.")}
        </p>
      </details>
    </div>
  );
}

export default async function Coach({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const [overview, status] = await Promise.all([studioGet<StudioOverview>("/overview"), intelGet<CoachStatus>("/coach/status")]);
  const canal = str(params.canal);
  const channel = overview.channels.find((c) => c.id === canal) ?? overview.channels[0];
  if (!channel) {
    return <><PageHeader title="Coach" /><Panel><Empty title="Nenhum canal cadastrado."><Link className="text-cobalt underline" href="/canais/novo">Cadastre um canal</Link> para conversar.</Empty></Panel></>;
  }
  const list = await intelGet<CoachList>(`/channels/${channel.id}/coach`);
  const conversationId = str(params.conversa);
  const conversation = conversationId ? await intelGetOrNull<CoachConversation>(`/channels/${channel.id}/coach/${conversationId}`) : null;
  const hidden = { channel_id: channel.id };
  return (
    <>
      <PageHeader title="Coach" intro="Pergunte sobre um canal. As respostas consultam só os dados deste aplicativo e separam o que é fato, hipótese e recomendação.">
        <Pill tone={status.is_ai ? "info" : "neutral"} title={status.note}>{status.label}</Pill>
      </PageHeader>
      <form action="/coach" className="mb-4 flex flex-wrap items-center gap-2">
        <label htmlFor="canal-coach" className="text-sm text-ink-2">Canal</label>
        <select id="canal-coach" name="canal" defaultValue={channel.id} className="field max-w-72">{overview.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
      </form>
      <p className="mb-4 text-sm text-ink-2">{status.note}</p>

      <div className="grid gap-4 lg:grid-cols-[17rem_1fr]">
        <Panel className="h-fit">
          <div className="flex items-center justify-between gap-2 border-b border-line p-3"><h2 className="text-sm font-semibold">Conversas</h2><Link className="text-sm text-cobalt underline underline-offset-2" href={`/coach?canal=${channel.id}`}>Nova</Link></div>
          {list.items.length ? (
            <ul className="divide-y divide-line">
              {list.items.map((item) => (
                <li key={item.id} className={item.id === conversationId ? "bg-page" : ""}>
                  <Link className="block px-3 py-2 text-sm hover:underline" href={`/coach?canal=${channel.id}&conversa=${item.id}`}>{item.title}</Link>
                  <p className="px-3 pb-2 text-[0.75rem] text-ink-3">{dateTime(item.updated_at)}{item.cost_usd > 0 && `, ${money(item.cost_usd)}`}</p>
                </li>
              ))}
            </ul>
          ) : <p className="p-3 text-sm text-ink-3">Nenhuma conversa neste canal.</p>}
          {list.usage.input_tokens > 0 && <p className="border-t border-line p-3 text-[0.75rem] text-ink-3">Uso neste canal: {integer(list.usage.input_tokens + list.usage.output_tokens)} tokens, {money(list.usage.cost_usd)} informados.</p>}
        </Panel>

        <div className="min-w-0 space-y-4">
          {conversation && (
            <Panel className="p-4">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
                <ActionForm action={renameConversation} submit="Renomear" tone="quiet" hidden={{ ...hidden, conversation_id: conversation.conversation.id }} className="flex flex-wrap items-end gap-2">
                  <label className="text-[0.8125rem] text-ink-2">Título da conversa<input name="title" defaultValue={conversation.conversation.title} maxLength={120} required className="field mt-1 block w-64 max-w-full" /></label>
                </ActionForm>
                <ActionForm action={deleteConversation} submit="Apagar conversa" tone="danger" hidden={{ ...hidden, conversation_id: conversation.conversation.id }} />
              </div>
              <ol className="space-y-5">
                {conversation.messages.map((message) => (
                  <li key={message.id}>
                    {message.role === "user"
                      ? <p className="rounded-md bg-pine px-3 py-2 text-sm text-white">{message.content.text}</p>
                      : <Answer message={message} />}
                  </li>
                ))}
              </ol>
            </Panel>
          )}
          {conversationId && !conversation && <Panel><Empty title="Conversa não encontrada neste canal." /></Panel>}

          {!conversation && (
            <Panel className="p-4">
              <h2 className="text-sm font-semibold">Comece por uma destas perguntas</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {status.suggestions.map((question) => (
                  <li key={question}>
                    <ActionForm action={askCoach} submit={question} pending="Consultando..." tone="quiet" hidden={{ ...hidden, question }} />
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel className="p-4">
            <ActionForm action={askCoach} submit="Perguntar" pending="Consultando..." hidden={{ ...hidden, ...(conversation ? { conversation_id: conversation.conversation.id } : {}) }}>
              <label className="mb-3 block text-sm text-ink-2">Sua pergunta
                <textarea name="question" required minLength={3} maxLength={2000} rows={3} className="field mt-1 w-full" placeholder={`Ex.: o que você acha de "queda de Roma" para ${channel.name}?`} />
              </label>
            </ActionForm>
            <p className="mt-2 text-[0.8125rem] text-ink-3">Para analisar um termo, escreva entre aspas. O Coach não publica, não altera canais e não assiste aos vídeos. Confira os dados importantes.</p>
          </Panel>
        </div>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
