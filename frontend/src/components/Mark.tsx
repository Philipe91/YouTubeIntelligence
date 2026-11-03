import type { Kind, Metric } from "@/lib/api";

export const KIND_INFO: Record<Kind, { label: string; meaning: string }> = {
  measured: { label: "Medido", meaning: "Veio direto da API do YouTube." },
  calculated: { label: "Calculado", meaning: "Conta deste aplicativo sobre valores medidos. Não é dado do YouTube." },
  estimated: { label: "Estimado", meaning: "Aproximação ou proxy. Use como indicação." },
  unavailable: { label: "Indisponível", meaning: "Não há fonte para este dado." },
  blocked: { label: "Bloqueado", meaning: "A política da API não permite este cálculo agora." },
};

/** Sinal de procedência: a forma, não só a cor, indica a origem do número. */
export function Mark({ kind, size = 11 }: { kind: Kind; size?: number }) {
  const shared = { width: size, height: size, viewBox: "0 0 12 12", "aria-hidden": true, className: "inline-block shrink-0" };
  switch (kind) {
    case "measured":
      return <svg {...shared}><circle cx="6" cy="6" r="5" fill="#17693f" /></svg>;
    case "calculated":
      return <svg {...shared}><path d="M6 .8 11.2 6 6 11.2.8 6Z" fill="#2747c7" /></svg>;
    case "estimated":
      return <svg {...shared}><circle cx="6" cy="6" r="4.6" fill="none" stroke="#a8650a" strokeWidth="1.8" strokeDasharray="2.2 1.6" /></svg>;
    case "unavailable":
      return <svg {...shared}><circle cx="6" cy="6" r="4.6" fill="none" stroke="#66736d" strokeWidth="1.4" /><path d="M2.8 9.2 9.2 2.8" stroke="#66736d" strokeWidth="1.4" /></svg>;
    case "blocked":
      return <svg {...shared}><rect x="1.5" y="1.5" width="9" height="9" rx="1.5" fill="none" stroke="#a3262c" strokeWidth="1.6" /><path d="M3.6 6h4.8" stroke="#a3262c" strokeWidth="1.6" /></svg>;
  }
}

function describe(metric: Metric<unknown>): string {
  const info = KIND_INFO[metric.kind];
  return [`${info.label}. ${metric.source}.`, metric.reason].filter(Boolean).join(" ");
}

/** Número com o sinal de procedência. Sem valor, mostra o motivo em vez de zero. */
export function Value({ metric, format, muted = "Sem dado" }: { metric: Metric; format: (value: number) => string; muted?: string }) {
  const text = metric.value === null ? (metric.kind === "blocked" ? "Bloqueado" : muted) : format(metric.value);
  return (
    <span className="inline-flex items-center gap-1.5" title={describe(metric)}>
      <Mark kind={metric.kind} />
      <span className={metric.value === null ? "text-ink-3" : ""}>{text}</span>
      <span className="sr-only">({KIND_INFO[metric.kind].label})</span>
    </span>
  );
}

export function MarkLegend({ tone = "dark" }: { tone?: "dark" | "light" }) {
  return (
    <ul className={`space-y-1.5 text-[0.8125rem] ${tone === "dark" ? "text-ink-2" : "text-ink-2"}`}>
      {(Object.keys(KIND_INFO) as Kind[]).map((kind) => (
        <li key={kind} className="flex items-center gap-2" title={KIND_INFO[kind].meaning}>
          <Mark kind={kind} /> {KIND_INFO[kind].label}
        </li>
      ))}
    </ul>
  );
}
