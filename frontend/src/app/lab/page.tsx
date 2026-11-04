import Link from "next/link";

import { ActionForm } from "@/components/ActionForm";
import { Empty, PageHeader, Panel, Pill, SectionTitle, str } from "@/components/ui";
import { Notice, Pagination } from "@/components/intel";
import { dateTime } from "@/lib/format";
import { intelGet, intelGetOrNull, type ImageEval, type LabCriterion, type LabProject, type LabProjects, type LabVariation, type TitleEval } from "@/lib/intel";
import { studioGet, type StudioOverview } from "@/lib/studio";

import {
  addLabVariation, attachLabImage, createLabProject, deleteLabProject, deleteLabVariation, updateLabVariation,
} from "../intel-actions";

function Criteria({ items }: { items: LabCriterion[] }) {
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.key} className="text-[0.8125rem]">
          <div className="flex items-center justify-between gap-2"><span className="font-medium text-ink">{item.label}</span><span className="text-ink-2">{item.score} de 100</span></div>
          <div className="mt-0.5 h-1 rounded-full bg-page" aria-hidden><div className="h-1 rounded-full bg-cobalt" style={{ width: `${item.score}%` }} /></div>
          <p className="mt-0.5 text-ink-3">{item.explanation}</p>
        </li>
      ))}
    </ul>
  );
}

function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[0.8125rem] text-warn">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function imageUrl(channel: string, file: string) {
  return `/lab/imagem/${channel}/${file}`;
}

/** Prévia neutra: mostra título e imagem juntos em três tamanhos, sem imitar a tela de nenhum serviço. */
function Preview({ variation, channel, channelName }: { variation: LabVariation; channel: string; channelName: string }) {
  const picture = variation.image_file ? imageUrl(channel, variation.image_file) : null;
  const sizes = [
    { key: "grande", label: "Grade", width: "w-full max-w-72", direction: "flex-col", titleSize: "text-sm", lines: "line-clamp-2", thumb: "w-full" },
    { key: "lista", label: "Lista lateral", width: "w-full max-w-80", direction: "flex-row", titleSize: "text-[0.8125rem]", lines: "line-clamp-2", thumb: "w-[168px] shrink-0" },
  ];
  return (
    <div className="flex flex-wrap items-start gap-4">
      {sizes.map((size) => (
        <figure key={size.key} className={size.width}>
          <figcaption className="mb-1 text-[0.75rem] text-ink-3">{size.label}</figcaption>
          <div className={`flex gap-2 ${size.direction}`}>
            <div className={`${size.thumb} aspect-video overflow-hidden rounded bg-page`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {picture ? <img src={picture} alt={`Thumbnail de ${variation.title}`} className="size-full object-cover" /> : <div className="flex size-full items-center justify-center text-[0.75rem] text-ink-3">Sem imagem</div>}
            </div>
            <div className="min-w-0">
              <p className={`${size.titleSize} ${size.lines} leading-snug font-medium`}>{variation.title}</p>
              <p className="mt-0.5 text-[0.75rem] text-ink-3">{channelName}</p>
            </div>
          </div>
        </figure>
      ))}
    </div>
  );
}

function ImageResult({ evaluation }: { evaluation: ImageEval }) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium">Imagem: nota de revisão {evaluation.review_score} de 100</p>
      <Criteria items={evaluation.criteria} />
      <Warnings items={evaluation.warnings} />
      <p className="mt-2 text-[0.75rem] text-ink-3">{evaluation.limits.join(" ")}</p>
    </div>
  );
}

function TitleResult({ evaluation }: { evaluation: TitleEval }) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium">Título: nota de revisão {evaluation.review_score} de 100</p>
      <Criteria items={evaluation.criteria} />
      <Warnings items={evaluation.warnings} />
    </div>
  );
}

