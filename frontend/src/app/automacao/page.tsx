import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { ChannelSelect, Notice, Pagination, RealChannelsNote } from "@/components/intel";
import { Empty, PageHeader, Panel, Pill, SectionTitle, str } from "@/components/ui";
import { dateTime, FORMAT_LABEL } from "@/lib/format";
import { intelGet, LANGUAGES, PERIODS, type AutomationGate, type AutomationOverview, type IntelContext, type ResearchSchedule } from "@/lib/intel";

import { approveAutomation, createSchedule, deleteSchedule, resumeAutomation, revokeAutomation, tickAutomation, updateSchedule } from "../intel-actions";

const STATE: Record<string, { label: string; tone: "good" | "warn" | "neutral" | "bad" }> = {
  demo: { label: "Só dados fictícios", tone: "warn" }, sem_chave: { label: "Desligado: sem chave", tone: "neutral" }, sem_validacao: { label: "Desligado: falta consulta real", tone: "neutral" },
  aguardando_aprovacao: { label: "Desligado: falta sua aprovação", tone: "neutral" }, pausado: { label: "Pausado", tone: "bad" }, limite_do_dia: { label: "Limite do dia atingido", tone: "warn" }, ligado: { label: "Ligado", tone: "good" },
};
const EVENT: Record<string, string> = { ok_api: "Pesquisou", ok_cache: "Usou o cache", duplicada: "Duplicada, ignorada", erro: "Falhou", sem_cota: "Sem cota", erro_chave: "Problema na chave" };

function Status({ gate, overview }: { gate: AutomationGate; overview: AutomationOverview }) {
  const style = STATE[gate.state] ?? STATE.sem_chave;
  const live = gate.mode === "live";
  const showApprove = live && (gate.state === "aguardando_aprovacao" || gate.real_enabled);
  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-center gap-2"><SectionTitle>Situação</SectionTitle><Pill tone={style.tone}>{style.label}</Pill>{gate.target === "simulada" && <Pill tone="warn">API simulada de teste</Pill>}</div>
      <p className="mt-2 text-sm text-ink-2">{gate.reason}</p>
      {gate.state === "sem_chave" || gate.state === "sem_validacao" ? <p className="mt-1 text-sm"><Link className="text-cobalt underline underline-offset-2" href="/sistema">Abrir Sistema e cotas</Link></p> : null}
      {live && (
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
          <dt className="text-ink-2">Limite aprovado</dt><dd className="text-right">{gate.real_enabled ? `${gate.max_searches_per_day} buscas por dia` : "Nenhum"}</dd>
          <dt className="text-ink-2">Buscas automáticas hoje</dt><dd className="text-right">{gate.used_today}</dd>
          <dt className="text-ink-2">Todas as buscas hoje</dt><dd className="text-right">{overview.quota.search_used} de {overview.quota.search_limit}</dd>
          {gate.approved_at && <><dt className="text-ink-2">Aprovado em</dt><dd className="text-right">{dateTime(gate.approved_at)}</dd></>}
        </dl>
      )}
      <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-3">
        {showApprove && (
          <ActionForm action={approveAutomation} submit={gate.real_enabled ? "Alterar limite" : "Aprovar limite e ligar"} tone={gate.real_enabled ? "quiet" : "primary"} className="flex flex-wrap items-end gap-2" doneMessage="Limite salvo.">
            <label className="text-sm text-ink-2">Buscas automáticas por dia, no máximo<input name="max_searches_per_day" type="number" required min={1} max={overview.max_approvable} defaultValue={gate.max_searches_per_day || 5} className="field mt-1 block w-28" /></label>
          </ActionForm>
        )}
        {gate.real_enabled && <ActionForm action={revokeAutomation} submit="Desligar" tone="danger" />}
        {gate.state === "pausado" && <ActionForm action={resumeAutomation} submit="Retomar" tone="quiet" />}
        {gate.can_run && <ActionForm action={tickAutomation} submit={`Rodar as vencidas agora (${overview.due_now})`} pending="Rodando..." tone="quiet" doneMessage="Rodada concluída. Veja o histórico." />}
      </div>
      <p className="mt-3 text-[0.8125rem] leading-relaxed text-ink-3">
        Nada roda sozinho enquanto você não iniciar o comando <code>research-tick</code>, descrito em <code>docs/POLITICA_DE_DADOS.md</code>. Falta de cota pausa tudo até a virada do dia de cota. Problema na chave pausa até você retomar. Três falhas seguidas pausam só aquele agendamento.
      </p>
    </Panel>
  );
}

function ScheduleRow({ item, channels, intervals }: { item: ResearchSchedule; channels: Map<string, string>; intervals: AutomationOverview["intervals"] }) {
  const hidden = { channel_id: item.managed_channel_id, schedule_id: item.id };
  const filters = [item.filters.niche, item.filters.subniche, item.filters.language, item.filters.country, item.filters.days && `${item.filters.days} dias`, item.filters.format && FORMAT_LABEL[item.filters.format]].filter(Boolean).join(", ");
  return (
    <li className="p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{item.query}</span>
        <Pill tone={item.enabled ? "good" : "neutral"}>{item.enabled ? "Ativo" : "Pausado"}</Pill>
        {item.last_status && <Pill tone={item.last_status === "erro" || item.last_status === "erro_chave" ? "bad" : "neutral"}>{EVENT[item.last_status] ?? item.last_status}</Pill>}
      </div>
      <p className="mt-0.5 text-[0.8125rem] text-ink-3">{channels.get(item.managed_channel_id) ?? "Canal indisponível neste modo"}. {item.kind_label}{filters && `, ${filters}`}. {item.interval_label}. Próxima: {dateTime(item.next_run_at)}.{item.last_run_at && ` Última: ${dateTime(item.last_run_at)}.`}</p>
      {item.paused_reason && <p className="mt-0.5 text-[0.8125rem] text-ink-2">{item.paused_reason}</p>}
      {item.last_error && <p className="mt-0.5 text-[0.8125rem] text-bad">{item.last_error}</p>}
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <ActionForm action={updateSchedule} submit="Mudar" tone="quiet" hidden={hidden} className="flex flex-wrap items-end gap-2">
          <label className="text-[0.8125rem] text-ink-2">Periodicidade<select name="interval_hours" defaultValue={item.interval_hours} className="field mt-1 block">{intervals.map((option) => <option key={option.hours} value={option.hours}>{option.label}</option>)}</select></label>
        </ActionForm>
        <ActionForm action={updateSchedule} submit={item.enabled ? "Pausar" : "Retomar"} tone="quiet" hidden={{ ...hidden, enabled: item.enabled ? "0" : "1" }} />
        <ActionForm action={deleteSchedule} submit="Remover" tone="danger" hidden={hidden} />
      </div>
    </li>
  );
}

