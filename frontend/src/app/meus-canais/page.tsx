import { Bars } from "@/components/Charts";
import { Value } from "@/components/Mark";
import { Empty, PageHeader, Panel, SectionTitle, SourceLink } from "@/components/ui";
import { api, type OwnChannel } from "@/lib/api";
import { FORMAT_LABEL, compact, decimal, integer, shortDate } from "@/lib/format";

const COLORS: Record<string, string> = { short: "#2747c7", long: "#a8650a" };

function Fact({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div>
      <dt className="text-[0.8125rem] text-ink-3">{label}</dt>
      <dd className="mt-0.5 font-display text-[1.25rem] font-semibold">{children}</dd>
      {note && <dd className="text-[0.8125rem] text-ink-3">{note}</dd>}
    </div>
  );
}

export default async function OwnChannels() {
  const channels = await api<OwnChannel[]>("/api/own-channels");
  return (
    <>
      <PageHeader title="Meus canais" intro="Dados da YouTube Analytics API, só dos canais que você autorizar. O acesso é somente leitura." />
      {channels.length === 0 && (
        <Panel><Empty title="Nenhum canal autorizado.">Rode o comando authorize-channel depois de configurar o OAuth. O passo a passo está no README.</Empty></Panel>
      )}
      <div className="space-y-6">
        {channels.map((channel) => (
          <section key={channel.id}>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
              <SectionTitle>{channel.title}</SectionTitle>
              <div className="flex items-center gap-4 text-sm text-ink-2">
                {channel.as_of && <span>Últimos {channel.days} dias até {shortDate(channel.as_of + "T12:00:00Z")}</span>}
                <SourceLink url={channel.source_url} label="Abrir canal" />
              </div>
            </div>
            {!channel.has_analytics ? <Panel><Empty title="Ainda sem dados do Analytics.">Rode a coleta para buscar o primeiro relatório.</Empty></Panel> : (
              <div className="grid gap-4 lg:grid-cols-2">
                {channel.formats.map((item) => (
                  <Panel key={item.content_type} className="p-4">
                    <h3 className="font-display text-[1.0625rem] font-semibold">{FORMAT_LABEL[item.format] ?? item.content_type}</h3>
                    <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <Fact label="Views"><Value metric={item.views} format={compact} /></Fact>
                      <Fact label="Minutos assistidos"><Value metric={item.minutes_watched} format={compact} /></Fact>
                      <Fact label="Inscritos, saldo"><Value metric={item.subscribers_net} format={integer} /></Fact>
                      <Fact label="Retenção média" note="% média assistida por reprodução"><Value metric={item.average_view_percentage} format={(v) => `${decimal(v)}%`} /></Fact>
                      <Fact label="CTR de thumbnail" note="Consulte o YouTube Studio"><Value metric={item.ctr} format={integer} muted="Indisponível" /></Fact>
                    </dl>
                    <div className="mt-4">
                      <Bars title={`Views por dia em ${FORMAT_LABEL[item.format]}`} unit="views" color={COLORS[item.format] ?? "#2747c7"}
                        points={item.daily.map((d) => ({ label: shortDate(d.day + "T12:00:00Z"), value: d.views }))} />
                    </div>
                  </Panel>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
