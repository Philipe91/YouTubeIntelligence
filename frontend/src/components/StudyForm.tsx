import { addStudy } from "@/app/intel-actions";
import { ActionForm } from "@/components/ActionForm";
import { ChannelSelect } from "@/components/intel";
import { intelGet, type IntelContext } from "@/lib/intel";

/** Guarda um vídeo na lista de estudo do canal escolhido. */
export async function StudyForm({ videoId }: { videoId: string }) {
  const context = await intelGet<IntelContext>("/context");
  if (!context.channels.length) return null;
  return (
    <ActionForm action={addStudy} submit="Guardar para estudo" tone="quiet" hidden={{ video_id: videoId }} className="mb-5 flex flex-wrap items-end gap-2" doneMessage="Guardado na lista de estudo.">
      <label className="min-w-56 text-sm text-ink-2">Lista de estudo do canal
        <div className="mt-1"><ChannelSelect context={context} emptyLabel="Escolha um canal" /></div>
      </label>
    </ActionForm>
  );
}
