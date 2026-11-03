const API_URL = process.env.YTI_API_URL ?? "http://127.0.0.1:8000";

export type Kind = "measured" | "calculated" | "estimated" | "unavailable" | "blocked";

export interface Metric<T = number> {
  value: T | null;
  kind: Kind;
  source: string;
  reason: string | null;
  as_of: string | null;
}

export interface VideoRow {
  id: string;
  title: string;
  channel_id: string;
  channel_title: string;
  published_at: string;
  duration_seconds: number | null;
  language: string | null;
  country: string | null;
  thumbnail_url: string | null;
  format: string;
  format_label: Metric<string>;
  source_url: string | null;
  views: Metric;
  snapshot_count: number;
  age_hours: number | null;
  vph_observed: Metric;
  vph_average: Metric;
  idr: Metric;
  outlier: { status: string; band: string | null; confidence: string | null; sample_size: number; robust_z: number | null; warnings: string[] } | null;
  acceleration: { status: string; ratio: number | null; recent_vph: number | null; previous_vph: number | null } | null;
  derived_blocked: boolean;
}

export interface VideoDetail extends VideoRow {
  description: string | null;
  snapshots: { captured_at: string; views: number; age_hours: number }[];
  outlier_explanation: string | null;
  acceleration_explanation: string | null;
  intervals: { start: string; end: string; hours: number; delta_views: number; vph: number | null; flags: string[] }[];
  peer_curve: { age_hours: number; median_views: number; sample: number }[];
}

export interface OpportunityRow {
  topic: string;
  format: string;
  status: string;
  score: Metric;
  demand: Metric;
  competition: Metric;
  relevance: Metric;
  confidence: Metric;
  search_volume: Metric;
  sample_size: number;
  distinct_channels: number;
  median_views_per_day: number | null;
  median_subscribers: number | null;
  recent_share: number | null;
  total_results_approx: number | null;
  competition_parts: Record<string, number>;
  justification: string[];
  video_ids: string[];
}

export interface Idea {
  working_title: string;
  title_options: string[];
  hook: string;
  angle: string;
  brief: string;
  script_outline: { section: string; beats: string[] }[];
  evidence_refs: string[];
  facts_to_verify: string[];
}

export interface Generation {
  id: number;
  provider: string;
  model: string | null;
  is_ai: boolean;
  created_at: string;
  output: { ideas: Idea[]; limitations: string[] };
}

export interface OpportunityDetail extends OpportunityRow {
  blocked: boolean;
  reason?: string;
  videos: VideoRow[];
  generations: Generation[];
  origin_note: string;
}

export interface TrendTerm {
  term: string;
  format: string;
  videos: number;
  channels: number;
  accelerating: number;
  accelerating_share: number;
  recent_vph_sum: number;
  previous_vph_sum: number;
  velocity_ratio: number | null;
  video_ids: string[];
}

export interface Overview {
  blocked: boolean;
  reason?: string;
  origin_note?: string;
  top_opportunities: OpportunityRow[];
  rising: VideoRow[];
  outliers: VideoRow[];
  trends: TrendTerm[];
  recent?: VideoRow[];
  health: { videos: number; insufficient_sample: number; rising: number; outliers: number };
}

export interface ChannelRow {
  id: string;
  title: string;
  handle: string | null;
  country: string | null;
  language: string | null;
  is_own: boolean;
  monitored: boolean;
  niche: string | null;
  source_url: string | null;
  subscribers: Metric;
  formats: Record<string, { videos: number; median_views: number | null; outliers: number | null; scored: number | null }>;
  derived_blocked: boolean;
}

export interface EditorialProfile {
  format: string;
  sample_size: number;
  uploads_per_week: number | null;
  median_gap_days: number | null;
  median_duration_seconds: number | null;
  median_title_words: number | null;
  question_title_share: number | null;
  number_title_share: number | null;
  top_weekday: string | null;
  top_terms: [string, number][];
  overperforming_terms: { term: string; videos: number; median_idr: number; lift: number }[];
}

export interface ChannelDetail extends ChannelRow {
  editorial: Record<string, EditorialProfile> | null;
  editorial_note: string;
}

export interface CompareRow {
  channel_id: string;
  title: string;
  is_own: boolean;
  subscribers: Metric;
  sample_size: number;
  uploads_per_week: number | null;
  median_duration_seconds: number | null;
  median_views: number | null;
  outliers: number | null;
  scored: number | null;
  question_title_share: number | null;
  top_weekday: string | null;
}

export interface OwnChannel {
  id: string;
  title: string;
  source_url: string | null;
  days: number;
  as_of: string | null;
  has_analytics: boolean;
  formats: {
    content_type: string;
    format: string;
    views: Metric;
    minutes_watched: Metric;
    average_view_percentage: Metric;
    subscribers_net: Metric;
    ctr: Metric;
    daily: { day: string; views: number }[];
  }[];
}

export interface SystemStatus {
  mode: "demo" | "live";
  policy: { state: string; derived_allowed: boolean; stats_retention: string; text_retention_days: number; description: string; extended_storage: boolean; problems: string[]; record_status: string; legacy_env_ignored: boolean };
  credentials: { youtube_api_key: boolean; oauth_client: boolean; own_channels_authorized: number };
  ai: { provider: string; model: string | null };
  vidiq: { enabled: boolean; note: string; how_to_enable: string };
  quota: { bucket: string; label: string; used: number; limit: number; google_limit: number | null; verified: boolean; note: string | null; quota_day: string }[];
  jobs: { name: string; interval_minutes: number; enabled: number; last_run_at: string | null; last_status: string | null; last_error: string | null }[];
  counts: Record<string, number>;
  count_changes: { date: string; description: string }[];
  scoring: Record<string, Record<string, unknown>>;
}

export interface Filters {
  niches: { id: number; name: string }[];
  languages: string[];
  countries: string[];
  channels: { id: string; title: string }[];
}

export class ApiUnavailable extends Error {}

export async function api<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value) query.set(key, value);
  }
  const suffix = query.size ? `?${query}` : "";
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}${suffix}`, { cache: "no-store" });
  } catch {
    throw new ApiUnavailable("A API local não respondeu em " + API_URL);
  }
  if (!response.ok) {
    throw new Error(`A API retornou HTTP ${response.status} em ${path}`);
  }
  return response.json() as Promise<T>;
}

export async function apiOrNull<T>(path: string, params?: Record<string, string | undefined>): Promise<T | null> {
  try {
    return await api<T>(path, params);
  } catch (error) {
    if (error instanceof Error && error.message.includes("HTTP 404")) return null;
    throw error;
  }
}

export async function postGenerate(topic: string, format: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const response = await fetch(`${API_URL}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, format }),
      cache: "no-store",
    });
    if (response.ok) return { ok: true };
    const body = await response.json().catch(() => ({}));
    return { ok: false, error: body.detail ?? `HTTP ${response.status}` };
  } catch {
    return { ok: false, error: "A API local não respondeu." };
  }
}
