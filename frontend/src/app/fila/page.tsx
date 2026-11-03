import { JobCard } from "@/components/studio";
import { Empty, PageHeader, Panel, SectionTitle, str } from "@/components/ui";
import { studioGet, type Job, type StudioOverview } from "@/lib/studio";

const COLUMNS = [
  { title: "Precisa de você", states: ["awaiting_authorization", "failed"], empty: "Nada aguardando sua decisão." },
  { title: "Em produção", states: ["authorized", "running", "delivered"], empty: "Nenhuma tarefa em produção." },
  { title: "Prontas para revisão", states: ["package_ready"], empty: "Nenhum pacote pronto." },
];

export default async function Queue({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const channelId = str((await searchParams).canal);
  const [jobs, overview] = await Promise.all([
    studioGet<{ jobs: Job[] }>("/jobs", { channel_id: channelId }),
    studioGet<StudioOverview>("/overview"),
  ]);
  const cancelled = jobs.jobs.filter((job) => job.state === "cancelled").length;
  return (
    <>
      <PageHeader title="Fila de produção" intro="Todas as tarefas dos seus canais. Você autoriza, os agentes executam, e nada é publicado." />
      <form className="mb-4 flex items-end gap-2">
        <label className="text-[0.8125rem] text-ink-2">Canal<br />
          <select name="canal" defaultValue={channelId ?? ""} className="field">
            <option value="">Todos</option>
            {overview.channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name}</option>)}
          </select>
        </label>
        <button className="min-h-9 rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Filtrar</button>
      </form>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
        {COLUMNS.map((column) => {
          const items = jobs.jobs.filter((job) => column.states.includes(job.state));
          return (
            <section key={column.title} aria-label={column.title}>
              <div className="mb-2 flex items-baseline gap-2"><SectionTitle>{column.title}</SectionTitle><span className="text-sm text-ink-3">{items.length}</span></div>
              {items.length
                ? <div className="space-y-3">{items.map((job) => <JobCard key={job.id} job={job} showChannel />)}</div>
                : <Panel><Empty title={column.empty} /></Panel>}
            </section>
          );
        })}
      </div>
      {cancelled > 0 && <p className="mt-4 text-sm text-ink-3">{cancelled} tarefas canceladas não aparecem aqui.</p>}
    </>
  );
}

export const dynamic = "force-dynamic";
