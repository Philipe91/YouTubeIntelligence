"use client";

import { useEffect, useId, useRef, useState, type RefObject } from "react";

import { compact, integer } from "@/lib/format";

const HEIGHT = 260;
const PAD = { top: 16, right: 18, bottom: 34, left: 54 };
const INNER_H = HEIGHT - PAD.top - PAD.bottom;
const AXIS_FONT = 13;

/** Mede a largura real: o texto do eixo mantém o mesmo tamanho no celular e no desktop. */
function useWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(entry.contentRect.width, 240)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const scaled = value / power;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * power;
}

function ageTick(hours: number): string {
  return hours < 72 ? `${Math.round(hours)} h` : `${Math.round(hours / 24)} d`;
}

function HorizontalGrid({ yMax, width }: { yMax: number; width: number }) {
  return (
    <g>
      {[0, 0.5, 1].map((tick) => {
        const y = PAD.top + INNER_H * (1 - tick);
        return (
          <g key={tick}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} stroke="#d5ddd8" strokeWidth={1} />
            <text x={PAD.left - 8} y={y + 4} textAnchor="end" fontSize={AXIS_FONT} fill="#66736d">{compact(yMax * tick)}</text>
          </g>
        );
      })}
    </g>
  );
}

function tooltipLeft(x: number, width: number, boxWidth = 190): number {
  return Math.max(0, Math.min(x + 12, width - boxWidth));
}

export interface CurvePoint { age: number; views: number }

