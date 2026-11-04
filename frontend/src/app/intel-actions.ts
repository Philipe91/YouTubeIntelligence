"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import type { ActionState } from "@/app/canais/actions";
import { intelWrite } from "@/lib/intel";
import type { WriteResult } from "@/lib/studio";

const seg = encodeURIComponent;

function text(data: FormData, key: string): string {
  return String(data.get(key) ?? "").trim();
}

function done(previous: ActionState, result: WriteResult, ...paths: string[]): ActionState {
  if (!result.ok) return { error: result.error, done: previous.done };
  for (const path of paths) revalidatePath(path, "page");
  return { error: null, done: previous.done + 1 };
}

// --- Research Center --------------------------------------------------------------------------

export async function runResearch(previous: ActionState, data: FormData): Promise<ActionState> {
  const days = Number(text(data, "days")) || null;
  const maxSubscribers = Number(text(data, "max_subscribers")) || null;
  const result = await intelWrite("/research/search", {
    kind: text(data, "kind") || "videos", query: text(data, "query"), channel_id: text(data, "channel_id") || null,
    language: text(data, "language") || null, country: text(data, "country") || null, days,
    format: text(data, "format") || null, order: text(data, "order") || "relevance", max_subscribers: maxSubscribers,
  });
  if (!result.ok) return { error: result.error, done: previous.done };
  revalidatePath("/pesquisa");
  redirect(`/pesquisa/${seg(String(result.data.id))}`);
}

export async function saveRun(previous: ActionState, data: FormData): Promise<ActionState> {
  const id = text(data, "run_id");
  return done(previous, await intelWrite(`/research/runs/${seg(id)}/save`, { name: text(data, "name") || null }), `/pesquisa/${id}`, "/pesquisa");
}

export async function rerunResearch(previous: ActionState, data: FormData): Promise<ActionState> {
  const result = await intelWrite(`/research/runs/${seg(text(data, "run_id"))}/rerun`);
  if (!result.ok) return { error: result.error, done: previous.done };
  revalidatePath("/pesquisa");
  redirect(`/pesquisa/${seg(String(result.data.id))}`);
}

export async function deleteRun(previous: ActionState, data: FormData): Promise<ActionState> {
  const result = await intelWrite(`/research/runs/${seg(text(data, "run_id"))}/delete`);
  if (!result.ok) return { error: result.error, done: previous.done };
  revalidatePath("/pesquisa");
  redirect("/pesquisa?aba=historico");
}

// --- Keyword Intelligence ----------------------------------------------------------------------

export async function lookupKeyword(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  const result = await intelWrite("/keywords/lookup", { term: text(data, "term"), channel_id: channel || null, fetch: text(data, "fetch") === "1" });
  if (!result.ok) return { error: result.error, done: previous.done };
  const query = new URLSearchParams({ termo: String(result.data.term) });
  if (channel) query.set("canal", channel);
  const failure = result.data.fetch_error as { message?: string } | null;
  if (failure?.message) query.set("aviso", failure.message);
  revalidatePath("/palavras");
  redirect(`/palavras?${query}`);
}

export async function addFavorite(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  if (!channel) return { error: "Escolha um canal para salvar o favorito.", done: previous.done };
  return done(previous, await intelWrite(`/channels/${seg(channel)}/keywords/favorites`, { term: text(data, "term"), note: text(data, "note") }), "/palavras");
}

export async function removeFavorite(previous: ActionState, data: FormData): Promise<ActionState> {
  return done(previous, await intelWrite(`/channels/${seg(text(data, "channel_id"))}/keywords/favorites/remove`, { term: text(data, "term") }), "/palavras");
}

// --- Outlier Explorer --------------------------------------------------------------------------

export async function addStudy(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  if (!channel) return { error: "Escolha um canal.", done: previous.done };
  return done(previous, await intelWrite(`/channels/${seg(channel)}/study`, { video_id: text(data, "video_id"), origin: text(data, "origin") || "explorer", note: text(data, "note") }), "/explorer", `/videos/${text(data, "video_id")}`, `/canais/${channel}/concorrentes`);
}

export async function saveStudyNote(previous: ActionState, data: FormData): Promise<ActionState> {
  return done(previous, await intelWrite(`/channels/${seg(text(data, "channel_id"))}/study/note`, { video_id: text(data, "video_id"), note: text(data, "note") }), "/explorer");
}

export async function removeStudy(previous: ActionState, data: FormData): Promise<ActionState> {
  return done(previous, await intelWrite(`/channels/${seg(text(data, "channel_id"))}/study/remove`, { video_id: text(data, "video_id") }), "/explorer");
}

// --- Competitor Intelligence -------------------------------------------------------------------

export async function addCompetitorRef(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/competitors`, { reference: text(data, "reference"), name: text(data, "name"), notes: text(data, "notes") }), `/canais/${channel}/concorrentes`, `/canais/${channel}`);
}

export async function linkCompetitor(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/competitors/${seg(text(data, "competitor_id"))}/link`, { reference: text(data, "reference") }), `/canais/${channel}/concorrentes`);
}

export async function refreshCompetitor(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  const id = text(data, "competitor_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/competitors/${seg(id)}/refresh`), `/canais/${channel}/concorrentes`, `/canais/${channel}/concorrentes/${id}`);
}

export async function addOpportunity(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/opportunities`, { title: text(data, "title"), note: text(data, "note"), video_id: text(data, "video_id") || null }), `/canais/${channel}/concorrentes`);
}

export async function discardOpportunity(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/opportunities/${seg(text(data, "opportunity_id"))}/discard`), `/canais/${channel}/concorrentes`);
}

export async function opportunityToIdea(previous: ActionState, data: FormData): Promise<ActionState> {
  const channel = text(data, "channel_id");
  return done(previous, await intelWrite(`/channels/${seg(channel)}/opportunities/${seg(text(data, "opportunity_id"))}/idea`, { format: text(data, "format") }), `/canais/${channel}/concorrentes`, `/canais/${channel}`);
}
