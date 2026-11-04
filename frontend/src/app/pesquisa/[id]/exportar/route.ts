import { intelFile } from "@/lib/intel";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return intelFile(`/research/runs/${encodeURIComponent(id)}/export.csv`);
}
