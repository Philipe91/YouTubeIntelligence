export const API_URL = process.env.YTI_API_URL ?? "http://127.0.0.1:8000";

export interface Automation { auto_research: string; auto_briefing: string; auto_production: string; auto_package: string; publishing: string }
export interface AuthStatus { state: string; label: string; detail: string; checked_at?: string }
export interface ScheduledItem { scheduled_on: string; title: string; format: string }

export interface Channel {
  id: string; name: string; handle: string | null; youtube_channel_id: string | null; is_demo: boolean;
  niche: string; language: string; country: string; audience: string; positioning: string; tone: string;
  keywords: string[]; avoid: string[]; topic_backlog: string[]; formats: string[];
  long_target_seconds: number; short_target_seconds: number; cadence_per_week: number | null;
  automation: Automation; pipeline_profile: string; created_at: string; updated_at: string;
}

export interface ChannelSummary extends Channel {
  youtube_auth: AuthStatus; open_recommendations: number; active_jobs: number; awaiting_authorization: number;
  packages_ready: number; history_count: number; next_scheduled: ScheduledItem | null;
}

export interface ClaudeStatus {
  cli_found: boolean; mcp_configured: boolean; contract_version: string;
  recent_agents: { agent_id: string; channel_id?: string; last_operation: string; last_seen_at: string }[];
  simulated_only: boolean | null;
}

export interface Job {
  id: string; channel_id: string; channel_name?: string; channel_is_demo?: number; recommendation_id: string | null;
  title: string; format: string; simulated: boolean; state: string; progress: number; step: string; attempts: number;
  max_attempts: number; lease_owner: string | null; lease_expires_at: string | null; requested_by: string;
  authorized_by: string | null; authorized_at: string | null; last_error: string | null; created_at: string; updated_at: string;
  briefing_id: string | null; state_label: string; review_status: string | null; review_note: string | null; reviewed_at: string | null;
}

export interface Stage { stage: string; label: string; status: "pendente" | "em_andamento" | "concluida" | "falhou"; detail: string; done: number | null; total: number | null; started_at: string | null; ended_at: string | null }
export interface ScriptScene { texto: string; m: string; set?: string; quem?: string; acao?: string; titulo?: string; valor?: string; hora?: string }
export interface ProductionView {
  script: { resumo: string; cenas: ScriptScene[]; fontes: { label: string; url?: string }[]; fatos_a_conferir?: string[]; submitted_by: string; submitted_at: string } | null;
  stages: Stage[];
  validation: { ok: boolean; problems: string[]; width: number | null; height: number | null; duration_seconds: number; video_codec: string | null; audio_codec: string | null; size_bytes: number; validated_by: string; validated_at: string } | null;
}

export interface Attempt { job_id?: string; title?: string; number: number; agent_id: string; started_at: string; ended_at: string | null; outcome: string; error: string | null }

export interface BriefingPayload {
  chosen_title: string; subject: string; justification: string; hook: string; thumbnail_idea: string; format: string; duration_seconds: number;
  target_audience: string; language: string; tone: string; outline: { section: string; target_seconds: number }[];
  facts_to_verify: string[]; fictional: boolean; constraints: string[];
}

export interface Briefing { id: string; chosen_title: string; approved_by: string; approved_at: string; updated_at: string; payload: BriefingPayload }

export interface CockpitArtifact { id: string; job_id: string; job_title: string; kind: string; label: string; path: string; size_bytes: number | null; sha256: string | null; simulated: number; downloadable: boolean; created_at: string }

export interface Alert { id: number; job_id: string; job_title: string; at: string; level: string; message: string }

export interface Cockpit {
  current_job: Job | null; attempts: Attempt[]; artifacts: CockpitArtifact[]; alerts: Alert[]; jobs_total: number;
  next_recommendation: Recommendation | null; briefing: Briefing | null; upcoming: CalendarEntry[];
  production: ProductionView | null; current_briefing: BriefingPayload | null; real_adapter: string | null;
}

export interface PipelineStage { stage: string; label: string; adapter: string; can_execute: boolean; simulated: boolean; project: string | null; project_found: boolean | null; command_preview: string | null; heavy: boolean; requires: string[]; notes: string | null; blocked_reason: string | null }
export interface PipelineInfo { plan: { profile: string; label: string; stages: PipelineStage[]; ready_to_execute: boolean; real_execution_enabled: boolean }; options: { id: string; label: string }[] }