function VariationCard({ variation, channel, channelName }: { variation: LabVariation; channel: string; channelName: string }) {
  const hidden = { channel_id: channel, variation_id: variation.id };
  return (
    <article className="min-w-0 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-[0.9375rem] leading-snug font-semibold">{variation.title}</h3>
        {variation.favorite && <Pill tone="ochre">Favorita</Pill>}
      </div>
      <div className="mt-3"><Preview variation={variation} channel={channel} channelName={channelName} /></div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <TitleResult evaluation={variation.title_eval} />
        {variation.image_eval ? <ImageResult evaluation={variation.image_eval} /> : <p className="text-sm text-ink-3">Envie uma imagem para analisar contraste, composição e leitura em tamanho pequeno.</p>}
      </div>
      <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-3">
        <ActionForm action={updateLabVariation} submit="Salvar nota" tone="quiet" hidden={hidden} className="flex min-w-60 flex-1 flex-wrap items-end gap-2" doneMessage="Nota salva.">
          <label className="min-w-52 flex-1 text-[0.8125rem] text-ink-2">Sua nota<input name="note" defaultValue={variation.note} maxLength={1000} className="field mt-1 w-full" /></label>
        </ActionForm>
        <ActionForm action={attachLabImage} submit="Enviar imagem" pending="Analisando..." tone="quiet" hidden={hidden} className="flex flex-wrap items-end gap-2">
          <label className="text-[0.8125rem] text-ink-2">Trocar ou enviar thumbnail<input type="file" name="image" accept="image/jpeg,image/png,image/webp" required className="mt-1 block max-w-56 text-[0.8125rem]" /></label>
        </ActionForm>
        <ActionForm action={updateLabVariation} submit={variation.favorite ? "Tirar dos favoritos" : "Favoritar"} tone="quiet" hidden={{ ...hidden, favorite: variation.favorite ? "0" : "1" }} />
        <ActionForm action={deleteLabVariation} submit="Apagar variação" tone="danger" hidden={hidden} />
      </div>
    </article>
  );
}

