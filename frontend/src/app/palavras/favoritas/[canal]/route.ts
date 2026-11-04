import { intelFile } from "@/lib/intel";

export async function GET(_request: Request, { params }: { params: Promise<{ canal: string }> }) {
  const { canal } = await params;
  return intelFile(`/channels/${encodeURIComponent(canal)}/keywords/favorites.csv`);
}
