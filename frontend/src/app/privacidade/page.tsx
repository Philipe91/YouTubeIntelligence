import { PageHeader, Panel, SectionTitle } from "@/components/ui";

const LINK = "text-cobalt underline underline-offset-2";

function External({ href, children }: { href: string; children: string }) {
  return <a className={LINK} href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
}

export default function Privacy() {
  return (
    <>
      <PageHeader title="Dados e privacidade" intro="O que este aplicativo lê do YouTube, onde guarda e como apagar." />
      <div className="grid max-w-5xl gap-4 lg:grid-cols-2">
        <Panel className="p-5 text-sm leading-relaxed text-ink-2">
          <SectionTitle>Serviços usados</SectionTitle>
          <p className="mt-2">Este aplicativo usa os serviços de API do YouTube. Ao usá-lo, você concorda com os <External href="https://www.youtube.com/t/terms">Termos de Serviço do YouTube</External>. A <External href="https://policies.google.com/privacy">Política de Privacidade do Google</External> se aplica ao que o Google trata.</p>
          <p className="mt-2">Com a sua autorização, você pode revogar o acesso a qualquer momento nas <External href="https://security.google.com/settings/security/permissions">permissões da sua Conta Google</External>.</p>
        </Panel>
        <Panel className="p-5 text-sm leading-relaxed text-ink-2">
          <SectionTitle>O que é lido e guardado</SectionTitle>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li><strong className="font-medium text-ink">Dados públicos,</strong> só com a chave de API: título, canal, data, duração, views, curtidas, comentários e inscritos públicos.</li>
            <li><strong className="font-medium text-ink">Dados dos seus canais,</strong> só se você autorizar: relatórios do YouTube Analytics, somente leitura.</li>
            <li><strong className="font-medium text-ink">Dados seus:</strong> canais cadastrados, notas, pesquisas e temas.</li>
          </ul>
          <p className="mt-2">Tudo fica neste computador, em <code>data/</code>, fora do Git. O aplicativo não envia esses dados a outros serviços. A exceção é o Coach, se você ligar um provedor de IA: nesse caso, a pergunta e os dados consultados vão para esse provedor.</p>
        </Panel>
        <Panel className="p-5 text-sm leading-relaxed text-ink-2">
          <SectionTitle>Por quanto tempo</SectionTitle>
          <p className="mt-2">Títulos, nomes e descrições são atualizados ou apagados em 30 dias. Estatísticas de canais de terceiros também saem em 30 dias, salvo aprovação do Google para um prazo maior. O que é seu fica até você apagar.</p>
        </Panel>
        <Panel className="p-5 text-sm leading-relaxed text-ink-2">
          <SectionTitle>Como apagar</SectionTitle>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>Um canal: <code>python -m app.cli delete-channel-data &lt;id&gt;</code>, a partir de <code>backend</code>.</li>
            <li>Revogar um canal próprio: <code>python -m app.cli revoke-channel &lt;id&gt;</code>. Revoga no Google e apaga os dados aqui.</li>
            <li>Todos os dados reais: desligue o aplicativo e apague <code>data/live.sqlite</code>.</li>
          </ul>
          <p className="mt-2">Isso apaga só a cópia local. Nada é apagado no YouTube.</p>
        </Panel>
      </div>
      <p className="mt-4 max-w-3xl text-[0.8125rem] text-ink-3">As regras completas e o que ainda depende de decisão estão em <code>docs/POLITICA_DE_DADOS.md</code>. Este texto descreve o funcionamento do aplicativo e não é um parecer jurídico.</p>
    </>
  );
}