export default async function Automation({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const offset = Number(str(params.inicio)) || 0;
  const [context, data] = await Promise.all([intelGet<IntelContext>("/context"), intelGet<AutomationOverview>("/automation", { offset: String(offset) })]);
  const names = new Map(context.channels.map((c) => [c.id, c.name]));
  return (
    <>
      <PageHeader title="Pesquisas agendadas" intro="Repita pesquisas por canal, sem buscas duplicadas e dentro dos limites que você aprovar. Com dados reais, fica desligado até você decidir." />
      <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
        <div className="min-w-0 space-y-4">
          <Status gate={data.gate} overview={data} />
          {data.gate.state === "pausado" && data.gate.paused_until && <Notice tone="warn">Volta sozinho em {dateTime(data.gate.paused_until)}.</Notice>}
          <section>
            <SectionTitle>Agendamentos ({data.schedules.length})</SectionTitle>
            <Panel className="mt-2">
              {data.schedules.length ? <ul className="divide-y divide-line">{data.schedules.map((item) => <ScheduleRow key={item.id} item={item} channels={names} intervals={data.intervals} />)}</ul>
                : <Empty title="Nenhuma pesquisa agendada.">Crie uma ao lado ou use Agendar nos resultados de uma descoberta.</Empty>}
            </Panel>
          </section>
          <section>
            <SectionTitle>Histórico</SectionTitle>
            <Panel className="mt-2">
              {data.events.items.length ? (
                <div className="overflow-x-auto">
                  <table className="data-table w-full">
                    <thead><tr><th>Quando</th><th>Pesquisa</th><th>Resultado</th><th>Detalhe</th></tr></thead>
                    <tbody>
                      {data.events.items.map((event) => (
                        <tr key={event.id}>
                          <td className="whitespace-nowrap">{dateTime(event.at)}</td>
                          <td>{event.run_id ? <Link className="text-cobalt underline underline-offset-2" href={`/pesquisa/${event.run_id}`}>{event.query}</Link> : event.query}</td>
                          <td className="whitespace-nowrap">{EVENT[event.status] ?? event.status}</td>
                          <td className="text-[0.8125rem] text-ink-3">{event.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <Empty title="Nenhuma rodada ainda." />}
              <Pagination total={data.events.total} limit={data.events.limit} offset={data.events.offset} href={(next) => `/automacao?inicio=${next}`} />
            </Panel>
          </section>
        </div>
        <Panel className="h-fit p-4">
          <SectionTitle>Nova pesquisa agendada</SectionTitle>
          {context.channels.length ? (
            <ActionForm action={createSchedule} submit="Agendar" tone="quiet" className="mt-3 space-y-2" doneMessage="Agendada." resetOnSuccess>
              <label className="block text-[0.8125rem] text-ink-2">Canal<div className="mt-1"><ChannelSelect context={context} emptyLabel="Escolha" /></div></label>
              <label className="block text-[0.8125rem] text-ink-2">Palavra ou tema<input name="query" required minLength={2} maxLength={120} className="field mt-1 w-full" /></label>
              <label className="block text-[0.8125rem] text-ink-2">O que procurar<select name="kind" defaultValue="recent" className="field mt-1 w-full"><option value="recent">Vídeos recentes</option><option value="videos">Vídeos por tema</option><option value="channels">Canais por nicho</option><option value="emerging">Canais pequenos em atividade</option></select></label>
              <label className="block text-[0.8125rem] text-ink-2">Periodicidade<select name="interval_hours" defaultValue="168" className="field mt-1 w-full">{data.intervals.map((option) => <option key={option.hours} value={option.hours}>{option.label}</option>)}</select></label>
              <label className="block text-[0.8125rem] text-ink-2">Idioma<select name="language" className="field mt-1 w-full"><option value="">Qualquer</option>{LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select></label>
              <label className="block text-[0.8125rem] text-ink-2">País (sigla)<input name="country" maxLength={2} className="field mt-1 w-full uppercase" /></label>
              <label className="block text-[0.8125rem] text-ink-2">Período<select name="days" className="field mt-1 mb-2 w-full"><option value="">Padrão do tipo</option>{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></label>
            </ActionForm>
          ) : <p className="mt-2 text-sm text-ink-3">Nenhum canal pode receber os dados do modo atual.</p>}
          <p className="mt-3 text-[0.8125rem] text-ink-3">Cada agendamento real gasta 1 das 100 buscas do dia por rodada. Até {data.max_per_channel} por canal.</p>
          <div className="mt-2"><RealChannelsNote context={context} /></div>
        </Panel>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
