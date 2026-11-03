"use client";

import { startTransition, useActionState, useEffect, useRef, type FormEvent, type ReactNode } from "react";

import type { ActionState } from "@/app/canais/actions";

const TONES = {
  primary: "bg-pine text-white hover:bg-pine-soft",
  quiet: "border border-line bg-surface text-ink hover:bg-page",
  danger: "border border-bad/40 bg-surface text-bad hover:bg-bad-soft",
};

interface Props {
  action: (state: ActionState, data: FormData) => Promise<ActionState>;
  submit: string;
  pending?: string;
  tone?: keyof typeof TONES;
  hidden?: Record<string, string>;
  children?: ReactNode;
  className?: string;
  resetOnSuccess?: boolean;
  doneMessage?: string;
}

/** Formulário ligado a uma ação do servidor, com estado de envio e erro legível. */
export function ActionForm({ action, submit, pending, tone = "primary", hidden, children, className, resetOnSuccess, doneMessage }: Props) {
  const [state, run, isPending] = useActionState(action, { error: null, done: 0 });
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.done > 0 && resetOnSuccess) form.current?.reset();
  }, [state.done, resetOnSuccess]);
  // Envio manual: com action direto, o React limpa o formulário mesmo quando a ação retorna erro.
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    startTransition(() => run(data));
  }
  return (
    <form ref={form} action={run} onSubmit={onSubmit} className={className}>
      {Object.entries(hidden ?? {}).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}
      {children}
      <button disabled={isPending} className={`min-h-9 rounded-md px-3.5 text-sm font-medium disabled:opacity-60 ${TONES[tone]}`}>
        {isPending ? pending ?? "Salvando..." : submit}
      </button>
      {state.error && <p role="alert" className="mt-1.5 max-w-md text-sm text-bad">{state.error}</p>}
      {!state.error && state.done > 0 && doneMessage && <p role="status" className="mt-1.5 text-sm text-good">{doneMessage}</p>}
    </form>
  );
}
