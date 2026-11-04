import { ActionForm } from "@/components/ActionForm";
import { Notice } from "@/components/intel";
import { PageHeader, Panel, Pill, SectionTitle } from "@/components/ui";
import { api, type SystemStatus } from "@/lib/api";
import { dateTime, integer } from "@/lib/format";
import { intelGet, type ApiStatus } from "@/lib/intel";

import { checkYouTubeApi } from "../intel-actions";

const STATE_LABEL: Record<string, string> = {
  demo: "Demonstração",
  live_restricted: "Dados reais, cálculos bloqueados",
  live_approved: "Dados reais, cálculos liberados",
};
const JOB_LABEL: Record<string, string> = {
  snapshots: "Snapshots de views", discover_videos: "Novos vídeos de canais monitorados", refresh_channels: "Atualização de canais",
  own_analytics: "Analytics dos meus canais", retention: "Retenção de dados",
};
const JOB_STATUS: Record<string, string> = { ok: "Concluída", erro: "Falhou", sem_cota: "Sem cota" };

function YouTubeConnection({ status }: { status: ApiStatus }) {
  const last = status.last_check;
  return (
    <Panel className="p-5 lg:col-span-2">
      <div className="flex flex-wrap items-center gap-2">
        <SectionTitle>Conexão com a YouTube Data API</SectionTitle>
        {status.target === "simulada"
          ? <Pill tone="warn">API simulada de teste</Pill>
          : status.validation_state === "validada" ? <Pill tone="good">Consulta real confirmada</Pill> : <Pill tone="warn">Validação real pendente</Pill>}
      </div>
      {status.last_real_validation
        ? <p className="mt-2 text-sm text-ink-2">Última consulta real bem-sucedida: {dateTime(status.last_real_validation.checked_at)}.</p>
        : <p className="mt-2 text-sm text-ink-2">Nenhuma consulta com dados reais foi concluída neste computador.</p>}
      {status.key_configured ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ActionForm action={checkYouTubeApi} submit="Testar conexão" pending="Testando..." tone="quiet" doneMessage="Teste concluído." />
          <ActionForm action={checkYouTubeApi} submit="Testar com uma busca" pending="Testando..." tone="quiet" hidden={{ with_search: "1" }} doneMessage="Teste concluído." />
          <span className="text-[0.8125rem] text-ink-3">O primeiro usa 1 unidade. O segundo usa 2 unidades e 1 das 100 buscas do dia.</span>
        </div>
      ) : (
        <div className="mt-3">
          <Notice tone="warn" title={status.no_key.title}>{status.no_key.action}</Notice>
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-ink-2">{status.setup_steps.map((step) => <li key={step}>{step}</li>)}</ol>
          <p className="mt-2 text-[0.8125rem] text-ink-3">Guia completo em <code>{status.setup_doc}</code>.</p>
        </div>
      )}
      {last && (
        <div className="mt-3">
          <Notice tone={last.ok ? "info" : "bad"} title={`${last.title}, em ${dateTime(last.checked_at)}`}>
            {last.message} {last.action}
            {last.details.steps && last.details.steps.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-[0.8125rem]">
                {last.details.steps.map((step) => <li key={step.method}><code>{step.method}</code>: {step.items} {step.items === 1 ? "item" : "itens"} com formato válido.</li>)}
              </ul>
            )}
          </Notice>
        </div>
      )}
    </Panel>
  );
}

function Check({ ok, label, missing }: { ok: boolean; label: string; missing: string }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{label}</span>
      {ok ? <Pill tone="good">Configurado</Pill> : <Pill>{missing}</Pill>}
    </li>
  );
}

