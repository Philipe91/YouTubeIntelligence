import { intelFile } from "@/lib/intel";

export async function GET(_request: Request, { params }: { params: Promise<{ canal: string; arquivo: string }> }) {
  const { canal, arquivo } = await params;
  return intelFile(`/channels/${encodeURIComponent(canal)}/lab/images/${encodeURIComponent(arquivo)}`);
}
