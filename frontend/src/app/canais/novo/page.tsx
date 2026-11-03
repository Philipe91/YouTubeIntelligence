import { ActionForm } from "@/components/ActionForm";
import { ChannelFields } from "@/components/studio";
import { PageHeader, Panel } from "@/components/ui";

import { createChannel } from "../actions";

export default function NewChannel() {
  return (
    <>
      <PageHeader title="Cadastrar canal" intro="Só o nome é obrigatório. O perfil editorial orienta as recomendações, e não precisa de chave de API." />
      <Panel className="max-w-3xl p-5">
        <ActionForm action={createChannel} submit="Cadastrar canal" pending="Cadastrando...">
          <ChannelFields />
          <div className="h-4" />
        </ActionForm>
      </Panel>
    </>
  );
}
