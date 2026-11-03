import { MarkLegend } from "@/components/Mark";
import { PageHeader, Panel, SectionTitle } from "@/components/ui";
import { api, type SystemStatus } from "@/lib/api";
import { shortDate } from "@/lib/format";

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Panel className="p-5">
      <SectionTitle>{title}</SectionTitle>
      <div className="mt-2 space-y-2 text-[0.9375rem] leading-relaxed text-ink-2">{children}</div>
    </Panel>
  );
}

function Formula({ children }: { children: React.ReactNode }) {
  return <p className="rounded-md bg-page px-3 py-2 text-sm text-ink">{children}</p>;
}

export default async function Method() {
  const system = await api<SystemStatus>("/api/system");
  const outlier = system.scoring.outlier as Record<string, number>;
  const acceleration = system.scoring.acceleration as Record<string, number>;
  const opportunity = system.scoring.opportunity as Record<string, number>;
  const short = system.scoring.format as Record<string, number>;
  return (
    <>
      <PageHeader title="Como calculamos" intro="Fórmulas próprias, sem relação com fórmulas do vidIQ ou do YouTube. Os parâmetros ficam em backend/config/scoring.toml." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Block title="De onde vem cada número"><MarkLegend tone="light" /></Block>

        <Block title="IDR: Índice de Desempenho Relativo">
          <Formula>IDR = views do vídeo ÷ mediana das views dos pares na mesma idade</Formula>
          <p>Pares são outros vídeos do mesmo canal e formato. A idade vem dos snapshots, com interpolação linear e sem extrapolar. Sem histórico, um par com idade atual próxima (até {outlier.band_factor}x) entra como reserva, com menos confiança.</p>
          <p>Com menos de {outlier.min_sample} pares, o resultado é amostra insuficiente e não há valor. Vídeos com menos de {outlier.min_age_hours} h não são comparados.</p>
          <p>Faixas: típico abaixo de {outlier.band_above}x, acima a partir de {outlier.band_above}x, bem acima a partir de {outlier.band_high}x, muito fora do padrão a partir de {outlier.band_extreme}x.</p>
        </Block>

        <Block title="VPH observado e média histórica">
          <Formula>VPH observado = diferença de views ÷ horas entre dois snapshots</Formula>
          <Formula>Média histórica = views ÷ horas desde a publicação</Formula>
          <p>São coisas diferentes. Um vídeo antigo pode ter média alta e quase nenhuma velocidade hoje. O VPH observado só existe a partir do segundo snapshot.</p>
          <p>Queda na contagem, intervalo curto demais e intervalo que cruza uma mudança de contagem recebem alerta, e os dois primeiros ficam sem valor.</p>
        </Block>

        <Block title="Aceleração e tendências">
          <Formula>Razão = views por hora nas últimas {acceleration.window_hours} h ÷ views por hora nas {acceleration.window_hours} h anteriores</Formula>
          <p>Acelerando a partir de {acceleration.ratio_up}x, desacelerando até {acceleration.ratio_down}x. Sem snapshots cobrindo as duas janelas, o resultado é dados insuficientes. Vídeos novos costumam desacelerar naturalmente.</p>
          <p>Um termo em alta precisa aparecer em vários vídeos de mais de um canal, com pelo menos um deles acelerando.</p>
        </Block>

        <Block title="Ranking de oportunidades (experimental)">
          <Formula>Pontuação = {opportunity.weight_demand} × demanda + {opportunity.weight_competition} × (100 − concorrência) + {opportunity.weight_relevance} × relevância</Formula>
          <p><strong className="font-medium text-ink">Demanda:</strong> escala log da mediana de views por dia nos resultados. É um proxy de atenção e não mede buscas.</p>
          <p><strong className="font-medium text-ink">Concorrência:</strong> porte mediano dos canais, parcela de vídeos recentes e total aproximado de resultados.</p>
          <p><strong className="font-medium text-ink">Relevância:</strong> parcela das palavras do tema presentes no vocabulário do nicho e do seu canal.</p>
          <p><strong className="font-medium text-ink">Confiança:</strong> tamanho da amostra, diversidade de canais e cobertura de snapshots. Abaixo de {opportunity.min_confidence}, não há pontuação.</p>
        </Block>

        <Block title="Shorts e vídeos longos">
          <p>Nunca entram no mesmo cálculo. Para o YouTube, Short é um vídeo quadrado ou vertical de até 3 min enviado desde 15/10/2024; envios anteriores acima de {short.legacy_short_max_seconds} s seguem longos. A Data API não informa proporção nem se o vídeo é Short: usamos duração e data de envio, até {short.short_max_seconds} s, e rotulamos como estimado. Um vídeo 16:9 curto ainda pode ser mal classificado. Em Analytics, os totais por tipo de conteúdo vêm do YouTube.</p>
          <p>O YouTube mudou a forma de contar views:</p>
          <ul className="list-disc pl-4">
            {system.count_changes.map((change) => <li key={change.date}>{shortDate(change.date + "T12:00:00Z")}: {change.description}</li>)}
          </ul>
        </Block>

        <Block title="O que não existe nesta ferramenta">
          <p>Volume de busca e CTR de concorrentes: nenhuma API pública fornece. Previsão de views: não fazemos. Nenhuma pontuação garante resultado.</p>
          <p>Ideias geradas por IA ficam separadas das métricas e citam as evidências usadas. Fatos históricos precisam de conferência em fontes confiáveis.</p>
        </Block>
      </div>
    </>
  );
}

export const dynamic = "force-dynamic";
