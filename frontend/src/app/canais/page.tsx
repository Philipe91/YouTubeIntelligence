import Link from "next/link";

import { AuthPill, ClaudePanel, JobCard, OriginPill } from "@/components/studio";
import { Empty, PageHeader, Panel, Pill, SectionTitle } from "@/components/ui";
import { CALENDAR_STATUS, LANGUAGE_LABEL, studioGet, type StudioOverview } from "@/lib/studio";
import { shortDate } from "@/lib/format";

const day = (iso: string) => shortDate(`${iso}T12:00:00Z`);

export default async function Channels() {
  const data = await studioGet<StudioOverview>("/overview");
  const hasDemo = data.channels.some((channel) => channel.is_demo);
  const waiting = data.channels.reduce((total, channel) => total + channel.awaiting_authorization, 0);
  const ready = data.channels.reduce((total, channel) => total + channel.packages_ready, 0);
  const attention = data.jobs.filter((job) => ["awaiting_authorization", "failed", "running", "authorized"].includes(job.state)).slice(0, 4);
  return (
    <>
      <PageHeader
        title="Meus canais dark"
        intro={data.channels.length
          ? `${data.channels.length} canais. ${waiting ? `${waiting} tarefas aguardam sua autorização.` : "Nenhuma tarefa aguarda autorização."} ${ready ? `${ready} pacotes prontos para revisão.` : ""}`
          : undefined}
      >
        <Link href="/canais/novo" className="inline-flex min-h-9 items-center rounded-md bg-pine px-4 text-sm font-medium text-white hover:bg-pine-soft">Cadastrar canal</Link>
      </PageHeader>

      {hasDemo && (
        <p className="mb-4 max-w-3xl rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
          Os canais marcados como fictícios existem só para mostrar como a central funciona, e você pode removê-los. Eles não usam a API do YouTube.
        </p>
      )}

      <Panel>
        {data.channels.length === 0 ? (
          <Empty title="Nenhum canal cadastrado.">Cadastre seu primeiro canal para organizar recomendações, calendário e fila de produção.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table w-full min-w-[54rem]">
              <thead>
                <tr>
                  <th scope="col">Canal</th>
                  <th scope="col">YouTube</th>
                  <th scope="col" className="num">Recomendações</th>
                  <th scope="col" className="num">Na fila</th>
                  <th scope="col" className="num">Para revisar</th>
                  <th scope="col">Próxima publicação</th>
                  <th scope="col">Produção</th>
                </tr>
              </thead>
              <tbody>
                {data.channels.map((channel) => (
                  <tr key={channel.id}>
                    <td className="max-w-[20rem]">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link href={`/canais/${channel.id}`} className="font-medium hover:text-cobalt hover:underline">{channel.name}</Link>
                        <OriginPill isDemo={channel.is_demo} />
                      </div>
                      <div className="mt-0.5 text-[0.8125rem] text-ink-3">{[channel.niche || "Nicho não definido", LANGUAGE_LABEL[channel.language] ?? channel.language].join(", ")}</div>
                    </td>
                    <td><AuthPill auth={channel.youtube_auth} /></td>
                    <td className="num">{channel.open_recommendations}</td>
                    <td className="num">{channel.active_jobs}</td>
                    <td className="num">{channel.packages_ready}</td>
                    <td>
                      {channel.next_scheduled
                        ? <><div className="line-clamp-1">{channel.next_scheduled.title}</div><div className="text-[0.8125rem] text-ink-3">{day(channel.next_scheduled.scheduled_on)}</div></>
                        : <span className="text-ink-3">Nada planejado</span>}
                    </td>
                    <td>
                      {channel.automation.auto_production === "off" ? <Pill>Desligada</Pill>
                        : channel.automation.auto_production === "auto_simulated" ? <Pill tone="warn">Simulação automática</Pill>
                          : <Pill tone="info">Com sua autorização</Pill>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
        <section>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <SectionTitle>Fila de produção</SectionTitle>
            <Link href="/fila" className="text-sm text-cobalt underline underline-offset-2">Ver fila completa</Link>
          </div>
          {attention.length ? (
            <div className="space-y-3">{attention.map((job) => <JobCard key={job.id} job={job} showChannel />)}</div>
          ) : (
            <Panel><Empty title="Nenhuma tarefa em andamento.">Abra um canal e envie uma recomendação para produção.</Empty></Panel>
          )}
        </section>
        <div className="space-y-4">
          <Panel className="p-4"><ClaudePanel claude={data.claude} /></Panel>
          <Panel className="p-4">
            <SectionTitle>Próximos 14 dias</SectionTitle>
            {data.upcoming.length ? (
              <ul className="mt-2 divide-y divide-line">
                {data.upcoming.map((entry) => (
                  <li key={entry.id} className="py-2 text-sm">
                    <div className="flex justify-between gap-3"><Link href={`/canais/${entry.channel_id}?aba=calendario`} className="line-clamp-1 font-medium hover:text-cobalt hover:underline">{entry.title}</Link><span className="shrink-0 text-ink-2">{day(entry.scheduled_on)}</span></div>
                    <div className="text-[0.8125rem] text-ink-3">{entry.channel_name}. {CALENDAR_STATUS[entry.status]}.</div>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-sm text-ink-3">Nada planejado para os próximos dias.</p>}
          </Panel>
        </div>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