export interface CalendarEntry {
  id: string; channel_id: string; channel_name?: string; channel_is_demo?: number; scheduled_on: string; title: string;
  format: string; status: string; recommendation_id: string | null; job_id: string | null; notes: string;
}

export interface StudioOverview {
  channels: ChannelSummary[]; jobs: Job[]; upcoming: CalendarEntry[]; claude: ClaudeStatus; mode: string;
  policy: { state: string; derived_allowed: boolean };
}

export interface Competitor { id: string; name: string; youtube_ref: string | null; notes: string }
export interface HistoryItem { id: string; title: string; format: string; published_on: string; url: string | null; views: number | null; result_notes: string; source: string }

export interface ChannelDetail extends ChannelSummary {
  competitors: Competitor[]; history: HistoryItem[]; claude: ClaudeStatus; mode: string;
  policy: { state: string; derived_allowed: boolean };
}

export interface Source { kind: string; label: string; url: string | null; fictional: boolean; verified?: boolean }

export interface Recommendation {
  id: string; channel_id: string; subject: string; justification: string; sources: Source[]; titles: string[];
  thumbnail_idea: string; hook: string; format: string; duration_seconds: number; target_audience: string;
  editorial_priority: string; facts_to_verify: string[]; data_basis: string; origin: string; status: string; created_at: string; updated_at: string;
}

export interface JobDetail extends ProductionView {
  job: Job;
  events: { at: string; level: string; kind: string; message: string }[];
  artifacts: { id: string; kind: string; path: string; label: string; size_bytes: number | null; sha256: string | null; simulated: number }[];
  attempt_history: Attempt[];
  briefing: BriefingPayload | null;
  package: { id: string; title: string; description: string; tags: string[]; checklist: string[]; state: string; created_at: string } | null;
}

/** Só roda no servidor do Next: o token nunca chega ao navegador. */
export function authHeaders(): Record<string, string> {
  return { "X-YTI-Token": process.env.YTI_API_TOKEN ?? "" };
}

export async function studioGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) if (value) query.set(key, value);
  const suffix = query.size ? `?${query}` : "";
  const response = await fetch(`${API_URL}/api/studio${path}${suffix}`, { cache: "no-store" });
  if (!response.ok) {
    const error = new Error(`A API retornou HTTP ${response.status} em ${path}`) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}

export async function studioGetOrNull<T>(path: string, params?: Record<string, string | undefined>): Promise<T | null> {
  try {
    return await studioGet<T>(path, params);
  } catch (error) {
    if ((error as { status?: number }).status === 404) return null;
    throw error;
  }
}

export type WriteResult = { ok: true; data: Record<string, unknown> } | { ok: false; error: string };

export async function studioWrite(method: "POST" | "PATCH", path: string, body?: unknown): Promise<WriteResult> {
  try {
    const response = await fetch(`${API_URL}/api/studio${path}`, {
      method, cache: "no-store", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body ?? {}),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message ?? `A API retornou HTTP ${response.status}.` };
  } catch {
    return { ok: false, error: "A API local não respondeu. Confira se o backend está rodando." };
  }
}

export const JOB_STATE: Record<string, { label: string; tone: "good" | "warn" | "bad" | "info" | "ochre" | "neutral" }> = {
  awaiting_authorization: { label: "Aguardando sua autorização", tone: "warn" },
  authorized: { label: "Na fila", tone: "info" },
  running: { label: "Em execução", tone: "info" },
  failed: { label: "Falhou", tone: "bad" },
  delivered: { label: "Arquivos entregues", tone: "ochre" },
  package_ready: { label: "PRONTO PARA REVISÃO", tone: "good" },
  cancelled: { label: "Cancelada", tone: "neutral" },
};

export const ATTEMPT_OUTCOME: Record<string, { label: string; tone: "good" | "warn" | "bad" | "info" | "neutral" }> = {
  em_andamento: { label: "Em andamento", tone: "info" }, entregue: { label: "Entregue", tone: "good" }, falhou: { label: "Falhou", tone: "bad" },
  prazo_vencido: { label: "Agente parou de responder", tone: "warn" }, cancelada: { label: "Cancelada", tone: "neutral" },
};

export const CALENDAR_STATUS: Record<string, string> = {
  planejado: "Planejado", em_producao: "Em produção", pronto_para_revisao: "Pronto para revisão",
  publicado_manualmente: "Publicado por você", cancelado: "Cancelado",
};

export const LANGUAGE_LABEL: Record<string, string> = { pt: "Português", es: "Espanhol", en: "Inglês" };
