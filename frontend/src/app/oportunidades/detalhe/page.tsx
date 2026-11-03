import { notFound } from "next/navigation";

import { Meter } from "@/components/Charts";
import { Value } from "@/components/Mark";
import { VideoTable } from "@/components/VideoTable";
import { BlockedNotice, PageHeader, Panel, Pill, SectionTitle, formatParam, str } from "@/components/ui";
import { api, apiOrNull, type Generation, type OpportunityDetail, type SystemStatus } from "@/lib/api";
import { dateTime, integer } from "@/lib/format";

import { GenerateButton } from "./GenerateButton";

const PART_LABEL: Record<string, string> = {
  porte_dos_canais: "Porte dos canais",
  oferta_recente: "Oferta recente",
  resultados_aproximados: "Resultados aproximados",
};

function GenerationBlock({ item }: { item: Generation }) {
  return (
    <Panel className="p-4">
      <div className="flex flex-wrap items-center gap-2 text-[0.8125rem] text-ink-3">
        {item.is_ai ? <Pill tone="info">Gerado por IA: {item.model}</Pill> : <Pill tone="warn">Modelo sem IA</Pill>}
        <span>{dateTime(item.created_at)}</span>
      </div>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        {item.output.ideas.map((idea, index) => (
          <article key={index} className="flex flex-col gap-2.5 text-sm">
            <h3 className="font-display text-[1.0625rem] leading-snug font-semibold">{idea.working_title}</h3>
            <div><span className="text-ink-3">Ângulo. </span>{idea.angle}</div>
            <div><span className="text-ink-3">Hook. </span>{idea.hook}</div>
            <details>
              <summary className="cursor-pointer text-cobalt">Títulos, briefing e roteiro</summary>
              <div className="mt-2 space-y-2.5">
                <ul className="list-disc pl-4">{idea.title_options.map((title) => <li key={title}>{title}</li>)}</ul>
                <p className="leading-relaxed">{idea.brief}</p>
                {idea.script_outline.map((section) => (
                  <div key={section.section}>
                    <p className="font-medium">{section.section}</p>
                    <ul className="list-disc pl-4">{section.beats.map((beat) => <li key={beat}>{beat}</li>)}</ul>
                  </div>
                ))}
              </div>
            </details>
            <div className="rounded-md bg-warn-soft p-2.5 text-[0.8125rem] text-warn">
              <p className="font-medium">Confira antes de gravar</p>
              <ul className="mt-1 list-disc pl-4">{idea.facts_to_verify.map((fact) => <li key={fact}>{fact}</li>)}</ul>
            </div>
          </article>
        ))}
      </div>
      {item.output.limitations.length > 0 && (
        <ul className="mt-3 list-disc pl-4 text-[0.8125rem] text-ink-3">{item.output.limitations.map((text) => <li key={text}>{text}</li>)}</ul>
      )}
    </Panel>
  );
}

export default async function OpportunityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const topic = str(params.topic);
  const format = formatParam(params.f);
  if (!topic) notFound();
  const [data, system] = await Promise.all([
    apiOrNull<OpportunityDetail>("/api/opportunities/detail", { topic, format }),
    api<SystemStatus>("/api/system"),
  ]);
  if (!data) notFound();
  if (data.blocked) return <BlockedNotice reason={data.reason} />;
  const usesAi = system.ai.provider !== "none";

  return (
    <>
      <PageHeader title={data.topic} intro={`Tema de busca, em ${data.format === "short" ? "Shorts" : "vídeos longos"}. Estes números apontam onde pesquisar e não preveem o resultado de um vídeo.`} />

      <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
        <Panel className="p-5">
          <div className="flex items-baseline justify-between gap-3">
            <SectionTitle>Pontuação experimental</SectionTitle>
            <span className="font-display text-[1.875rem] leading-none font-semibold"><Value metric={data.score} format={integer} muted="Sem pontuação" /></span>
          </div>
          <div className="mt-4 space-y-3">
            <Meter label="Demanda (proxy, não é volume de busca)" value={data.demand.value} title={data.demand.source} />
            <Meter label="Concorrência" value={data.competition.value} tone="#a8650a" title={data.competition.source} />
            <Meter label="Relevância para o nicho e o canal" value={data.relevance.value} title={data.relevance.source} />
            <Meter label="Confiança nos dados" value={data.confidence.value} tone="#46544e" title={data.confidence.source} />
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-sm">
            <span className="text-ink-2">Volume de busca</span>
            <Value metric={data.search_volume} format={integer} muted="Indisponível" />
          </div>
          <p className="mt-1 text-[0.8125rem] text-ink-3">{data.search_volume.reason}</p>
        </Panel>
        <Panel className="p-5">
          <SectionTitle>Por que esta pontuação</SectionTitle>
          <ul className="mt-3 list-disc space-y-1.5 pl-4 text-[0.9375rem] leading-relaxed text-ink-2">
            {data.justification.map((line) => <li key={line}>{line}</li>)}
          </ul>
          {Object.keys(data.competition_parts).length > 0 && (
            <>
              <h3 className="mt-4 text-sm font-medium">Componentes da concorrência</h3>
              <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 text-sm text-ink-2">
                {Object.entries(data.competition_parts).map(([key, value]) => (
                  <div key={key} className="contents"><dt>{PART_LABEL[key] ?? key}</dt><dd className="text-right">{integer(value)}</dd></div>
                ))}
              </dl>
            </>
          )}
          <p className="mt-4 text-[0.8125rem] text-ink-3">{data.origin_note}</p>
        </Panel>
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionTitle>Ideias, títulos, hooks e roteiro</SectionTitle>
          <p className="mt-0.5 text-sm text-ink-2">
            {usesAi ? `Usa ${system.ai.provider === "anthropic" ? "a API paga da Anthropic" : "o comando claude desta máquina"} com o modelo ${system.ai.model}.` : "Nenhum provedor de IA configurado: gera só uma estrutura para preencher, sem custo."}
          </p>
        </div>
        {data.status === "ok" ? <GenerateButton topic={data.topic} format={data.format} usesAi={usesAi} /> : <Pill>Amostra insuficiente para gerar ideias com evidência</Pill>}
      </div>
      <div className="mt-3 space-y-3">{data.generations.map((item) => <GenerationBlock key={item.id} item={item} />)}</div>

      <h2 className="mt-8 mb-3 font-display text-[1.1875rem] font-semibold">Vídeos da amostra</h2>
      <Panel><VideoTable videos={data.videos} /></Panel>
    </>
  );
}

export const dynamic = "force-dynamic";
