import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Pill, SectionTitle } from "@/components/ui";
import { jobAction } from "@/app/canais/actions";
import { JOB_STATE, type AuthStatus, type Channel, type ClaudeStatus, type Job } from "@/lib/studio";
import { dateTime } from "@/lib/format";

export function OriginPill({ isDemo }: { isDemo: boolean }) {
  return isDemo
    ? <Pill tone="warn" title="Canal inventado para demonstração. Não existe no YouTube.">Fictício</Pill>
    : <Pill tone="info" title="Canal cadastrado por você.">Seu canal</Pill>;
}

export function AuthPill({ auth }: { auth: AuthStatus }) {
  const tone = auth.state === "authorized" ? "good" : auth.state === "check_overdue" ? "warn" : "neutral";
  return <Pill tone={tone} title={auth.detail}>{auth.label}</Pill>;
}

export function JobStatePill({ state }: { state: string }) {
  const info = JOB_STATE[state] ?? { label: state, tone: "neutral" as const };
  return <Pill tone={info.tone}>{info.label}</Pill>;
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-page" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="h-full rounded-full bg-cobalt" style={{ width: `${value}%` }} />
    </div>
  );
}

function JobButton({ job, action, label, tone = "quiet", pending }: { job: Job; action: string; label: string; tone?: "primary" | "quiet" | "danger"; pending?: string }) {
  return <ActionForm action={jobAction} submit={label} tone={tone} pending={pending ?? "Enviando..."} hidden={{ channel_id: job.channel_id, job_id: job.id, action }} />;
}

/** Só mostra ações válidas para o estado. Não há ação de publicar. */
export function JobActions({ job }: { job: Job }) {
  const open = !["package_ready", "cancelled", "delivered"].includes(job.state);
  return (
    <div className="flex flex-wrap items-start gap-2">
      {job.state === "awaiting_authorization" && <JobButton job={job} action="authorize" label={job.simulated ? "Autorizar simulação" : "Autorizar produção"} tone="primary" />}
      {job.state === "failed" && <JobButton job={job} action="retry" label="Tentar de novo" tone="primary" />}
      {job.simulated && ["authorized", "running", "delivered"].includes(job.state) && <JobButton job={job} action="simulate-step" label="Avançar simulação" tone="primary" pending="Avançando..." />}
      {job.simulated && job.state === "running" && <JobButton job={job} action="simulate-failure" label="Simular falha" />}
      {open && <JobButton job={job} action="cancel" label="Cancelar" tone="danger" pending="Cancelando..." />}
    </div>
  );
}

export function JobCard({ job, showChannel = false }: { job: Job; showChannel?: boolean }) {
  return (
    <article className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-medium">
            <Link href={`/canais/${job.channel_id}/tarefas/${job.id}`} className="hover:text-cobalt hover:underline">{job.title}</Link>
          </h3>
          <p className="mt-0.5 text-[0.8125rem] text-ink-3">
            {showChannel && job.channel_name && <>{job.channel_name}. </>}
            {job.format === "short" ? "Short" : "Vídeo longo"}. Tentativa {job.attempts} de {job.max_attempts}.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {job.simulated ? <Pill tone="warn" title="Nenhum arquivo é gerado e nenhum render é executado.">Simulada</Pill> : <Pill tone="ochre">Real</Pill>}
          <JobStatePill state={job.state} />
        </div>
      </div>
      {(job.state === "running" || job.progress > 0) && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-[0.8125rem] text-ink-2"><span>{job.step || "Iniciando"}</span><span>{job.progress}%</span></div>
          <ProgressBar value={job.progress} label={`Progresso de ${job.title}`} />
        </div>
      )}
      {job.last_error && <p className="mt-2 text-sm text-bad">{job.last_error}</p>}
      <div className="mt-3"><JobActions job={job} /></div>
    </article>
  );
}