/** Views do vídeo e mediana dos pares, por idade. Um eixo só. */
export function ViewsChart({ target, peers }: { target: CurvePoint[]; peers: { age: number; views: number; sample: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [ref, width] = useWidth();
  const titleId = useId();
  if (target.length === 0) return <p className="p-6 text-sm text-ink-3">Sem snapshots com views para desenhar.</p>;
  const innerW = width - PAD.left - PAD.right;
  const xMax = Math.max(...target.map((p) => p.age), 1);
  const yMax = niceMax(Math.max(...target.map((p) => p.views), ...peers.map((p) => p.views), 1));
  const x = (value: number) => PAD.left + (value / xMax) * innerW;
  const y = (value: number) => PAD.top + INNER_H * (1 - value / yMax);
  const path = (points: { age: number; views: number }[]) => points.map((p, i) => `${i ? "L" : "M"}${x(p.age).toFixed(1)} ${y(p.views).toFixed(1)}`).join(" ");
  const point = hover === null ? null : target[hover];
  const nearestPeer = point && peers.length
    ? peers.reduce((best, p) => (Math.abs(p.age - point.age) < Math.abs(best.age - point.age) ? p : best))
    : null;
  const xTicks = width < 480 ? [0, 0.5, 1] : [0, 0.25, 0.5, 0.75, 1];

  function onMove(event: React.PointerEvent<SVGRectElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const age = ((event.clientX - rect.left) / rect.width) * xMax;
    let best = 0;
    target.forEach((p, i) => {
      if (Math.abs(p.age - age) < Math.abs(target[best].age - age)) best = i;
    });
    setHover(best);
  }

  const lastTarget = target[target.length - 1];
  const lastPeer = peers[peers.length - 1];
  return (
    <figure className="relative">
      <div className="mb-2 flex flex-wrap gap-4 text-[0.8125rem] text-ink-2">
        <span className="inline-flex items-center gap-1.5"><svg width="18" height="8" aria-hidden><line x1="0" x2="18" y1="4" y2="4" stroke="#2747c7" strokeWidth="2" /></svg>Este vídeo (medido)</span>
        {peers.length > 0 && <span className="inline-flex items-center gap-1.5"><svg width="18" height="8" aria-hidden><line x1="0" x2="18" y1="4" y2="4" stroke="#a8650a" strokeWidth="2" strokeDasharray="5 3" /></svg>Mediana dos pares na mesma idade (calculado)</span>}
      </div>
      <div ref={ref} className="relative">
        <svg width={width} height={HEIGHT} className="block max-w-full" role="img" aria-labelledby={titleId}>
          <title id={titleId}>Views acumuladas por idade do vídeo</title>
          <HorizontalGrid yMax={yMax} width={width} />
          {xTicks.map((tick) => (
            <text key={tick} x={PAD.left + innerW * tick} y={HEIGHT - 10} textAnchor={tick === 1 ? "end" : tick === 0 ? "start" : "middle"} fontSize={AXIS_FONT} fill="#66736d">{ageTick(xMax * tick)}</text>
          ))}
          {peers.length > 1 && <path d={path(peers)} fill="none" stroke="#a8650a" strokeWidth={2} strokeDasharray="6 4" strokeLinejoin="round" />}
          <path d={path(target)} fill="none" stroke="#2747c7" strokeWidth={2} strokeLinejoin="round" />
          <circle cx={x(lastTarget.age)} cy={y(lastTarget.views)} r={4} fill="#2747c7" stroke="#fcfcfb" strokeWidth={2} />
          {lastPeer && <circle cx={x(lastPeer.age)} cy={y(lastPeer.views)} r={4} fill="#a8650a" stroke="#fcfcfb" strokeWidth={2} />}
          {point && (
            <g>
              <line x1={x(point.age)} x2={x(point.age)} y1={PAD.top} y2={PAD.top + INNER_H} stroke="#66736d" strokeWidth={1} />
              <circle cx={x(point.age)} cy={y(point.views)} r={5} fill="#2747c7" stroke="#fcfcfb" strokeWidth={2} />
            </g>
          )}
          <rect x={PAD.left} y={PAD.top} width={innerW} height={INNER_H} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
        {point && (
          <figcaption
            className="tooltip-box pointer-events-none absolute top-3 w-[190px] rounded-md border border-line bg-surface px-2.5 py-1.5 text-[0.8125rem] shadow-sm"
            style={{ left: tooltipLeft(x(point.age), width) }}
          >
            <div className="text-ink-3">Idade {ageTick(point.age)}</div>
            <div>{integer(point.views)} views</div>
            {nearestPeer && <div className="text-ink-2">Pares: {integer(nearestPeer.views)} (n={nearestPeer.sample})</div>}
          </figcaption>
        )}
      </div>
    </figure>
  );
}

export interface BarPoint { label: string; value: number | null; note?: string }

/** Barras finas, uma por intervalo ou dia. Valor ausente fica como lacuna, nunca como zero. */
export function Bars({ points, unit, color = "#2747c7", title }: { points: BarPoint[]; unit: string; color?: string; title: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [ref, width] = useWidth();
  const titleId = useId();
  if (points.length === 0) return <p className="p-6 text-sm text-ink-3">Sem dados para desenhar.</p>;
  const innerW = width - PAD.left - PAD.right;
  const max = niceMax(Math.max(...points.map((p) => p.value ?? 0), 1));
  const slot = innerW / points.length;
  const barWidth = Math.max(1.5, Math.min(12, slot - 2));
  const hovered = hover === null ? null : points[hover];
  return (
    <figure className="relative">
      <div ref={ref} className="relative">
        <svg width={width} height={HEIGHT} className="block max-w-full" role="img" aria-labelledby={titleId}>
          <title id={titleId}>{title}</title>
          <HorizontalGrid yMax={max} width={width} />
          <text x={PAD.left} y={HEIGHT - 10} textAnchor="start" fontSize={AXIS_FONT} fill="#66736d">{points[0].label}</text>
          {points.length > 1 && <text x={width - PAD.right} y={HEIGHT - 10} textAnchor="end" fontSize={AXIS_FONT} fill="#66736d">{points[points.length - 1].label}</text>}
          {points.map((point, index) => {
            const cx = PAD.left + slot * index + slot / 2;
            const height = point.value === null ? 0 : (point.value / max) * INNER_H;
            return (
              <g key={index} onPointerEnter={() => setHover(index)} onPointerLeave={() => setHover(null)}>
                <rect x={PAD.left + slot * index} y={PAD.top} width={slot} height={INNER_H} fill="transparent" />
                {point.value !== null && (
                  <rect x={cx - barWidth / 2} y={PAD.top + INNER_H - height} width={barWidth} height={Math.max(height, 1)} rx={Math.min(3, barWidth / 2)} fill={color} opacity={hover === null || hover === index ? 1 : 0.45} />
                )}
              </g>
            );
          })}
        </svg>
        {hovered && hover !== null && (
          <figcaption
            className="tooltip-box pointer-events-none absolute top-1 w-[190px] rounded-md border border-line bg-surface px-2.5 py-1.5 text-[0.8125rem] shadow-sm"
            style={{ left: tooltipLeft(PAD.left + slot * hover, width) }}
          >
            <div className="text-ink-3">{hovered.label}</div>
            <div>{hovered.value === null ? "Sem valor" : `${integer(hovered.value)} ${unit}`}</div>
            {hovered.note && <div className="text-ink-2">{hovered.note}</div>}
          </figcaption>
        )}
      </div>
    </figure>
  );
}

/** Indicador de 0 a 100. Ausente aparece como "sem dado", com a barra vazia. */
export function Meter({ label, value, tone = "#2747c7", title }: { label: string; value: number | null; tone?: string; title?: string }) {
  return (
    <div title={title}>
      <div className="flex items-baseline justify-between gap-2 text-[0.8125rem]">
        <span className="text-ink-2">{label}</span>
        <span className="font-medium text-ink">{value === null ? "Sem dado" : integer(value)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-page" role="presentation">
        {value !== null && <div className="h-full rounded-full" style={{ width: `${Math.max(value, 1)}%`, background: tone }} />}
      </div>
    </div>
  );
}
