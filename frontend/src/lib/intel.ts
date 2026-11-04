import { API_URL, authHeaders, type WriteResult } from "@/lib/studio";
import type { Metric, VideoRow } from "@/lib/api";

export interface IntelContext {
  mode: "demo" | "live"; derived_allowed: boolean; policy_state: string; has_api_key: boolean;
  channels: { id: string; name: string; is_demo: boolean; language: string; niche: string }[];
  other_channels: { id: string; name: string; is_demo: boolean }[];
}

export interface Run {
  id: string; managed_channel_id: string | null; kind: string; kind_label: string; query: string;
  filters: { language: string | null; country: string | null; days: number | null; format: string | null; order: string; max_subscribers: number | null };
  data_origin: "demo" | "youtube"; fictional: boolean; total_results_approx: number | null; result_count: number; saved_name: string | null; executed_at: string;
}
export interface Page<T> { total: number; limit: number; offset: number; items: T[] }
export interface ChannelResult {
  id: string; title: string; handle: string | null; country: string | null; language: string | null; thumbnail_url: string | null;
  source_url: string | null; is_own: boolean; monitored: boolean; subscribers: Metric; videos_collected: number; last_published_at: string | null;
}
export interface RunView {
  run: Run; videos: VideoRow[]; channels: ChannelResult[]; removed: number; total: number; limit: number; offset: number;
  derived_allowed: boolean; filter_notes: string[]; search_volume: Metric;
}
export interface CompareItem { type: string; id: string; rank: number; rank_b?: number; url: string | null; title: string | null; channel: string | null }
export interface RunComparison { a: Run; b: Run; both: CompareItem[]; only_a: CompareItem[]; only_b: CompareItem[] }
export interface GrowingTopics { blocked: boolean; reason?: string; origin_note?: string; items: { term: string; format: string; videos: number; channels: number; accelerating: number }[] }

export interface KeywordIndexRow {
  format: string; status: string; sample_size: number; distinct_channels: number; index: Metric; attention: Metric; competition: Metric;
  relevance: Metric; confidence: Metric; justification: string[];
}
export interface KeywordAnalysis {
  term: string; language: string; channel_id: string | null; fictional: boolean; is_favorite: boolean;
  volume: { measured: Metric; provider_estimate: Metric };
  index: { blocked: boolean; reason: string | null; note: string; origin_note?: string; formats: KeywordIndexRow[] };
  sample: { total: number; limit: number; offset: number; videos: VideoRow[]; note: string };
  last_youtube_search_at: string | null;
  related: { from_titles: { term: string; videos: number }[]; from_titles_blocked: boolean; from_titles_reason: string | null; from_profile: { term: string; reason: string }[] };
  variations: { items: { term: string; rule: string }[]; note: string };
  questions: { from_model: string[]; model_note: string; from_titles: { id: string; title: string; channel_title: string; source_url: string | null }[] };
  rising: GrowingTopics;
}
export interface KeywordHistoryItem { id: number; managed_channel_id: string | null; term: string; language: string | null; data_origin: string; looked_up_at: string }
export interface Favorite { term: string; note: string; created_at: string }
export interface OwnTerms {
  available: boolean; reason: string | null; fictional?: boolean; source?: string;
  items: { term: string; views: Metric; minutes_watched: Metric; period_start: string; period_end: string }[];
}
export interface ForYou {
  channel_id: string; items: { term: string; reason: string; origin: string }[]; trends_blocked: boolean; trends_reason: string | null; uses_research: boolean; fictional: boolean;
}

