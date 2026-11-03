const API_URL = process.env.YTI_API_URL ?? "http://127.0.0.1:8000";

export interface Automation { auto_research: string; auto_briefing: string; auto_production: string; auto_package: string; publishing: string }
export interface AuthStatus { state: string; label: string; detail: string; checked_at?: string }
export interface ScheduledItem { scheduled_on: string; title: string; format: string }

export interface Channel {
  id: string; name: string; handle: string | null; youtube_channel_id: string | null; is_demo: boolean;
  niche: string; language: string; country: string; audience: string; positioning: string; tone: string;
  keywords: string[]; avoid: string[]; topic_backlog: string[]; formats: string[];
  long_target_seconds: number; short_target_seconds: number; cadence_per_week: number | null;
  automation: Automation; created_at: string; updated_at: string;
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
}

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

export interface JobDetail {
  job: Job;
  events: { at: string; level: string; kind: string; message: string }[];
  artifacts: { id: string; kind: string; path: string; label: string; size_bytes: number | null; sha256: string | null; simulated: number }[];
  package: { id: string; title: string; description: string; tags: string[]; checklist: string[]; state: string; created_at: string } | null;
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
      method, cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
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
  package_ready: { label: "Pronto para sua revisão", tone: "good" },
  cancelled: { label: "Cancelada", tone: "neutral" },
};

export const CALENDAR_STATUS: Record<string, string> = {
  planejado: "Planejado", em_producao: "Em produção", pronto_para_revisao: "Pronto para revisão",
  publicado_manualmente: "Publicado por você", cancelado: "Cancelado",
};

export const LANGUAGE_LABEL: Record<string, string> = { pt: "Português", es: "Espanhol", en: "Inglês" };
