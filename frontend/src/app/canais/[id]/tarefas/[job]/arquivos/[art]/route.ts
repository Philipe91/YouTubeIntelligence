import { API_URL, authHeaders } from "@/lib/studio";

export const dynamic = "force-dynamic";

/** Repassa o arquivo da API. Anexo por padrão; ?ver=1 só tem efeito em vídeo e imagem de revisão. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string; job: string; art: string }> }) {
  const { id, job, art } = await params;
  const ver = new URL(request.url).searchParams.get("ver") === "1";
  const url = `${API_URL}/api/studio/channels/${encodeURIComponent(id)}/jobs/${encodeURIComponent(job)}/artifacts/${encodeURIComponent(art)}${ver ? "?inline=1" : ""}`;
  const range = request.headers.get("range");
  let upstream: Response;
  try {
    upstream = await fetch(url, { cache: "no-store", headers: { ...authHeaders(), ...(range ? { Range: range } : {}) } });
  } catch {
    return new Response("A API local não respondeu.", { status: 502 });
  }
  if (!upstream.ok) {
    const body = await upstream.json().catch(() => null);
    return new Response(body?.error?.message ?? "Arquivo indisponível.", { status: upstream.status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  const headers = new Headers({
    "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
    "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of ["accept-ranges", "content-range", "content-length"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}
