"use client";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="max-w-xl rounded-lg border border-line bg-surface p-6">
      <h1 className="font-display text-xl font-semibold">Não foi possível carregar esta tela</h1>
      <p className="mt-2 text-[0.9375rem] text-ink-2">{error.message || "A API local não respondeu como esperado."}</p>
      <p className="mt-2 text-[0.9375rem] text-ink-2">Confira se o backend está rodando em 127.0.0.1:8000 e tente de novo.</p>
      <button onClick={reset} className="mt-4 rounded-md bg-pine px-4 py-2 text-sm font-medium text-white hover:bg-pine-soft">Tentar de novo</button>
    </div>
  );
}
