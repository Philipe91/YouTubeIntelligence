import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { AttemptsTable, ClaudePanel, FileLink, JobActions, JobStatePill, ProgressBar } from "@/components/studio";
import { Panel, Pill, SectionTitle } from "@/components/ui";
import {
  acknowledgeAlert, approveBriefing, createRecommendation, dispatchBriefing, generateTitles,
} from "@/app/canais/actions";
import { dateTime, duration, shortDate } from "@/lib/format";
import { CALENDAR_STATUS, LANGUAGE_LABEL, type ChannelDetail, type Cockpit } from "@/lib/studio";

const day = (iso: string) => shortDate(`${iso}T12:00:00Z`);

export function AlertsBar({ channelId, cockpit }: { channelId: string; cockpit: Cockpit }) {
  if (cockpit.alerts.length === 0) return null;
  return (
    <section aria-label="Alertas" className="mb-5 rounded-lg border border-bad/40 bg-bad-soft p-4">
      <h2 className="font-display text-[1.0625rem] font-semibold text-bad">Alertas de produção</h2>
      <ul className="mt-2 divide-y divide-bad/20">
        {cockpit.alerts.map((alert) => (
          <li key={alert.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
            <div className="min-w-0">
              <Pill tone={alert.level === "error" ? "bad" : "warn"}>{alert.level === "error" ? "Erro" : "Aviso"}</Pill>{" "}
              <span className="text-ink">{alert.message}</span>
              <div className="text-[0.8125rem] text-ink-2">
                <Link href={`/canais/${channelId}/tarefas/${alert.job_id}`} className="underline underline-offset-2">{alert.job_title}</Link>, {dateTime(alert.at)}
              </div>
            </div>
            <ActionForm action={acknowledgeAlert} submit="Marcar como visto" tone="quiet" pending="Salvando..." hidden={{ channel_id: channelId, event_id: String(alert.id) }} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function NewRecommendationForm({ channel }: { channel: ChannelDetail }) {
  return (
    <ActionForm action={createRecommendation} submit="Criar recomendação" pending="Criando..." resetOnSuccess hidden={{ channel_id: channel.id }}>
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="text-[0.8125rem] text-ink-2 sm:col-span-2">Assunto do vídeo<input name="subject" required className="field mt-1 w-full" /></label>
        <label className="text-[0.8125rem] text-ink-2 sm:col-span-2">Justificativa<textarea name="justification" rows={2} required className="field mt-1 w-full" /></label>
        <label className="text-[0.8125rem] text-ink-2">Formato
          <select name="format" defaultValue={channel.formats[0]} className="field mt-1 w-full">
            {channel.formats.map((f) => <option key={f} value={f}>{f === "short" ? "Short" : "Vídeo longo"}</option>)}
          </select>
        </label>
        <label className="text-[0.8125rem] text-ink-2">Prioridade
          <select name="editorial_priority" defaultValue="media" className="field mt-1 w-full"><option value="alta">Alta</option><option value="media">Média</option><option value="baixa">Baixa</option></select>
        </label>
      </div>
    </ActionForm>
  );
}

function NextVideo({ channel, cockpit }: { channel: ChannelDetail; cockpit: Cockpit }) {
  const item = cockpit.next_recommendation;
  const briefing = cockpit.briefing;
  if (!item) {
    return (
      <Panel className="p-5">
        <SectionTitle>Próximo vídeo recomendado</SectionTitle>
        <p className="mt-1 mb-3 text-sm text-ink-2">Nenhuma recomendação aberta. Crie uma aqui ou gere pela aba Recomendações.</p>
        <NewRecommendationForm channel={channel} />
      </Panel>
    );
  }
  const hidden = { channel_id: channel.id, recommendation_id: item.id };
  const selected = briefing?.chosen_title ?? item.titles[0];
  const isCustom = Boolean(briefing && !item.titles.includes(briefing.chosen_title));
  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm text-ink-3">Próximo vídeo recomendado</p>
          <h2 className="font-display text-[1.375rem] leading-snug font-semibold">{item.subject}</h2>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {item.data_basis === "demo_metrics" ? <Pill tone="warn">Dados fictícios</Pill> : item.data_basis === "editorial" ? <Pill>Editorial, sem métricas</Pill> : <Pill tone="info">Métrica própria</Pill>}
          <Pill>{item.format === "short" ? "Short" : "Vídeo longo"}, {duration(item.duration_seconds)}</Pill>
        </div>
      </div>
      <h3 className="mt-3 text-sm font-medium">Justificativa</h3>
      <p className="mt-0.5 text-sm leading-relaxed text-ink-2">{item.justification}</p>

      <h3 className="mt-4 text-sm font-medium">Opções de título</h3>
      {item.titles.length === 0 ? (
        <div className="mt-1.5">
          <p className="mb-2 text-sm text-ink-2">Ainda sem títulos. Eles são rascunhos por regras, para você ajustar.</p>
          <ActionForm action={generateTitles} submit="Gerar três títulos" pending="Gerando..." hidden={hidden} />
        </div>
      ) : (
        <ActionForm action={approveBriefing} submit={briefing ? "Aprovar briefing de novo" : "Aprovar briefing"} pending="Aprovando..." tone={briefing ? "quiet" : "primary"} className="mt-1" hidden={hidden}>
          <fieldset className="mb-3 space-y-1.5">
            <legend className="sr-only">Escolha um título</legend>
            {item.titles.map((title) => (
              <label key={title} className="flex items-start gap-2 text-sm"><input type="radio" name="chosen" value={title} defaultChecked={!isCustom && selected === title} className="mt-1" /> {title}</label>
            ))}
            <label className="flex items-center gap-2 text-sm"><input type="radio" name="chosen" value="__outro__" defaultChecked={isCustom} /> Outro:
              <input name="custom_title" maxLength={100} defaultValue={isCustom ? briefing?.chosen_title : ""} aria-label="Título próprio" className="field min-w-0 flex-1" />
            </label>
          </fieldset>
          <label className="mb-3 block max-w-xs text-[0.8125rem] text-ink-2">Data no calendário (opcional)<input type="date" name="planned_on" className="field mt-1 w-full" /></label>
        </ActionForm>
      )}

      {briefing && (
        <div className="mt-4 border-t border-line pt-4">
          <div className="flex flex-wrap items-center gap-2"><Pill tone="good">Briefing aprovado</Pill><span className="text-[0.8125rem] text-ink-3">{dateTime(briefing.approved_at)}</span></div>
          <p className="mt-2 text-sm font-medium">{briefing.chosen_title}</p>
          <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            <div><dt className="text-ink-3">Hook</dt><dd>{briefing.payload.hook}</dd></div>
            <div><dt className="text-ink-3">Thumbnail</dt><dd>{briefing.payload.thumbnail_idea}</dd></div>
            <div><dt className="text-ink-3">Público</dt><dd>{briefing.payload.target_audience}</dd></div>
            <div><dt className="text-ink-3">Estrutura</dt><dd>{briefing.payload.outline.map((s) => `${s.section} (${s.target_seconds} s)`).join(", ")}</dd></div>
          </dl>
          <div className="mt-3">
            <ActionForm action={dispatchBriefing} submit="Disponibilizar ao Claude Code" pending="Enviando..." hidden={{ channel_id: channel.id, briefing_id: briefing.id, form_key: `ui:${briefing.id}:${briefing.updated_at}` }} />
            <p className="mt-1.5 text-[0.8125rem] text-ink-3">Cria uma tarefa simulada, já autorizada por você. Nada é publicado.</p>
          </div>
        </div>
      )}
    </Panel>
  );
}

function ClaudeTask({ channel, cockpit }: { channel: ChannelDetail; cockpit: Cockpit }) {
  const job = cockpit.current_job;
  return (
    <Panel className="p-5">
      <SectionTitle>Tarefa do Claude Code</SectionTitle>
      {!job ? <p className="mt-2 text-sm text-ink-3">Nenhuma tarefa ativa. Aprove um briefing e disponibilize.</p> : (
        <>
          <p className="mt-2 font-medium"><Link href={`/canais/${channel.id}/tarefas/${job.id}`} className="hover:text-cobalt hover:underline">{job.title}</Link></p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {job.simulated ? <Pill tone="warn">Simulada</Pill> : <Pill tone="ochre">Real</Pill>}
            <JobStatePill state={job.state} />
          </div>
          <p className="mt-2 text-sm text-ink-2">
            {job.state === "authorized" && "Disponível: aguardando um agente assumir pelo MCP yti-producao."}
            {job.state === "running" && <>Com <strong className="font-medium text-ink">{job.lease_owner}</strong>. Tentativa {job.attempts} de {job.max_attempts}.</>}
            {job.state === "awaiting_authorization" && "Um agente pediu esta tarefa. Ela só anda com a sua autorização."}
            {job.state === "failed" && "Parou depois de falhar. Reabra ou cancele."}
            {job.state === "delivered" && "Arquivos entregues. Falta o pacote para revisão."}
            {job.state === "package_ready" && "Pacote pronto para você revisar. Nada foi publicado."}
          </p>
          <div className="mt-3">
            <div className="mb-1 flex justify-between text-[0.8125rem] text-ink-2"><span>{job.step || "Sem etapa ativa"}</span><span>{job.progress}%</span></div>
            <ProgressBar value={job.progress} label="Progresso da produção" />
          </div>
          {job.last_error && <p className="mt-2 text-sm text-bad">{job.last_error}</p>}
          <div className="mt-3"><JobActions job={job} /></div>
        </>
      )}
    </Panel>
  );
}

export function ChannelCockpit({ channel, cockpit }: { channel: ChannelDetail; cockpit: Cockpit }) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div className="min-w-0 space-y-4">
        <NextVideo channel={channel} cockpit={cockpit} />
        <Panel className="p-5">
          <SectionTitle>Histórico de execuções</SectionTitle>
          <div className="mt-2"><AttemptsTable attempts={cockpit.attempts} showTitle /></div>
        </Panel>
        {cockpit.next_recommendation && (
          <Panel className="p-5">
            <details>
              <summary className="cursor-pointer font-display text-[1.0625rem] font-semibold">Criar outra recomendação</summary>
              <div className="mt-3"><NewRecommendationForm channel={channel} /></div>
            </details>
          </Panel>
        )}
      </div>
      <div className="min-w-0 space-y-4">
        <ClaudeTask channel={channel} cockpit={cockpit} />
        <Panel className="p-5">
          <SectionTitle>Arquivos gerados</SectionTitle>
          {cockpit.artifacts.length === 0 ? <p className="mt-2 text-sm text-ink-3">Nenhum arquivo ainda.</p> : (
            <ul className="mt-2 divide-y divide-line">
              {cockpit.artifacts.map((artifact) => (
                <li key={artifact.id} className="py-2 text-sm">
                  <FileLink channelId={channel.id} jobId={artifact.job_id} artifact={artifact} />
                  <p className="text-[0.8125rem] text-ink-3">{artifact.job_title}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel className="p-5">
          <div className="flex items-baseline justify-between gap-3">
            <SectionTitle>Calendário editorial</SectionTitle>
            <Link href={`/canais/${channel.id}?aba=calendario`} className="text-sm text-cobalt underline underline-offset-2">Abrir</Link>
          </div>
          {cockpit.upcoming.length === 0 ? <p className="mt-2 text-sm text-ink-3">Nada planejado.</p> : (
            <ul className="mt-2 divide-y divide-line">
              {cockpit.upcoming.map((entry) => (
                <li key={entry.id} className="py-1.5 text-sm">
                  <div className="flex justify-between gap-3"><span className="line-clamp-1">{entry.title}</span><span className="shrink-0 text-ink-2">{day(entry.scheduled_on)}</span></div>
                  <div className="text-[0.8125rem] text-ink-3">{CALENDAR_STATUS[entry.status]}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel className="p-5"><ClaudePanel claude={channel.claude} compact /></Panel>
        <Panel className="p-5">
          <SectionTitle>Contexto do canal</SectionTitle>
          <dl className="mt-2 space-y-1.5 text-sm">
            <div><dt className="text-ink-3">Nicho, idioma</dt><dd>{[channel.niche || "Nicho não definido", LANGUAGE_LABEL[channel.language] ?? channel.language, channel.country].filter(Boolean).join(", ")}</dd></div>
            <div><dt className="text-ink-3">Público</dt><dd>{channel.audience || "Não definido"}</dd></div>
            <div><dt className="text-ink-3">YouTube</dt><dd>{channel.youtube_auth.detail}</dd></div>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
