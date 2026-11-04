import { API_URL } from "@/lib/studio";

export const dynamic = "force-dynamic";

/** Repassa o download da API. Sempre como anexo: o navegador não interpreta o conteúdo. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string; job: string; art: string }> }) {
  const { id, job, art } = await params;
  const url = `${API_URL}/api/studio/channels/${encodeURIComponent(id)}/jobs/${encodeURIComponent(job)}/artifacts/${encodeURIComponent(art)}`;
  let upstream: Response;
  try {
    upstream = await fetch(url, { cache: "no-store" });
  } catch {
    return new Response("A API local não respondeu.", { status: 502 });
  }
  if (!upstream.ok) {
    const body = await upstream.json().catch(() => null);
    return new Response(body?.error?.message ?? "Arquivo indisponível.", { status: upstream.status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
