"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { studioWrite } from "@/lib/studio";

export interface ActionState { error: string | null; done: number }

function text(data: FormData, key: string): string {
  return String(data.get(key) ?? "").trim();
}

function list(data: FormData, key: string): string[] {
  return text(data, key).split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean);
}

function backlog(data: FormData, key: string): string[] {
  return text(data, key).split(/\n+/).map((item) => item.trim()).filter(Boolean);
}

function number(data: FormData, key: string): number | null {
  const raw = text(data, key).replace(",", ".");
  return raw ? Number(raw) : null;
}

function channelFields(data: FormData): Record<string, unknown> {
  const formats = data.getAll("formats").map(String);
  return {
    name: text(data, "name"), handle: text(data, "handle"), youtube_channel_id: text(data, "youtube_channel_id"),
    niche: text(data, "niche"), language: text(data, "language") || "pt", country: text(data, "country").toUpperCase(),
    audience: text(data, "audience"), positioning: text(data, "positioning"), tone: text(data, "tone"),
    keywords: list(data, "keywords"), avoid: list(data, "avoid"), topic_backlog: backlog(data, "topic_backlog"), formats,
    long_target_seconds: Math.round((number(data, "long_target_minutes") ?? 10) * 60),
    short_target_seconds: number(data, "short_target_seconds") ?? 60,
    cadence_per_week: number(data, "cadence_per_week"),
  };
}

function refresh(channelId?: string) {
  revalidatePath("/canais");
  revalidatePath("/fila");
  if (channelId) revalidatePath(`/canais/${channelId}`, "layout");
}

async function finish(previous: ActionState, result: Awaited<ReturnType<typeof studioWrite>>, channelId?: string): Promise<ActionState> {
  if (!result.ok) return { error: result.error, done: previous.done };
  refresh(channelId);
  return { error: null, done: previous.done + 1 };
}

const seg = encodeURIComponent;

export async function createChannel(previous: ActionState, data: FormData): Promise<ActionState> {
  const result = await studioWrite("POST", "/channels", { fields: channelFields(data) });
  if (!result.ok) return { error: result.error, done: previous.done };
  refresh();
  redirect(`/canais/${seg(String(result.data.id))}`);
}

export async function updateChannel(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("PATCH", `/channels/${seg(id)}`, { fields: channelFields(data) }), id);
}

export async function updateAutomation(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const fields = {
    auto_research: text(data, "auto_research"), auto_briefing: text(data, "auto_briefing"),
    auto_production: text(data, "auto_production"), auto_package: text(data, "auto_package"),
  };
  return finish(previous, await studioWrite("PATCH", `/channels/${seg(id)}`, { fields }), id);
}

export async function deleteChannel(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const result = await studioWrite("POST", `/channels/${seg(id)}/delete`, { confirm_name: text(data, "confirm_name") });
  if (!result.ok) return { error: result.error, done: previous.done };
  refresh();
  redirect("/canais");
}

export async function addCompetitor(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/competitors`, {
    name: text(data, "name"), youtube_ref: text(data, "youtube_ref") || null, notes: text(data, "notes"),
  }), id);
}

export async function addHistory(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const views = number(data, "views");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/history`, {
    title: text(data, "title"), format: text(data, "format"), published_on: text(data, "published_on"),
    url: text(data, "url") || null, views: views === null ? null : Math.round(views), result_notes: text(data, "result_notes"),
  }), id);
}

export async function removeItem(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const kinds: Record<string, string> = { competitor: "competitors", history: "history", calendar: "calendar" };
  const kind = kinds[text(data, "kind")];
  if (!kind) return { error: "Tipo de item inválido.", done: previous.done };
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/${kind}/${seg(text(data, "item_id"))}/delete`), id);
}

export async function generateRecommendations(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations/generate`), id);
}

export async function setRecommendationStatus(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations/${seg(text(data, "recommendation_id"))}/status`, { status: text(data, "status") }), id);
}

export async function produceSimulated(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  // A chave do formulário evita tarefa duplicada em caso de duplo clique.
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations/${seg(text(data, "recommendation_id"))}/produce`, {
    simulated: true, idempotency_key: text(data, "form_key"),
  }), id);
}

export async function addCalendarEntry(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/calendar`, {
    scheduled_on: text(data, "scheduled_on"), title: text(data, "title"), format: text(data, "format"), notes: text(data, "notes"),
  }), id);
}

export async function updateCalendarEntry(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("PATCH", `/channels/${seg(id)}/calendar/${seg(text(data, "entry_id"))}`, {
    scheduled_on: text(data, "scheduled_on") || null, status: text(data, "status") || null,
  }), id);
}

export async function createRecommendation(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const minutes = number(data, "duration_minutes");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations`, {
    subject: text(data, "subject"), justification: text(data, "justification"), format: text(data, "format"),
    duration_seconds: minutes === null ? null : Math.round(minutes * 60), editorial_priority: text(data, "editorial_priority") || "media",
  }), id);
}

export async function generateTitles(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations/${seg(text(data, "recommendation_id"))}/titles`), id);
}

export async function approveBriefing(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const choice = text(data, "chosen");
  const title = choice === "__outro__" ? text(data, "custom_title") : choice;
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/recommendations/${seg(text(data, "recommendation_id"))}/briefing`, {
    chosen_title: title, planned_on: text(data, "planned_on") || null,
  }), id);
}

export async function dispatchBriefing(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/briefings/${seg(text(data, "briefing_id"))}/dispatch`, { idempotency_key: text(data, "form_key"), real: text(data, "real") === "1" }), id);
}

export async function reviewJob(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/jobs/${seg(text(data, "job_id"))}/review`, { decision: text(data, "decision"), note: text(data, "note") }), id);
}

export async function acknowledgeAlert(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/alerts/${seg(text(data, "event_id"))}/acknowledge`), id);
}

export async function updatePipelineProfile(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  return finish(previous, await studioWrite("PATCH", `/channels/${seg(id)}`, { fields: { pipeline_profile: text(data, "pipeline_profile") } }), id);
}

const JOB_ACTIONS = new Set(["authorize", "cancel", "retry", "simulate-step", "simulate-failure"]);

export async function jobAction(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "channel_id");
  const action = text(data, "action");
  if (!JOB_ACTIONS.has(action)) return { error: "Ação inválida.", done: previous.done };
  return finish(previous, await studioWrite("POST", `/channels/${seg(id)}/jobs/${seg(text(data, "job_id"))}/${action}`), id);
}
