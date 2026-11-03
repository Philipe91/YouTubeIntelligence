"use client";

import { useActionState } from "react";

import { generateIdeas, type GenerateState } from "./actions";

const INITIAL: GenerateState = { error: null, done: false };

export function GenerateButton({ topic, format, usesAi }: { topic: string; format: string; usesAi: boolean }) {
  const [state, action, pending] = useActionState(generateIdeas, INITIAL);
  return (
    <form action={action}>
      <input type="hidden" name="topic" value={topic} />
      <input type="hidden" name="format" value={format} />
      <button disabled={pending} className="rounded-md bg-pine px-4 py-2 text-sm font-medium text-white hover:bg-pine-soft disabled:opacity-60">
        {pending ? "Gerando ideias..." : usesAi ? "Gerar ideias com Claude" : "Gerar estrutura sem IA"}
      </button>
      {state.error && <p role="alert" className="mt-2 max-w-md text-sm text-bad">{state.error}</p>}
    </form>
  );
}
