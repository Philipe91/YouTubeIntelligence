"use server";

import { revalidatePath } from "next/cache";

import { postGenerate } from "@/lib/api";

export interface GenerateState { error: string | null; done: boolean }

export async function generateIdeas(_previous: GenerateState, data: FormData): Promise<GenerateState> {
  const result = await postGenerate(String(data.get("topic")), String(data.get("format")));
  if (!result.ok) return { error: result.error, done: false };
  revalidatePath("/oportunidades/detalhe");
  return { error: null, done: true };
}
