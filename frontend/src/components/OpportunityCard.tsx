import Link from "next/link";

import { Meter } from "@/components/Charts";
import { Mark } from "@/components/Mark";
import { Pill } from "@/components/ui";
import type { OpportunityRow } from "@/lib/api";
import { integer } from "@/lib/format";

export function opportunityHref(item: Pick<OpportunityRow, "topic" | "format">) {
  return `/oportunidades/detalhe?topic=${encodeURIComponent(item.topic)}&f=${item.format}`;
}

export function OpportunityCard({ item, rank }: { item: OpportunityRow; rank?: number }) {
  return (
    <article className="flex flex-col rounded-lg border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-[1.0625rem] leading-snug font-semibold">
          {rank !== undefined && <span className="mr-1.5 text-ink-3">{rank}.</span>}
          <Link href={opportunityHref(item)} className="hover:text-cobalt hover:underline">{item.topic}</Link>
        </h3>
        <div className="text-right" title="Ranking experimental. Não prevê o resultado de nenhum vídeo.">
          {item.score.value === null ? (
            <Pill>Sem pontuação</Pill>
          ) : (
            <span className="inline-flex items-center gap-1.5 font-display text-[1.375rem] leading-none font-semibold">
              <Mark kind="estimated" /> {integer(item.score.value)}
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
        <Meter label="Demanda (proxy)" value={item.demand.value} title={item.demand.source} />
        <Meter label="Concorrência" value={item.competition.value} tone="#a8650a" title={item.competition.source} />
        <Meter label="Relevância" value={item.relevance.value} title={item.relevance.source} />
        <Meter label="Confiança" value={item.confidence.value} tone="#46544e" title={item.confidence.source} />
      </div>
      <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-2">{item.justification[0]}</p>
    </article>
  );
}
