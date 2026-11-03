"""Padrões editoriais de um canal: cadência, duração, títulos, termos com melhor desempenho."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .core import hours_between, median
from .text import terms, tokens

WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(frozen=True)
class EditorialVideo:
    video_id: str
    title: str
    format: str
    published_at: datetime
    duration_seconds: int | None
    idr: float | None


@dataclass(frozen=True)
class EditorialProfile:
    format: str
    sample_size: int
    uploads_per_week: float | None
    median_gap_days: float | None
    median_duration_seconds: float | None
    median_title_words: float | None
    question_title_share: float | None
    number_title_share: float | None
    top_weekday: str | None
    top_terms: tuple[tuple[str, int], ...]
    overperforming_terms: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def editorial_profile(videos: list[EditorialVideo], video_format: str, min_term_videos: int = 2) -> EditorialProfile:
    sample = sorted((v for v in videos if v.format == video_format), key=lambda v: v.published_at)
    n = len(sample)
    if n == 0:
        return EditorialProfile(video_format, 0, None, None, None, None, None, None, None, (), ())

    gaps = [hours_between(a.published_at, b.published_at) / 24 for a, b in zip(sample, sample[1:])]
    span_days = sum(gaps)
    durations = [float(v.duration_seconds) for v in sample if v.duration_seconds is not None]
    weekdays = Counter(WEEKDAYS[v.published_at.weekday()] for v in sample)
    term_counts: Counter[str] = Counter()
    for video in sample:
        term_counts.update(terms(video.title))

    return EditorialProfile(
        format=video_format, sample_size=n,
        uploads_per_week=(len(gaps) / span_days * 7) if span_days > 0 else None,
        median_gap_days=median(gaps) if gaps else None,
        median_duration_seconds=median(durations) if durations else None,
        median_title_words=median([float(len(v.title.split())) for v in sample]),
        question_title_share=sum("?" in v.title for v in sample) / n,
        number_title_share=sum(any(ch.isdigit() for ch in v.title) for v in sample) / n,
        top_weekday=weekdays.most_common(1)[0][0],
        top_terms=tuple(term_counts.most_common(8)),
        overperforming_terms=tuple(_overperforming(sample, min_term_videos)),
    )


def _overperforming(sample: list[EditorialVideo], min_term_videos: int) -> list[dict[str, Any]]:
    """Termos cujo IDR mediano supera o do canal. Correlação, não causa."""
    scored = [v for v in sample if v.idr is not None]
    if len(scored) < 2 * min_term_videos:
        return []
    overall = median([v.idr for v in scored])
    by_term: dict[str, list[float]] = {}
    for video in scored:
        for word in set(tokens(video.title)):
            by_term.setdefault(word, []).append(video.idr)
    rows = []
    for term, values in by_term.items():
        if min_term_videos <= len(values) < len(scored):
            term_median = median(values)
            if overall > 0 and term_median > overall:
                rows.append({"term": term, "videos": len(values), "median_idr": term_median,
                             "lift": term_median / overall})
    rows.sort(key=lambda row: (-row["lift"], row["term"]))
    return rows[:6]
