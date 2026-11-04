"""Title & Thumbnail Lab: analisa títulos e imagens que são seus, por regras explicadas.

As notas ajudam a revisar o pacote. Nunca foram calibradas com resultado real e não preveem CTR nem
viralização. Não usa dados da API do YouTube, então vale em qualquer modo. Não gera imagens, não faz OCR
e não detecta rostos: mede contraste, brilho, saturação, complexidade e distribuição de detalhes.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

from ..config import Settings
from ..db import to_iso
from ..metrics.text import tokens
from ..studio.store import StudioError, get_channel, new_id
from . import titles

NOTE = "Nota de revisão por regras. Não foi calibrada com resultados reais e não prevê CTR, views ou viralização."
TITLE_LIMIT = 100
TITLE_COMFORT = 60
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
FORMATS = {"JPEG", "PNG", "WEBP"}
ANALYSIS_WIDTH = 640
SMALL_SIZE = (168, 94)
RECOMMENDED = (1280, 720)
FILE_NAME = re.compile(r"^var_[0-9a-f]{16}\.jpg$")

CURIOSITY = re.compile(r"\?|por que|por quê|porque|como |segredo|ninguém|quase ninguém|verdade|mito|estranh|inesperad|why|how |secret|nobody|truth|myth|strange|qué|cómo|nadie|secreto|verdad", re.I)
PROMISE_WORDS = re.compile(r"\d|explicad|entenda|aprenda|guia|história de|o dia em que|como |explained|guide|how |the day|the story|cómo|guía|historia de", re.I)
CLICKBAIT = re.compile(r"você não vai acreditar|chocante|inacreditável|urgente|bizarro demais|you won.t believe|shocking|no vas a creer|impactante", re.I)


def _clamp(value: float) -> int:
    return round(max(0.0, min(100.0, value)))


def _criterion(key: str, label: str, score: float, explanation: str) -> dict:
    return {"key": key, "label": label, "score": _clamp(score), "explanation": explanation}


def evaluate_title(title: str, subject: str = "") -> dict:
    text = " ".join((title or "").split())
    if not text:
        raise StudioError("invalid_field", "Escreva um título.")
    chars, words = len(text), text.split()
    warnings: list[str] = []
    if chars > TITLE_LIMIT:
        warnings.append(f"O título tem {chars} caracteres: o YouTube aceita até {TITLE_LIMIT}.")
    elif chars > TITLE_COMFORT:
        warnings.append(f"Com {chars} caracteres, o fim pode ser cortado em telas pequenas. O corte varia com o aparelho.")

    length = 100 if chars <= TITLE_COMFORT else max(0, 100 - (chars - TITLE_COMFORT) * 2.5)
    length_text = f"{chars} caracteres. Até {TITLE_COMFORT} tende a aparecer inteiro; o limite do YouTube é {TITLE_LIMIT}."

    caps = sum(1 for w in words if len(w) > 2 and w.isupper())
    symbols = len(re.findall(r"[!]{2,}|[?]{2,}|[#$%*]", text))
    clarity = 100 - max(0, len(words) - 12) * 8 - (15 if len(words) < 3 else 0) - caps * 15 - symbols * 15
    clarity_parts = [f"{len(words)} palavras"]
    if caps:
        clarity_parts.append(f"{caps} em maiúsculas")
        warnings.append("Palavras inteiras em maiúsculas dificultam a leitura.")
    if symbols:
        clarity_parts.append("símbolos repetidos")

    curiosity_hit = bool(CURIOSITY.search(text))
    promise_hit = bool(PROMISE_WORDS.search(text))
    if CLICKBAIT.search(text):
        warnings.append("Expressão exagerada: confira se o vídeo entrega o que o título promete.")

    criteria = [
        _criterion("tamanho", "Tamanho", length, length_text),
        _criterion("clareza", "Clareza", clarity, f"{', '.join(clarity_parts).capitalize()}."),
        _criterion("curiosidade", "Curiosidade", 85 if curiosity_hit else 45, "Abre uma pergunta ou uma lacuna." if curiosity_hit else "Não abre pergunta nem lacuna evidente."),
        _criterion("promessa", "Promessa", 85 if promise_hit else 50, "Indica o que a pessoa vai encontrar." if promise_hit else "Não deixa claro o que o vídeo entrega."),
    ]
    wanted = set(tokens(subject))
    if wanted:
        shared = wanted & set(tokens(text))
        criteria.append(_criterion("assunto", "Consistência com o assunto", 100 * len(shared) / len(wanted),
                                   f"Usa {len(shared)} de {len(wanted)} palavras do assunto." if shared else "Não usa nenhuma palavra do assunto."))
        if not shared:
            warnings.append("O título não menciona o assunto informado.")
    return {"title": text, "characters": chars, "words": len(words), "criteria": criteria, "warnings": warnings,
            "review_score": _clamp(sum(c["score"] for c in criteria) / len(criteria)), "note": NOTE}


def suggest_titles(subject: str, language: str = "pt", forbidden: set[str] | None = None, niche: str | None = None, avoid: list[str] | None = None, video_format: str = "long") -> list[dict]:
    """Três alternativas de ângulos diferentes, revisadas. Título igual ao de um vídeo coletado é trocado."""
    text = " ".join((subject or "").split())
    if not 3 <= len(text) <= 200:
        raise StudioError("invalid_field", "Informe o assunto em 3 a 200 caracteres.")
    return [{**item, **evaluate_title(item["title"], text)} for item in titles.build_titles(text, language, video_format, niche, forbidden, avoid)]


def ai_variations(studio: sqlite3.Connection, provider, channel_id: str, project_id: str, forbidden: set[str] | None, now: datetime) -> dict:
    """Só por pedido explícito, porque tem custo. Cada alternativa vira uma variação, com o motivo na nota."""
    project = _project(studio, channel_id, project_id)
    channel = get_channel(studio, channel_id)
    options, usage = titles.ai_titles(provider, project["subject"], channel["language"], channel, forbidden)
    created = []
    for item in options:
        origin = "Sugestão por regras" if item["origin"] == "regras" else "Sugestão do Claude"
        created.append(add_variation(studio, channel_id, project_id, item["title"], f"{origin}: {item['why']}", now))
    return {"created": len(created), "usage": usage, "note": titles.NO_EVIDENCE}


# --- Imagem ---------------------------------------------------------------------------------------

def _spread(gray: Image.Image) -> float:
    """Distância entre os percentis 5 e 95 do brilho, de 0 a 255. Resiste a poucos pixels extremos."""
    histogram = gray.histogram()
    total = sum(histogram)
    low_target, high_target = total * 0.05, total * 0.95
    running, low, high = 0, 0, 255
    found_low = False
    for level, count in enumerate(histogram):
        running += count
        if not found_low and running >= low_target:
            low, found_low = level, True
        if running >= high_target:
            high = level
            break
    return float(high - low)


def _edge_map(gray: Image.Image) -> Image.Image:
    return gray.filter(ImageFilter.FIND_EDGES).crop((1, 1, gray.width - 1, gray.height - 1))


def _grid(edges: Image.Image) -> list[float]:
    """Energia de bordas em cada célula de uma grade 3 x 3."""
    cells = []
    for row in range(3):
        for column in range(3):
            box = (edges.width * column // 3, edges.height * row // 3, edges.width * (column + 1) // 3, edges.height * (row + 1) // 3)
            cells.append(ImageStat.Stat(edges.crop(box)).mean[0])
    return cells


ROW_NAMES = ("no alto", "no meio", "embaixo")
COLUMN_NAMES = ("à esquerda", "ao centro", "à direita")


def analyze_image(data: bytes) -> tuple[Image.Image, dict]:
    if len(data) > MAX_IMAGE_BYTES:
        raise StudioError("image_too_large", "A imagem passa de 5 MB.", 413)
    if not data:
        raise StudioError("invalid_image", "Nenhuma imagem enviada.")
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.format not in FORMATS:
            raise StudioError("invalid_image", "Use uma imagem JPEG, PNG ou WebP.", 415)
        if probe.width * probe.height > MAX_PIXELS:
            raise StudioError("image_too_large", "A imagem tem pixels demais.", 413)
        width, height, source_format = probe.width, probe.height, probe.format
        # draft reduz o custo de memória de JPEG grande; thumbnail cobre os outros formatos.
        probe.draft("RGB", (ANALYSIS_WIDTH * 2, ANALYSIS_WIDTH * 2))
        image = probe.convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise StudioError("invalid_image", "O arquivo não é uma imagem válida.", 415) from error
    image.thumbnail((ANALYSIS_WIDTH, ANALYSIS_WIDTH * 2))
    gray = image.convert("L")
    brightness = ImageStat.Stat(gray).mean[0]
    spread = _spread(gray)
    saturation = ImageStat.Stat(image.convert("HSV").getchannel("S")).mean[0]
    edges = _edge_map(gray)
    complexity = ImageStat.Stat(edges).mean[0]
    cells = _grid(edges)
    total_energy = sum(cells)

    small = gray.resize(SMALL_SIZE, Image.Resampling.LANCZOS)
    small_edges = ImageStat.Stat(_edge_map(small)).mean[0]
    small_spread = _spread(small)

    ratio = width / height
    criteria = [
        _criterion("proporcao", "Proporção", max(0, 100 - abs(ratio - 16 / 9) * 200), f"{width} x {height} pixels. O formato de vídeo longo no YouTube é 16:9."),
        _criterion("contraste", "Contraste", spread / 180 * 100, "Boa separação entre claros e escuros." if spread >= 140 else "Claros e escuros próximos: a imagem pode parecer lavada em tela pequena."),
        _criterion("brilho", "Brilho", 100 - max(0, abs(brightness - 125) - 45) * 1.6, f"Brilho médio de {brightness:.0f} em 255." + (" Escura demais." if brightness < 60 else " Clara demais." if brightness > 190 else "")),
        _criterion("saturacao", "Saturação", min(100, saturation / 90 * 100), "Cores vivas." if saturation >= 90 else "Cores discretas. Pode ser uma escolha de estilo."),
    ]
    if complexity < 4:
        criteria.append(_criterion("complexidade", "Complexidade", 35, "Quase sem detalhes: não há um elemento que se destaque."))
    else:
        criteria.append(_criterion("complexidade", "Complexidade", 100 - max(0, complexity - 28) * 3, "Detalhes em quantidade razoável." if complexity <= 28 else "Muitos detalhes competindo: em tamanho pequeno, tende a virar ruído."))

    if total_energy < 1:
        focus_text, hierarchy = "Sem elemento dominante.", 20.0
    else:
        strongest = max(range(9), key=lambda i: cells[i])
        share = cells[strongest] / total_energy
        focus_text = f"Mais detalhes {ROW_NAMES[strongest // 3]}, {COLUMN_NAMES[strongest % 3]}, com {share * 100:.0f}% dos detalhes."
        hierarchy = (share - 1 / 9) / (0.30 - 1 / 9) * 100
    criteria.append(_criterion("hierarquia", "Hierarquia e composição", hierarchy, focus_text + " Quanto mais concentrado, mais fácil achar o foco."))
    criteria.append(_criterion("legibilidade", "Leitura em tamanho pequeno", min(small_spread / 140 * 60 + min(small_edges, 25) / 25 * 40, 100), f"Reduzida a {SMALL_SIZE[0]} x {SMALL_SIZE[1]}, como em uma lista lateral. Mede contraste e detalhe restantes, sem ler texto."))

    warnings = []
    if width < RECOMMENDED[0] or height < RECOMMENDED[1]:
        warnings.append(f"Resolução de {width} x {height}: abaixo de {RECOMMENDED[0]} x {RECOMMENDED[1]}, a imagem pode perder nitidez.")
    if abs(ratio - 16 / 9) > 0.05:
        warnings.append("Fora de 16:9: o YouTube pode acrescentar faixas ou cortar a imagem.")
    return image, {
        "width": width, "height": height, "format": source_format, "bytes": len(data), "criteria": criteria, "warnings": warnings,
        "review_score": _clamp(sum(c["score"] for c in criteria) / len(criteria)),
        "limits": ["Não lê texto na imagem.", "Não detecta rostos.", "Não compara com outras thumbnails."], "note": NOTE,
    }


# --- Projetos -------------------------------------------------------------------------------------

def _project(studio: sqlite3.Connection, channel_id: str, project_id: str) -> sqlite3.Row:
    row = studio.execute("SELECT * FROM lab_projects WHERE id = ? AND channel_id = ?", (project_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("project_not_found", "Projeto não encontrado neste canal.", 404)
    return row


def _variation(studio: sqlite3.Connection, channel_id: str, variation_id: str) -> sqlite3.Row:
    row = studio.execute("SELECT v.* FROM lab_variations v JOIN lab_projects p ON p.id = v.project_id WHERE v.id = ? AND p.channel_id = ?", (variation_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("variation_not_found", "Variação não encontrada neste canal.", 404)
    return row


def create_project(studio: sqlite3.Connection, channel_id: str, subject: str, recommendation_id: str | None, now: datetime) -> dict:
    get_channel(studio, channel_id)
    text = " ".join((subject or "").split())
    if not 3 <= len(text) <= 200:
        raise StudioError("invalid_field", "Informe o assunto do vídeo em 3 a 200 caracteres.")
    if recommendation_id and studio.execute("SELECT 1 FROM recommendations WHERE id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone() is None:
        raise StudioError("recommendation_not_in_channel", "A ideia não pertence a este canal.", 404)
    identifier = new_id("lab")
    studio.execute("INSERT INTO lab_projects (id, channel_id, subject, recommendation_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (identifier, channel_id, text, recommendation_id, to_iso(now), to_iso(now)))
    studio.commit()
    return {"id": identifier, "subject": text}


def list_projects(studio: sqlite3.Connection, channel_id: str, limit: int = 30, offset: int = 0) -> dict:
    get_channel(studio, channel_id)
    rows = studio.execute("""SELECT p.*, COUNT(v.id) AS variations FROM lab_projects p LEFT JOIN lab_variations v ON v.project_id = p.id
                             WHERE p.channel_id = ? GROUP BY p.id ORDER BY p.updated_at DESC, p.id LIMIT ? OFFSET ?""", (channel_id, limit, offset)).fetchall()
    total = studio.execute("SELECT COUNT(*) AS n FROM lab_projects WHERE channel_id = ?", (channel_id,)).fetchone()["n"]
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


def _variation_view(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["title_eval"] = json.loads(data.pop("title_eval_json"))
    raw = data.pop("image_eval_json")
    data["image_eval"] = json.loads(raw) if raw else None
    data["favorite"] = bool(data["favorite"])
    return data


def get_project(studio: sqlite3.Connection, channel_id: str, project_id: str, forbidden: set[str] | None = None) -> dict:
    project = dict(_project(studio, channel_id, project_id))
    channel = get_channel(studio, channel_id)
    rows = studio.execute("SELECT * FROM lab_variations WHERE project_id = ? ORDER BY favorite DESC, created_at, id", (project_id,)).fetchall()
    return {"project": project, "channel_name": channel["name"], "variations": [_variation_view(r) for r in rows],
            "suggestions": suggest_titles(project["subject"], channel["language"], forbidden, channel.get("niche"), channel.get("avoid")), "titles_note": titles.NO_EVIDENCE, "note": NOTE}


def _touch(studio: sqlite3.Connection, project_id: str, now: datetime) -> None:
    studio.execute("UPDATE lab_projects SET updated_at = ? WHERE id = ?", (to_iso(now), project_id))


def add_variation(studio: sqlite3.Connection, channel_id: str, project_id: str, title: str, note: str, now: datetime) -> dict:
    project = _project(studio, channel_id, project_id)
    evaluation = evaluate_title(title, project["subject"])
    identifier = new_id("var")
    studio.execute("INSERT INTO lab_variations (id, project_id, title, title_eval_json, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (identifier, project_id, evaluation["title"], json.dumps(evaluation, ensure_ascii=False), note.strip()[:1000], to_iso(now)))
    _touch(studio, project_id, now)
    studio.commit()
    return _variation_view(_variation(studio, channel_id, identifier))


def _image_dir(settings: Settings, channel_id: str) -> Path:
    return settings.data_dir / "lab" / channel_id


def attach_image(studio: sqlite3.Connection, settings: Settings, channel_id: str, variation_id: str, data: bytes, now: datetime) -> dict:
    """Salva uma cópia reduzida, sem metadados, com nome gerado aqui. O nome original é ignorado."""
    row = _variation(studio, channel_id, variation_id)
    image, evaluation = analyze_image(data)
    folder = _image_dir(settings, channel_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{variation_id}.jpg"
    image.save(folder / name, "JPEG", quality=85, optimize=True)
    studio.execute("UPDATE lab_variations SET image_file = ?, image_eval_json = ? WHERE id = ?", (name, json.dumps(evaluation, ensure_ascii=False), variation_id))
    _touch(studio, row["project_id"], now)
    studio.commit()
    return _variation_view(_variation(studio, channel_id, variation_id))


def image_path(studio: sqlite3.Connection, settings: Settings, channel_id: str, file_name: str) -> Path:
    if not FILE_NAME.match(file_name):
        raise StudioError("not_found", "Imagem não encontrada.", 404)
    owner = studio.execute("SELECT 1 FROM lab_variations v JOIN lab_projects p ON p.id = v.project_id WHERE v.image_file = ? AND p.channel_id = ?", (file_name, channel_id)).fetchone()
    path = _image_dir(settings, channel_id) / file_name
    if owner is None or not path.is_file():
        raise StudioError("not_found", "Imagem não encontrada.", 404)
    return path


def update_variation(studio: sqlite3.Connection, channel_id: str, variation_id: str, *, note: str | None, favorite: bool | None, now: datetime) -> dict:
    row = _variation(studio, channel_id, variation_id)
    if note is not None:
        studio.execute("UPDATE lab_variations SET note = ? WHERE id = ?", (note.strip()[:1000], variation_id))
    if favorite is not None:
        studio.execute("UPDATE lab_variations SET favorite = ? WHERE id = ?", (int(favorite), variation_id))
    _touch(studio, row["project_id"], now)
    studio.commit()
    return _variation_view(_variation(studio, channel_id, variation_id))


def _unlink(settings: Settings, channel_id: str, file_name: str | None) -> None:
    if file_name and FILE_NAME.match(file_name):
        (_image_dir(settings, channel_id) / file_name).unlink(missing_ok=True)


def delete_variation(studio: sqlite3.Connection, settings: Settings, channel_id: str, variation_id: str) -> None:
    row = _variation(studio, channel_id, variation_id)
    studio.execute("DELETE FROM lab_variations WHERE id = ?", (variation_id,))
    studio.commit()
    _unlink(settings, channel_id, row["image_file"])


def delete_project(studio: sqlite3.Connection, settings: Settings, channel_id: str, project_id: str) -> None:
    _project(studio, channel_id, project_id)
    files = [r["image_file"] for r in studio.execute("SELECT image_file FROM lab_variations WHERE project_id = ?", (project_id,))]
    studio.execute("DELETE FROM lab_projects WHERE id = ?", (project_id,))
    studio.commit()
    for name in files:
        _unlink(settings, channel_id, name)
