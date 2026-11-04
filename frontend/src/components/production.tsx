import { ActionForm } from "@/components/ActionForm";
import { ProgressBar } from "@/components/studio";
import { Panel, Pill, SectionTitle } from "@/components/ui";
import { reviewJob } from "@/app/canais/actions";
import { dateTime } from "@/lib/format";
import type { BriefingPayload, Job, ProductionView, ScriptScene, Stage } from "@/lib/studio";

const STAGE_TONE = { pendente: "neutral", em_andamento: "info", concluida: "good", falhou: "bad" } as const;
const STAGE_LABEL = { pendente: "Na fila", em_andamento: "Rodando", concluida: "Concluída", falhou: "Falhou" } as const;
const REVIEW_LABEL: Record<string, string> = { aprovado: "Vídeo aprovado por você. Nada foi publicado.", ajustes: "Você pediu ajustes." };

type Artifact = { id: string; kind: string; path: string; label: string };

function fileUrl(channelId: string, jobId: string, artifactId: string, inline = true) {
  return `/canais/${channelId}/tarefas/${jobId}/arquivos/${artifactId}${inline ? "?ver=1" : ""}`;
}

function StageRow({ stage }: { stage: Stage }) {
  const counted = stage.total !== null && stage.done !== null && stage.total > 0;
  return (
    <li className="py-2 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className={stage.status === "pendente" ? "text-ink-3" : ""}>{stage.label}</span>
        <Pill tone={STAGE_TONE[stage.status]}>{STAGE_LABEL[stage.status]}</Pill>
      </div>
      {counted && stage.status === "em_andamento" && (
        <div className="mt-1.5"><ProgressBar value={Math.min(100, Math.round((stage.done! / stage.total!) * 100))} label={`${stage.done} de ${stage.total} quadros`} /></div>
      )}
      {stage.detail && <p className={`mt-0.5 text-[0.8125rem] ${stage.status === "falhou" ? "text-bad" : "text-ink-3"}`}>{stage.detail}</p>}
    </li>
  );
}

const SCENE: Record<string, string> = { mundo: "Cenário animado", quill: "Quill", numero: "Número", documento: "Documento", relogio: "Relógio" };

function sceneLabel(cena: ScriptScene) {
  const place = cena.m === "mundo" ? `${cena.set}, ${cena.quem}` : cena.acao ?? cena.titulo ?? cena.valor ?? cena.hora ?? "";
  return `${SCENE[cena.m] ?? cena.m}${place ? `: ${place}` : ""}`;
}

