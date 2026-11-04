import Link from "next/link";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/AutoRefresh";
import { ProductionPanel } from "@/components/production";
import { AttemptsTable, FileLink, JobActions, JobStatePill, ProgressBar } from "@/components/studio";
import { PageHeader, Panel, Pill, SectionTitle } from "@/components/ui";
import { dateTime } from "@/lib/format";
import { studioGetOrNull, type JobDetail } from "@/lib/studio";

const LEVEL = { info: "neutral", warning: "warn", error: "bad" } as const;
const LEVEL_LABEL: Record<string, string> = { info: "Info", warning: "Aviso", error: "Erro" };

export default async function JobPage({ params }: { params: Promise<{ id: string; job: string }> }) {
  const { id, job: jobId } = await params;
  const data = await studioGetOrNull<JobDetail>(`/channels/${encodeURIComponent(id)}/jobs/${encodeURIComponent(jobId)}`);
  if (!data) notFound();
  const { job, events, artifacts, package: pack, attempt_history: attempts, briefing } = data;
  return (
    <>
      <AutoRefresh active={["authorized", "running", "delivered"].includes(job.state)} />
      <p className="mb-2 text-sm"><Link href={`/canais/${id}?aba=fila`} className="text-cobalt underline underline-offset-2">Voltar à fila do canal</Link></p>
      <PageHeader title={job.title} intro={`Tarefa ${job.id}. Pedida por ${job.requested_by} em ${dateTime(job.created_at)}.`}>
        <div className="flex flex-wrap gap-1.5">{job.simulated ? <Pill tone="warn">Simulada</Pill> : <Pill tone="ochre">Real</Pill>}<JobStatePill state={job.state} /></div>
      </PageHeader>
      {job.simulated && <p className="mb-4 max-w-3xl rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">Tarefa simulada: nenhum vídeo foi renderizado. O único arquivo real é um texto de teste.</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-4">
          <Panel className="p-4">
            <SectionTitle>Progresso</SectionTitle>
            <div className="mt-2 mb-1 flex justify-between text-sm text-ink-2"><span>{job.step || "Sem etapa ativa"}</span><span>{job.progress}%</span></div>
            <ProgressBar value={job.progress} label="Progresso da tarefa" />
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div><dt className="text-ink-3">Tentativas</dt><dd>{job.attempts} de {job.max_attempts}</dd></div>
              <div><dt className="text-ink-3">Agente atual</dt><dd>{job.lease_owner ?? "Nenhum"}</dd></div>
              <div><dt className="text-ink-3">Autorizada por</dt><dd>{job.authorized_by ?? "Ainda não autorizada"}</dd></div>
              <div><dt className="text-ink-3">Prazo do agente</dt><dd>{job.lease_expires_at ? dateTime(job.lease_expires_at) : "Sem prazo ativo"}</dd></div>
            </dl>
            {job.last_error && <p className="mt-3 rounded-md bg-bad-soft px-2.5 py-1.5 text-sm text-bad">{job.last_error}</p>}
            <div className="mt-3"><JobActions job={job} /></div>
          </Panel>
          {!job.simulated && <ProductionPanel channelId={id} job={job} production={data} briefing={briefing} artifacts={artifacts} />}
          <Panel className="p-4">
            <SectionTitle>Histórico de execuções</SectionTitle>
            <div className="mt-2"><AttemptsTable attempts={attempts} /></div>
          </Panel>
          {briefing && (
            <Panel className="p-4">
              <SectionTitle>Briefing aprovado</SectionTitle>
              <dl className="mt-2 space-y-1.5 text-sm">
                <div><dt className="text-ink-3">Título</dt><dd>{briefing.chosen_title}</dd></div>
                <div><dt className="text-ink-3">Hook</dt><dd>{briefing.hook}</dd></div>
                <div><dt className="text-ink-3">Estrutura</dt><dd>{briefing.outline.map((s) => `${s.section} (${s.target_seconds} s)`).join(", ")}</dd></div>
              </dl>
            </Panel>
          )}
          <Panel className="p-4">
            <SectionTitle>Registro</SectionTitle>
            {events.length === 0 ? <p className="mt-2 text-sm text-ink-3">Sem eventos.</p> : (
              <ol className="mt-2 divide-y divide-line">
                {events.map((event, index) => (
                  <li key={index} className="flex flex-wrap items-baseline gap-2 py-1.5 text-sm">
                    <Pill tone={LEVEL[event.level as keyof typeof LEVEL] ?? "neutral"}>{LEVEL_LABEL[event.level] ?? event.level}</Pill>
                    <span className="min-w-0 flex-1">{event.message}</span>
                    <span className="text-[0.8125rem] text-ink-3">{dateTime(event.at)}</span>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
        <div className="space-y-4">
          <Panel className="p-4">
            <SectionTitle>Arquivos entregues</SectionTitle>
            {artifacts.length === 0 ? <p className="mt-2 text-sm text-ink-3">Nenhum arquivo ainda.</p> : (
              <ul className="mt-2 divide-y divide-line">
                {artifacts.map((artifact) => (
                  <li key={artifact.id} className="py-2 text-sm">
                    <FileLink channelId={id} jobId={job.id} artifact={artifact} />
                    {artifact.sha256 && <p className="text-[0.8125rem] text-ink-3">SHA-256 {artifact.sha256.slice(0, 16)}.</p>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel className="p-4">
            <SectionTitle>Pacote de publicação</SectionTitle>
            {!pack ? <p className="mt-2 text-sm text-ink-3">Ainda não preparado.</p> : (
              <>
                <p className="mt-2"><Pill tone="good">PRONTO PARA REVISÃO</Pill></p>
                <dl className="mt-2 space-y-1.5 text-sm">
                  <div><dt className="text-ink-3">Título</dt><dd>{pack.title}</dd></div>
                  <div><dt className="text-ink-3">Descrição</dt><dd className="whitespace-pre-line">{pack.description}</dd></div>
                  <div><dt className="text-ink-3">Tags</dt><dd>{pack.tags.join(", ") || "Nenhuma"}</dd></div>
                </dl>
                <h3 className="mt-3 text-sm font-medium">Antes de publicar</h3>
                <ul className="mt-1 list-disc pl-4 text-sm text-ink-2">{pack.checklist.map((item) => <li key={item}>{item}</li>)}</ul>
                <p className="mt-3 text-[0.8125rem] text-ink-3">Esta versão não publica nada: nada foi enviado ao YouTube.</p>
              </>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