export interface ExplorerResult {
  total: number; limit: number; offset: number; items: VideoRow[]; sort: string; notes: string[]; derived_allowed: boolean;
  blocked_reason: string | null; origin_note: string | null; fictional: boolean;
}
export interface StudyItem {
  video: VideoRow; note: string; origin: string; added_at: string;
  snapshots: { count: number; first_at: string | null; first_views: number | null; last_at: string | null; last_views: number | null };
}
export interface TitleFeatures { characters: number; words: number; has_number: boolean; is_question: boolean; approach: string; approach_label: string; caps_words: number }
export interface StudyComparison {
  columns: { video: VideoRow; note: string; features: TitleFeatures | null }[]; features_blocked: boolean; reason: string | null; shared_words: string[]; note: string;
}
export interface CompetitorSummary {
  id: string; name: string; notes: string; youtube_ref: string | null; research_id: string | null; linked: boolean; videos_collected: number;
  last_published_at: string | null; recent_days_uploads: string[];
  channel: { title: string; handle: string | null; country: string | null; source_url: string | null; subscribers: Metric; text_refreshed_at: string } | null;
}
export interface EditorialColumns { sample_size: number; uploads_per_week: number | null; median_duration_seconds: number | null; question_title_share: number | null; top_weekday: string | null }
export interface CompetitorOverview {
  channel: { id: string; name: string; is_demo: boolean }; usable: boolean; items: CompetitorSummary[];
  comparison: { name: string; research_id: string; formats: Record<string, EditorialColumns> }[] | null;
  comparison_blocked: boolean; reason: string | null; origin_note: string | null; fictional: boolean; has_api_key: boolean; mode: string; demo_options: { id: string; title: string }[];
}
export interface EditorialProfile extends EditorialColumns { median_gap_days: number | null; median_title_words: number | null; number_title_share: number | null; top_terms: [string, number][] }
export interface CompetitorDetail {
  competitor: { id: string; name: string; notes: string; youtube_ref: string | null }; linked: boolean; usable: boolean; summary: CompetitorSummary | null; fictional?: boolean;
  videos?: { total: number; limit: number; offset: number; items: VideoRow[] };
  calendar?: { day: string; videos: { id: string; title: string; format: string }[] }[]; calendar_days?: number;
  editorial?: Record<string, EditorialProfile> | null; title_patterns?: { pattern: string; videos: number }[]; recurring_subjects?: { term: string; videos: number }[];
  patterns_blocked?: boolean; reason?: string | null; origin_note?: string | null; study_ids?: string[];
}
export interface EditorialOpportunity { id: string; title: string; note: string; video_id: string | null; video_title: string | null; source_url: string | null; status: string; recommendation_id: string | null; created_at: string }

export async function intelGet<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) if (value) query.set(key, value);
  const suffix = query.size ? `?${query}` : "";
  const response = await fetch(`${API_URL}/api/intel${path}${suffix}`, { cache: "no-store" });
  if (!response.ok) {
    const error = new Error(`A API retornou HTTP ${response.status} em ${path}`) as Error & { status?: number; message_api?: string };
    error.status = response.status;
    const body = await response.json().catch(() => null);
    error.message_api = body?.error?.message;
    throw error;
  }
  return response.json() as Promise<T>;
}

export async function intelGetOrNull<T>(path: string, params?: Record<string, string | undefined>): Promise<T | null> {
  try {
    return await intelGet<T>(path, params);
  } catch (error) {
    if ((error as { status?: number }).status === 404) return null;
    throw error;
  }
}

export async function intelWrite(path: string, body?: unknown): Promise<WriteResult> {
  try {
    const response = await fetch(`${API_URL}/api/intel${path}`, {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(body ?? {}),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) return { ok: true, data };
    return { ok: false, error: data?.error?.message ?? `A API retornou HTTP ${response.status}.` };
  } catch {
    return { ok: false, error: "A API local não respondeu. Confira se o backend está rodando." };
  }
}

/** Repassa um arquivo da API ao navegador sem expor a API local. */
export async function intelFile(path: string, params?: Record<string, string | undefined>): Promise<Response> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) if (value) query.set(key, value);
  const suffix = query.size ? `?${query}` : "";
  const upstream = await fetch(`${API_URL}/api/intel${path}${suffix}`, { cache: "no-store" });
  if (!upstream.ok) return new Response("Arquivo não encontrado.", { status: upstream.status === 404 ? 404 : 502 });
  const headers = new Headers({ "X-Content-Type-Options": "nosniff" });
  for (const name of ["content-type", "content-disposition", "content-length", "cache-control"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: 200, headers });
}

export const LANGUAGES = [{ value: "pt", label: "Português" }, { value: "en", label: "Inglês" }, { value: "es", label: "Espanhol" }];
export const PERIODS = [{ value: "1", label: "Último dia" }, { value: "7", label: "Última semana" }, { value: "30", label: "Último mês" }, { value: "90", label: "Últimos 3 meses" }, { value: "365", label: "Último ano" }];
