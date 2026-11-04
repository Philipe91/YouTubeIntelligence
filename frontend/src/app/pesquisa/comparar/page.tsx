import Link from "next/link";
import { notFound } from "next/navigation";

import { Empty, PageHeader, Panel, SectionTitle, str } from "@/components/ui";
import { OriginPill } from "@/components/intel";
import { dateTime } from "@/lib/format";
import { intelGet, type CompareItem, type RunComparison } from "@/lib/intel";

function Items({ items, showRanks }: { items: CompareItem[]; showRanks?: boolean }) {
  if (!items.length) return <Empty title="Nenhum item aqui." />;
  return (
    <ol className="divide-y divide-line">
      {items.map((item) => (
        <li key={`${item.type}-${item.id}`} className="px-3 py-2 text-sm">
          <span className="text-ink-3">{showRanks ? `${item.rank}º e ${item.rank_b}º` : `${item.rank}º`}</span>{" "}
          {item.title
            ? (item.url ? <a className="text-cobalt underline underline-offset-2" href={item.url} target="_blank" rel="noreferrer noopener">{item.title}</a> : item.title)
            : <span className="text-ink-3">Removido da base</span>}
          {item.channel && <div className="text-[0.8125rem] text-ink-3">{item.channel}</div>}
        </li>
      ))}
    </ol>
  );
}

export default async function Compare({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const a = str(params.a);
  const b = str(params.b);
  if (!a || !b) notFound();
  let data: RunComparison;
  try {
    data = await intelGet<RunComparison>("/research/compare", { a, b });
  } catch (error) {
    if ((error as { status?: number }).status === 404) notFound();
    return <Panel><Empty title="Não dá para comparar estas pesquisas.">{(error as { message_api?: string }).message_api ?? "A API recusou a comparação."}</Empty></Panel>;
  }
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-cobalt underline underline-offset-2" href={`/pesquisa/${a}`}>Voltar à pesquisa</Link></p>
      <PageHeader title="Comparar pesquisas" intro={`"${data.a.query}" (${dateTime(data.a.executed_at)}) com "${data.b.query}" (${dateTime(data.b.executed_at)}). Mostra posições e títulos, sem cálculo.`}>
        <OriginPill fictional={data.a.fictional} />
      </PageHeader>
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel><div className="border-b border-line p-3"><SectionTitle>Nas duas</SectionTitle><p className="text-sm text-ink-3">{data.both.length} itens</p></div><Items items={data.both} showRanks /></Panel>
        <Panel><div className="border-b border-line p-3"><SectionTitle>Só em &ldquo;{data.a.query}&rdquo;</SectionTitle><p className="text-sm text-ink-3">{data.only_a.length} itens</p></div><Items items={data.only_a} /></Panel>
        <Panel><div className="border-b border-line p-3"><SectionTitle>Só em &ldquo;{data.b.query}&rdquo;</SectionTitle><p className="text-sm text-ink-3">{data.only_b.length} itens</p></div><Items items={data.only_b} /></Panel>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
