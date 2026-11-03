const compactFormatter = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const integerFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const decimalFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const compact = (value: number) => compactFormatter.format(value);
export const integer = (value: number) => integerFormatter.format(value);
export const decimal = (value: number) => decimalFormatter.format(value);
export const times = (value: number) => `${decimalFormatter.format(value)}x`;
export const percent = (value: number) => `${integerFormatter.format(value)}%`;

export function age(hours: number | null): string {
  if (hours === null) return "idade desconhecida";
  if (hours < 48) return `${integerFormatter.format(hours)} h`;
  const days = hours / 24;
  if (days < 60) return `${integerFormatter.format(days)} dias`;
  return `${integerFormatter.format(days / 30.4)} meses`;
}

export function duration(seconds: number | null): string {
  if (seconds === null) return "duração desconhecida";
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes >= 60) return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  return minutes ? `${minutes} min ${rest.toString().padStart(2, "0")} s` : `${rest} s`;
}

export function dateTime(iso: string | null): string {
  if (!iso) return "nunca";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" });
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", { dateStyle: "short", timeZone: "America/Sao_Paulo" });
}

export const BAND_LABEL: Record<string, string> = {
  extremo: "Muito fora do padrão",
  muito_acima: "Bem acima do típico",
  acima: "Acima do típico",
  tipico: "Típico",
  abaixo: "Abaixo do típico",
};

export const ACCELERATION_LABEL: Record<string, string> = {
  acelerando: "Acelerando",
  emergente: "Saiu do zero",
  estavel: "Estável",
  desacelerando: "Desacelerando",
  dados_insuficientes: "Dados insuficientes",
};

export const OUTLIER_STATUS_LABEL: Record<string, string> = {
  insufficient_sample: "Amostra insuficiente",
  too_young: "Vídeo muito novo",
  no_views: "Sem views",
  unknown_format: "Formato desconhecido",
};

export const FLAG_LABEL: Record<string, string> = {
  intervalo_curto: "intervalo curto demais",
  contagem_diminuiu: "contagem diminuiu",
  intervalo_longo: "intervalo longo",
  cruza_mudanca_de_contagem: "cruza mudança de contagem do YouTube",
  pares_em_regimes_de_contagem_diferentes: "pares medidos em regras de contagem diferentes",
  dispersao_zero: "todos os pares têm o mesmo valor",
  mediana_zero: "mediana dos pares é zero",
};

export const FORMAT_LABEL: Record<string, string> = { short: "Shorts", long: "Longos", live: "Lives", unknown: "Desconhecido" };