function ProjectView({ data, channel }: { data: LabProject; channel: string }) {
  const projectHidden = { channel_id: channel, project_id: data.project.id };
  const compared = data.variations.filter((v) => v.title_eval);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-cobalt underline underline-offset-2" href={`/lab?canal=${channel}`}>Voltar aos projetos</Link></p>
          <h2 className="mt-1 font-display text-[1.375rem] font-semibold">{data.project.subject}</h2>
        </div>
        <ActionForm action={deleteLabProject} submit="Apagar projeto" tone="danger" hidden={projectHidden} />
      </div>
      <div className="mb-4"><Notice tone="warn">{data.note}</Notice></div>

      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-3">
          <SectionTitle>Variações salvas ({data.variations.length})</SectionTitle>
          {data.variations.length ? data.variations.map((variation) => <VariationCard key={variation.id} variation={variation} channel={channel} channelName={data.channel_name} />)
            : <Panel><Empty title="Nenhuma variação ainda.">Guarde uma alternativa ou escreva o seu título.</Empty></Panel>}
          {compared.length >= 2 && (
            <Panel className="p-4">
              <SectionTitle>Comparar opções</SectionTitle>
              <div className="mt-3 overflow-x-auto">
                <table className="data-table w-full min-w-[34rem]">
                  <thead><tr><th>Título</th><th className="num">Caracteres</th>{compared[0].title_eval.criteria.map((c) => <th key={c.key} className="num">{c.label}</th>)}<th className="num">Imagem</th></tr></thead>
                  <tbody>{compared.map((v) => (
                    <tr key={v.id}><td className="max-w-64">{v.title}</td><td className="num">{v.title_eval.characters}</td>{v.title_eval.criteria.map((c) => <td key={c.key} className="num">{c.score}</td>)}<td className="num">{v.image_eval ? v.image_eval.review_score : "Sem imagem"}</td></tr>
                  ))}</tbody>
                </table>
              </div>
              <p className="mt-2 text-[0.8125rem] text-ink-3">Comparação editorial, sem vencedor. Quem decide é você.</p>
            </Panel>
          )}
        </div>
        <div className="min-w-0 space-y-4">
          <Panel className="p-4">
            <SectionTitle>Nova variação</SectionTitle>
            <ActionForm action={addLabVariation} submit="Salvar variação" pending="Analisando..." resetOnSuccess hidden={projectHidden} className="mt-3" doneMessage="Variação salva.">
              <div className="mb-3 space-y-2">
                <label className="block text-[0.8125rem] text-ink-2">Seu título<input name="title" required maxLength={200} className="field mt-1 w-full" /></label>
                <label className="block text-[0.8125rem] text-ink-2">Thumbnail (opcional)<input type="file" name="image" accept="image/jpeg,image/png,image/webp" className="mt-1 block w-full text-[0.8125rem]" /></label>
                <p className="text-[0.75rem] text-ink-3">JPEG, PNG ou WebP, até 5 MB. Fica só neste computador, em cópia reduzida e sem metadados.</p>
              </div>
            </ActionForm>
          </Panel>
          <Panel className="p-4">
            <SectionTitle>Alternativas de título</SectionTitle>
            <p className="mt-0.5 text-[0.8125rem] text-ink-3">Modelos de texto, no idioma do canal. Títulos iguais a vídeos coletados ficam de fora.</p>
            <ul className="mt-3 divide-y divide-line">
              {data.suggestions.map((item) => (
                <li key={item.title} className="py-2">
                  <p className="text-sm">{item.title}</p>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="text-[0.75rem] text-ink-3">Revisão {item.review_score} de 100, {item.characters} caracteres</span>
                    <ActionForm action={addLabVariation} submit="Guardar título" tone="quiet" hidden={{ ...projectHidden, title: item.title }} />
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}

export default async function Lab({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const overview = await studioGet<StudioOverview>("/overview");
  const canal = str(params.canal);
  const channel = overview.channels.find((c) => c.id === canal) ?? overview.channels[0];
  if (!channel) {
    return <><PageHeader title="Títulos e thumbnails" /><Panel><Empty title="Nenhum canal cadastrado."><Link className="text-cobalt underline" href="/canais/novo">Cadastre um canal</Link> para usar o laboratório.</Empty></Panel></>;
  }
  const projectId = str(params.projeto);
  const offset = Number(str(params.inicio)) || 0;
  const project = projectId ? await intelGetOrNull<LabProject>(`/channels/${channel.id}/lab/projects/${projectId}`) : null;
  const list = projectId ? null : await intelGet<LabProjects>(`/channels/${channel.id}/lab/projects`, { offset: String(offset) });
  return (
    <>
      <PageHeader title="Títulos e thumbnails" intro="Gere alternativas, analise legibilidade e composição, e veja título e imagem juntos. As notas ajudam a revisar: não preveem resultado." />
      <form action="/lab" className="mb-4 flex flex-wrap items-center gap-2">
        <label htmlFor="canal-lab" className="text-sm text-ink-2">Canal</label>
        <select id="canal-lab" name="canal" defaultValue={channel.id} className="field max-w-72">{overview.channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <button className="min-h-9 rounded-md border border-line bg-surface px-3 text-sm hover:bg-page">Aplicar</button>
      </form>
      {projectId && !project && <Panel><Empty title="Projeto não encontrado neste canal."><Link className="text-cobalt underline" href={`/lab?canal=${channel.id}`}>Ver os projetos deste canal</Link></Empty></Panel>}
      {project && <ProjectView data={project} channel={channel.id} />}
      {list && (
        <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
          <Panel>
            {list.items.length ? (
              <ul className="divide-y divide-line">
                {list.items.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                    <Link className="font-medium text-cobalt underline underline-offset-2" href={`/lab?canal=${channel.id}&projeto=${item.id}`}>{item.subject}</Link>
                    <span className="text-ink-3">{item.variations} {item.variations === 1 ? "variação" : "variações"}, {dateTime(item.updated_at)}</span>
                  </li>
                ))}
              </ul>
            ) : <Empty title="Nenhum projeto neste canal.">Crie um projeto com o assunto do vídeo.</Empty>}
            <Pagination total={list.total} limit={list.limit} offset={list.offset} href={(next) => `/lab?canal=${channel.id}&inicio=${next}`} />
          </Panel>
          <Panel className="h-fit p-4">
            <SectionTitle>Novo projeto</SectionTitle>
            <ActionForm action={createLabProject} submit="Criar projeto" hidden={{ channel_id: channel.id, recommendation_id: str(params.ideia) ?? "" }} className="mt-3">
              <label className="mb-3 block text-[0.8125rem] text-ink-2">Assunto do vídeo<input name="subject" required minLength={3} maxLength={200} defaultValue={str(params.assunto)} className="field mt-1 w-full" /></label>
            </ActionForm>
          </Panel>
        </div>
      )}
    </>
  );
}

export const dynamic = "force-dynamic";