function Check({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return <li className="flex items-center justify-between gap-3 py-1.5 text-sm"><span>{ok ? yes : no}</span><Pill tone={ok ? "good" : "neutral"}>{ok ? "Ok" : "Pendente"}</Pill></li>;
}

export function ClaudePanel({ claude, compact = false }: { claude: ClaudeStatus; compact?: boolean }) {
  const last = claude.recent_agents[0];
  return (
    <div>
      <SectionTitle>Claude Code</SectionTitle>
      <ul className="mt-1 divide-y divide-line">
        <Check ok={claude.cli_found} yes="Comando claude encontrado" no="Comando claude não encontrado" />
        <Check ok={claude.mcp_configured} yes="Servidor yti-producao configurado" no="Arquivo .mcp.json ausente" />
      </ul>
      <p className="mt-2 text-sm text-ink-2">
        {last
          ? <>Último contato: <strong className="font-medium text-ink">{last.agent_id}</strong> em {dateTime(last.last_seen_at)} ({last.last_operation}).</>
          : "Nenhum agente falou com este estúdio ainda."}
      </p>
      {claude.simulated_only && <p className="mt-1 text-[0.8125rem] text-warn">Até agora, só o agente simulado atuou aqui.</p>}
      {!compact && <p className="mt-2 text-[0.8125rem] text-ink-3">Contrato {claude.contract_version}. O agente pode ler, pedir produção e entregar arquivos, mas não pode autorizar nem publicar.</p>}
    </div>
  );
}

const FIELD_LABEL = "text-[0.8125rem] text-ink-2";

export function ChannelFields({ channel }: { channel?: Channel }) {
  const formats = channel?.formats ?? ["long", "short"];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <label className={FIELD_LABEL}>Nome do canal
        <input name="name" required defaultValue={channel?.name} className="field mt-1 w-full" />
      </label>
      <label className={FIELD_LABEL}>Handle
        <input name="handle" defaultValue={channel?.handle ?? ""} className="field mt-1 w-full" placeholder="@meucanal" />
      </label>
      <label className={FIELD_LABEL}>ID do canal no YouTube (opcional)
        <input name="youtube_channel_id" defaultValue={channel?.youtube_channel_id ?? ""} className="field mt-1 w-full" placeholder="UC..." />
      </label>
      <label className={FIELD_LABEL}>Nicho
        <input name="niche" defaultValue={channel?.niche} className="field mt-1 w-full" placeholder="História animada" />
      </label>
      <label className={FIELD_LABEL}>Idioma
        <select name="language" defaultValue={channel?.language ?? "pt"} className="field mt-1 w-full">
          <option value="pt">Português</option><option value="es">Espanhol</option><option value="en">Inglês</option>
        </select>
      </label>
      <label className={FIELD_LABEL}>País principal
        <input name="country" defaultValue={channel?.country} maxLength={2} className="field mt-1 w-full" placeholder="BR" />
      </label>
      <label className={`${FIELD_LABEL} sm:col-span-2`}>Público
        <input name="audience" defaultValue={channel?.audience} className="field mt-1 w-full" placeholder="Quem você quer alcançar" />
      </label>
      <label className={`${FIELD_LABEL} sm:col-span-2`}>Posicionamento editorial
        <textarea name="positioning" rows={2} defaultValue={channel?.positioning} className="field mt-1 w-full" placeholder="O que diferencia este canal" />
      </label>
      <label className={FIELD_LABEL}>Tom de voz
        <input name="tone" defaultValue={channel?.tone} className="field mt-1 w-full" placeholder="Irônico e direto" />
      </label>
      <label className={FIELD_LABEL}>Publicações por semana
        <input name="cadence_per_week" inputMode="decimal" defaultValue={channel?.cadence_per_week ?? ""} className="field mt-1 w-full" />
      </label>
      <label className={FIELD_LABEL}>Palavras do perfil, separadas por vírgula
        <input name="keywords" defaultValue={channel?.keywords.join(", ")} className="field mt-1 w-full" placeholder="roma, cartago, império" />
      </label>
      <label className={FIELD_LABEL}>Temas a evitar, separados por vírgula
        <input name="avoid" defaultValue={channel?.avoid.join(", ")} className="field mt-1 w-full" />
      </label>
      <label className={`${FIELD_LABEL} sm:col-span-2`}>Ideias de tema, uma por linha
        <textarea name="topic_backlog" rows={3} defaultValue={channel?.topic_backlog.join("\n")} className="field mt-1 w-full" />
      </label>
      <fieldset className={FIELD_LABEL}>
        <legend>Formatos</legend>
        <label className="mr-4 inline-flex min-h-9 items-center gap-1.5 text-sm"><input type="checkbox" name="formats" value="long" defaultChecked={formats.includes("long")} /> Vídeos longos</label>
        <label className="inline-flex min-h-9 items-center gap-1.5 text-sm"><input type="checkbox" name="formats" value="short" defaultChecked={formats.includes("short")} /> Shorts</label>
      </fieldset>
      <div className="grid grid-cols-2 gap-3">
        <label className={FIELD_LABEL}>Longo, em minutos
          <input name="long_target_minutes" inputMode="decimal" defaultValue={channel ? channel.long_target_seconds / 60 : 10} className="field mt-1 w-full" />
        </label>
        <label className={FIELD_LABEL}>Short, em segundos
          <input name="short_target_seconds" inputMode="numeric" defaultValue={channel?.short_target_seconds ?? 60} className="field mt-1 w-full" />
        </label>
      </div>
    </div>
  );
}
