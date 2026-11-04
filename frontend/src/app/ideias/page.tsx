import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Empty, PageHeader, Panel, Pill, str } from "@/components/ui";
import { Notice, Pagination, Tabs } from "@/components/intel";
import { duration, FORMAT_LABEL, shortDate } from "@/lib/format";
import { intelGet, type Idea, type IdeasPage } from "@/lib/intel";
import { studioGet, type StudioOverview } from "@/lib/studio";

import { generateIdeas, ideaAct, ideaFavorite, ideaSchedule } from "../intel-actions";

const FILTERS = [{ key: "novas", label: "Novas" }, { key: "salvas", label: "Salvas" }, { key: "favoritas", label: "Favoritas" }, { key: "rejeitadas", label: "Rejeitadas" }, { key: "producao", label: "Em produção" }];
const LEVEL: Record<string, string> = { baixa: "Baixa", media: "Média", alta: "Alta" };
const BASIS: Record<string, { label: string; tone: "warn" | "neutral" | "info" }> = {
  demo_metrics: { label: "Dados fictícios", tone: "warn" }, editorial: { label: "Editorial, sem métricas", tone: "neutral" }, approved_metrics: { label: "Métrica própria", tone: "info" },
};
const PRIORITY: Record<string, string> = { alta: "Prioridade alta", media: "Prioridade média", baixa: "Prioridade baixa" };

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><dt className="text-[0.8125rem] font-medium text-ink-3">{label}</dt><dd className="mt-0.5 text-sm leading-relaxed text-ink-2">{children}</dd></div>;
}

function IdeaCard({ idea, today }: { idea: Idea; today: string }) {
  const hidden = { channel_id: idea.channel_id, idea_id: idea.id };
  const basis = BASIS[idea.data_basis] ?? BASIS.editorial;
  const open = idea.status === "nova" || idea.status === "aceita";
  return (
    <article className="min-w-0 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 className="font-display text-[1.125rem] leading-snug font-semibold"><span className="sr-only">Ideia para vídeo: </span>{idea.subject}</h2>
        <div className="flex flex-wrap gap-1.5">
          {idea.favorite && <Pill tone="ochre">Favorita</Pill>}
          <Pill tone={basis.tone}>{basis.label}</Pill>
          <Pill>{PRIORITY[idea.editorial_priority]}</Pill>
        </div>
      </div>
      <dl className="mt-3 grid gap-3 md:grid-cols-2">
        <Field label="Justificativa">{idea.justification}</Field>
        <Field label="Referências">
          <ul className="space-y-0.5">
            {idea.sources.map((source) => (
              <li key={source.label}>
                {source.url?.startsWith("/") ? <Link className="text-cobalt underline underline-offset-2" href={source.url}>{source.label}</Link> : source.url ? <a className="text-cobalt underline underline-offset-2" href={source.url} target="_blank" rel="noreferrer noopener">{source.label}</a> : source.label}
                {source.fictional && " (fictícia)"}{source.verified === false && " (não verificada)"}
              </li>
            ))}
          </ul>
        </Field>
        <Field label="Títulos">{idea.titles.length ? <ol className="list-decimal space-y-0.5 pl-4">{idea.titles.map((title) => <li key={title}>{title}</li>)}</ol> : "Gere os títulos na página do canal."}</Field>
        <Field label="Conceito de thumbnail">{idea.thumbnail_idea}</Field>
        <Field label="Hook inicial">{idea.hook}</Field>
        <Field label="Público">{idea.target_audience}</Field>
        <Field label="Formato">{FORMAT_LABEL[idea.format]}, cerca de {duration(idea.duration_seconds)}</Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Dificuldade estimada">{idea.difficulty ? LEVEL[idea.difficulty] : "Sem estimativa"}</Field>
          <Field label="Confiança na evidência">{idea.confidence ? LEVEL[idea.confidence] : "Sem estimativa"}</Field>
          <Field label="Recomendada em">{shortDate(`${idea.recommended_on}T12:00:00Z`)}</Field>
        </div>
      </dl>
      {idea.scheduled_on && <p className="mt-2 text-sm font-medium text-good">Calendário: {shortDate(`${idea.scheduled_on}T12:00:00Z`)}</p>}
      <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3">
        {idea.status === "nova" && <ActionForm action={ideaAct} submit="Salvar" hidden={{ ...hidden, action: "salvar" }} />}
        {open && <ActionForm action={ideaAct} submit="Rejeitar" tone="quiet" hidden={{ ...hidden, action: "rejeitar" }} />}
        {idea.status !== "nova" && idea.status !== "em_producao" && idea.status !== "concluida" && <ActionForm action={ideaAct} submit="Restaurar" tone="quiet" hidden={{ ...hidden, action: "restaurar" }} />}
        <ActionForm action={ideaFavorite} submit={idea.favorite ? "Tirar dos favoritos" : "Favoritar"} tone="quiet" hidden={{ ...hidden, favorite: idea.favorite ? "0" : "1" }} />
        {open && (
          <ActionForm action={ideaSchedule} submit="Pôr no calendário" tone="quiet" hidden={hidden} className="flex flex-wrap items-end gap-2">
            <label className="text-[0.8125rem] text-ink-2">Data no calendário<input type="date" name="scheduled_on" required min={today} defaultValue={idea.scheduled_on ?? ""} className="field mt-1 block" /></label>
          </ActionForm>
        )}
        <Link className="ml-auto text-sm text-cobalt underline underline-offset-2" href={`/lab?canal=${idea.channel_id}&assunto=${encodeURIComponent(idea.subject)}&ideia=${idea.id}`}>Abrir no laboratório</Link>
        <Link className="text-sm text-cobalt underline underline-offset-2" href={`/canais/${idea.channel_id}?aba=recomendacoes`}>Abrir no canal</Link>
      </div>
      {idea.facts_to_verify.length > 0 && <p className="mt-2 text-[0.8125rem] text-ink-3">Antes de produzir: {idea.facts_to_verify.join(" ")}</p>}
    </article>
  );
}