export default async function System() {
  const [data, youtube] = await Promise.all([api<SystemStatus>("/api/system"), intelGet<ApiStatus>("/api-status")]);
  const approvalNeeded = data.policy.state !== "live_approved";
  return (
    <>
      <PageHeader title="Sistema e cotas" intro="Estado do aplicativo, credenciais, consumo de cota e tarefas de coleta." />
      <div className="grid gap-4 lg:grid-cols-2">
        <YouTubeConnection status={youtube} />
        <Panel className="p-5">
          <div className="flex flex-wrap items-center gap-2"><SectionTitle>Política da API</SectionTitle><Pill tone={data.policy.derived_allowed ? "good" : "bad"}>{STATE_LABEL[data.policy.state]}</Pill></div>
          <p className="mt-2 text-sm text-ink-2">{data.policy.description}</p>
          <dl className="mt-3 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
            <dt className="text-ink-2">Retenção de estatísticas</dt><dd className="text-right">{data.policy.stats_retention}</dd>
            <dt className="text-ink-2">Retenção de títulos e descrições</dt><dd className="text-right">{data.policy.text_retention_days} dias, com atualização</dd>
          </dl>
          {approvalNeeded && (
            <div className="mt-4 border-t border-line pt-3 text-sm leading-relaxed text-ink-2">
              <p className="font-medium text-ink">Para calcular scores e VPH com dados reais</p>
              <ol className="mt-1 list-decimal space-y-1 pl-4">
                <li>Leia a <a className="text-cobalt underline" href="https://developers.google.com/youtube/terms/derived-metrics-policy" target="_blank" rel="noreferrer noopener">política de métricas derivadas</a>.</li>
                <li>Envie o <a className="text-cobalt underline" href="https://support.google.com/youtube/contact/yt_api_form" target="_blank" rel="noreferrer noopener">pedido de extensão de cota</a>, com o caso de uso de análise e relatórios, e passe pela auditoria de conformidade.</li>
                <li>Com a aprovação em mãos, preencha <code>backend/config/compliance.toml</code>. O aplicativo não consegue confirmar a aprovação com o Google.</li>
              </ol>
              {data.mode === "live" && data.policy.problems.length > 0 && (
                <>
                  <p className="mt-3 font-medium text-ink">O que ainda falta no registro</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">{data.policy.problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>
                </>
              )}
              {data.policy.legacy_env_ignored && <p className="mt-3 text-warn">A variável YTI_DERIVED_METRICS_APPROVAL_REF foi ignorada: ela não autoriza mais nada.</p>}
            </div>
          )}
        </Panel>
        <Panel className="p-5">
          <SectionTitle>Credenciais e integrações</SectionTitle>
          <ul className="mt-2 divide-y divide-line">
            <Check ok={data.credentials.youtube_api_key} label="Chave da YouTube Data API" missing="Não configurada" />
            <Check ok={data.credentials.oauth_client} label="Cliente OAuth (meus canais)" missing="Não configurado" />
            <Check ok={data.ai.provider !== "none"} label={data.ai.provider !== "none" ? `IA: ${data.ai.provider}, ${data.ai.model}` : "Provedor de IA"} missing="Sem IA" />
            <Check ok={data.vidiq.enabled} label="vidIQ MCP (opcional)" missing="Desligado" />
          </ul>
          <p className="mt-3 text-sm text-ink-2">{integer(data.credentials.own_channels_authorized)} canais próprios autorizados. Valores das credenciais nunca aparecem aqui.</p>
        </Panel>

        <Panel className="p-5">
          <SectionTitle>Cota de hoje</SectionTitle>
          <p className="mt-0.5 text-sm text-ink-2">Dia de cota do YouTube: {data.quota[0]?.quota_day}, virada à meia-noite do Pacífico. Limites locais, abaixo dos do Google.</p>
          <ul className="mt-3 space-y-3">
            {data.quota.map((bucket) => {
              const share = bucket.limit ? Math.min(100, (bucket.used / bucket.limit) * 100) : 0;
              return (
                <li key={bucket.bucket}>
                  <div className="flex justify-between gap-3 text-sm"><span>{bucket.label}</span><span className="shrink-0">{integer(bucket.used)} de {integer(bucket.limit)}</span></div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-page"><div className="h-full rounded-full bg-cobalt" style={{ width: `${Math.max(share, bucket.used ? 1 : 0)}%` }} /></div>
                  <p className="mt-0.5 text-[0.8125rem] text-ink-3">
                    {bucket.google_limit !== null ? `Limite do Google: ${integer(bucket.google_limit)} por dia.` : "Limite do Google não informado."}
                    {!bucket.verified && " Não confirmado na tabela oficial de custos."}
                    {bucket.note && ` ${bucket.note}`}
                  </p>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-sm text-ink-2">
            Base local: {integer(data.counts.channels)} canais, {integer(data.counts.videos)} vídeos, {integer(data.counts.snapshots)} snapshots, {integer(data.counts.searches)} buscas, {integer(data.counts.ai_generations)} gerações.
          </p>
        </Panel>

        <Panel className="p-5">
          <SectionTitle>Tarefas periódicas</SectionTitle>
          {data.mode === "demo" && <p className="mt-0.5 text-sm text-ink-2">No modo demonstração nada é coletado.</p>}
          <ul className="mt-2 divide-y divide-line">
            {data.jobs.map((job) => (
              <li key={job.name} className="py-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span>{JOB_LABEL[job.name] ?? job.name}</span>
                  <span className="text-ink-2">{job.last_status ? JOB_STATUS[job.last_status] ?? job.last_status : "Nunca rodou"}</span>
                </div>
                <div className="text-[0.8125rem] text-ink-3">A cada {integer(job.interval_minutes)} min. Última: {dateTime(job.last_run_at)}.</div>
                {job.last_error && <div className="mt-0.5 text-[0.8125rem] text-bad">{job.last_error}</div>}
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