export function ProductionPanel({ channelId, job, production, briefing, artifacts }: { channelId: string; job: Job; production: ProductionView; briefing: BriefingPayload | null; artifacts: Artifact[] }) {
  const video = artifacts.find((a) => a.kind === "short" || a.kind === "video");
  const sheet = artifacts.find((a) => a.path.endsWith(".jpg"));
  const log = artifacts.find((a) => a.path.endsWith(".log"));
  const { script, stages, validation } = production;
  return (
    <Panel className="p-5">
      <SectionTitle>Produção real</SectionTitle>
      {briefing && (
        <dl className="mt-2 space-y-1.5 text-sm">
          <div><dt className="text-ink-3">Ideia escolhida</dt><dd>{briefing.subject}</dd></div>
          <div><dt className="text-ink-3">Título recomendado</dt><dd className="font-medium">{briefing.chosen_title}</dd></div>
          <div><dt className="text-ink-3">Briefing aprovado</dt><dd>{briefing.hook} Duração alvo de {briefing.duration_seconds} s.</dd></div>
        </dl>
      )}

      <h3 className="mt-4 text-sm font-medium">Etapas</h3>
      {stages.length === 0
        ? <p className="mt-1 text-sm text-ink-3">{job.lease_owner ? `${job.lease_owner} ainda está escrevendo o roteiro.` : "Aguardando o Claude Code assumir a tarefa."}</p>
        : <ol className="mt-1 divide-y divide-line">{stages.map((stage) => <StageRow key={stage.stage} stage={stage} />)}</ol>}
      {stages.length > 0 && <p className="mt-1 text-[0.8125rem] text-ink-3">Situação gravada pelo processo que renderiza. Os quadros são contados no disco.</p>}

      {script && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium">Roteiro, {script.cenas.length} cenas, de {script.submitted_by}</summary>
          <p className="mt-2 text-sm text-ink-2">{script.resumo}</p>
          <ol className="mt-2 divide-y divide-line">
            {script.cenas.map((cena, index) => (
              <li key={index} className="py-2 text-sm">
                <p>{cena.texto}</p>
                <p className="text-[0.8125rem] text-ink-3">{sceneLabel(cena)}</p>
              </li>
            ))}
          </ol>
          <h4 className="mt-2 text-[0.8125rem] font-medium">Fontes indicadas pelo agente</h4>
          <ul className="mt-0.5 list-disc pl-4 text-[0.8125rem] text-ink-2">
            {script.fontes.map((fonte) => <li key={fonte.label}>{fonte.url ? <a href={fonte.url} rel="noreferrer noopener" className="text-cobalt underline underline-offset-2">{fonte.label}</a> : fonte.label}</li>)}
          </ul>
          {(script.fatos_a_conferir ?? []).length > 0 && (
            <>
              <h4 className="mt-2 text-[0.8125rem] font-medium">Confira antes de usar</h4>
              <ul className="mt-0.5 list-disc pl-4 text-[0.8125rem] text-ink-2">{script.fatos_a_conferir!.map((fato) => <li key={fato}>{fato}</li>)}</ul>
            </>
          )}
        </details>
      )}

      {video && !video.path.startsWith("simulado://") && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Vídeo gerado</h3>
          <video controls preload="metadata" src={fileUrl(channelId, job.id, video.id)} className="mt-2 aspect-[9/16] max-h-[32rem] rounded-md bg-ink" aria-label={`Vídeo: ${job.title}`} />
          {validation && (
            <p className={`mt-2 text-sm ${validation.ok ? "text-ink-2" : "text-bad"}`}>
              {validation.ok
                ? `Arquivo conferido: ${validation.width}x${validation.height}, ${validation.duration_seconds} s, ${validation.video_codec} e ${validation.audio_codec}, ${(validation.size_bytes / 1048576).toFixed(1)} MB. Por ${validation.validated_by}, ${dateTime(validation.validated_at)}.`
                : validation.problems.join(" ")}
            </p>
          )}
          <p className="mt-2 flex flex-wrap gap-x-4 text-sm">
            {sheet && <a href={fileUrl(channelId, job.id, sheet.id)} className="text-cobalt underline underline-offset-2">Ver folha de contato</a>}
            {log && <a href={fileUrl(channelId, job.id, log.id, false)} className="text-cobalt underline underline-offset-2">Baixar registro completo</a>}
          </p>
        </div>
      )}

      {job.state === "package_ready" && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Sua revisão</h3>
          {job.review_status && (
            <p className="mt-1 text-sm">
              {REVIEW_LABEL[job.review_status]}{job.review_note ? ` Nota: ${job.review_note}` : ""}{job.reviewed_at ? ` Em ${dateTime(job.reviewed_at)}.` : ""}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-start gap-3">
            <ActionForm action={reviewJob} submit="Aprovar vídeo" pending="Salvando..." hidden={{ channel_id: channelId, job_id: job.id, decision: "aprovado" }} />
            <ActionForm action={reviewJob} tone="quiet" submit="Pedir ajustes" pending="Salvando..." hidden={{ channel_id: channelId, job_id: job.id, decision: "ajustes" }}>
              <label className="mb-2 block text-[0.8125rem] text-ink-2">O que mudar
                <textarea name="note" rows={2} maxLength={1000} className="field mt-1 w-full min-w-64" />
              </label>
            </ActionForm>
          </div>
          <p className="mt-2 text-[0.8125rem] text-ink-3">Aprovar só registra sua decisão. Nada é enviado ao YouTube.</p>
        </div>
      )}
    </Panel>
  );
}