export default async function IdeasPageView({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const overview = await studioGet<StudioOverview>("/overview");
  const canal = str(params.canal);
  const channel = overview.channels.find((c) => c.id === canal) ?? overview.channels[0];
  const filter = FILTERS.some((f) => f.key === params.filtro) ? String(params.filtro) : "novas";
  const offset = Number(str(params.inicio)) || 0;
  if (!channel) {
    return <><PageHeader title="Ideias diárias" /><Panel><Empty title="Nenhum canal cadastrado."><Link className="text-cobalt underline" href="/canais/novo">Cadastre um canal</Link> para receber ideias.</Empty></Panel></>;
  }
  const data = await intelGet<IdeasPage>(`/channels/${channel.id}/ideas`, { filtro: filter, offset: String(offset) });
  const today = new Date().toISOString().slice(0, 10);
  const sectionHref = (key: string) => `/ideias?canal=${channel.id}&filtro=${key}`;
  return (
    <>
      <PageHeader title="Ideias diárias" intro="Sugestões para cada canal, a partir do perfil, do histórico, das pesquisas salvas, dos concorrentes e das tendências permitidas. Não há previsão de views.">
        <ActionForm action={generateIdeas} submit="Gerar ideias de hoje" pending="Gerando..." hidden={{ channel_id: channel.id }} doneMessage="Ideias atualizadas." />
      </PageHeader>
      <form action="/ideias" className="mb-4 flex flex-wrap items-center gap-2">
        <input type="hidden" name="filtro" value={filter} />
        <label htmlFor="canal-ideias" className="text-sm text-ink-2">Canal</label>
        <select id="canal-ideias" name="canal" defaultValue={channel.id} className="field max-w-72">{overview.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
      </form>
      {channel.is_demo !== (overview.mode === "demo") && <div className="mb-4"><Notice>{overview.mode === "demo" ? "Canal real no modo demonstração: as ideias usam só o perfil, o histórico e as favoritas dele." : "Canal fictício: não recebe dados reais do YouTube."}</Notice></div>}
      <Tabs items={FILTERS.map((f) => ({ ...f, count: data.counts[f.key] }))} current={filter} href={sectionHref} />
      {data.items.length ? (
        <div className="space-y-3">{data.items.map((idea) => <IdeaCard key={idea.id} idea={idea} today={today} />)}</div>
      ) : (
        <Panel><Empty title="Nenhuma ideia nesta lista.">{filter === "novas" ? "Clique em Gerar ideias de hoje." : "As ideias aparecem aqui quando você as marcar."}</Empty></Panel>
      )}
      <Pagination total={data.total} limit={data.limit} offset={data.offset} href={(next) => `${sectionHref(filter)}&inicio=${next}`} />
      <p className="mt-3 text-[0.8125rem] text-ink-3">{data.estimate_note} As ideias não rodam sozinhas: você decide quando gerar. Confira os fatos e use um ângulo próprio, sem copiar vídeos, roteiros ou thumbnails.</p>
    </>
  );
}

export const dynamic = "force-dynamic";
