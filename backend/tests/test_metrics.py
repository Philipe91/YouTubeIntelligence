from __future__ import annotations

import pytest

from app.metrics.acceleration import compute_acceleration
from app.metrics.classify import classify_format, parse_duration
from app.metrics.editorial import EditorialVideo, editorial_profile
from app.metrics.opportunity import OpportunityInput, SampleVideo, compute_opportunity, relevance_score
from app.metrics.outlier import compute_outlier, views_at_age
from app.metrics.trends import TrendInput, compute_trends
from app.metrics.vph import historical_average, latest_observed, observed_intervals

from .conftest import T0, make_series


# --- VPH -------------------------------------------------------------------------------------

def test_vph_is_delta_views_over_interval(scoring):
    series = make_series(points=[(10, 1000), (12, 1300)])
    assert latest_observed(series, scoring["vph"]).vph == pytest.approx(150.0)


def test_vph_needs_two_snapshots(scoring):
    assert latest_observed(make_series(points=[(10, 1000)]), scoring["vph"]) is None


def test_vph_ignores_snapshots_with_hidden_views(scoring):
    series = make_series(points=[(10, 1000), (11, None), (12, 1300)])
    intervals = observed_intervals(series, scoring["vph"])
    assert len(intervals) == 1
    assert intervals[0].hours == pytest.approx(2.0)


def test_vph_count_decrease_has_no_value_and_is_flagged(scoring):
    interval = observed_intervals(make_series(points=[(10, 1000), (12, 900)]), scoring["vph"])[0]
    assert interval.vph is None
    assert "contagem_diminuiu" in interval.flags


def test_vph_short_interval_is_rejected(scoring):
    interval = observed_intervals(make_series(points=[(10, 1000), (10.1, 1100)]), scoring["vph"])[0]
    assert interval.vph is None
    assert "intervalo_curto" in interval.flags


def test_vph_flags_long_interval_but_keeps_value(scoring):
    interval = observed_intervals(make_series(points=[(0, 0), (100, 1000)]), scoring["vph"])[0]
    assert interval.vph == pytest.approx(10.0)
    assert "intervalo_longo" in interval.flags


def test_vph_flags_interval_crossing_count_change(scoring):
    from datetime import UTC, datetime

    series = make_series(published=datetime(2026, 8, 23, tzinfo=UTC), points=[(0, 0), (48, 480)])
    assert "cruza_mudanca_de_contagem" in observed_intervals(series, scoring["vph"])[0].flags


def test_historical_average_differs_from_observed(scoring):
    from datetime import timedelta

    series = make_series(points=[(100, 10000), (102, 10010)])
    observed = latest_observed(series, scoring["vph"]).vph
    average = historical_average(10010, T0, T0 + timedelta(hours=102))
    assert observed == pytest.approx(5.0)
    assert average == pytest.approx(98.137, rel=1e-3)


def test_historical_average_handles_missing_and_future():
    from datetime import timedelta

    assert historical_average(None, T0, T0) is None
    assert historical_average(10, T0, T0 - timedelta(hours=1)) is None


# --- IDR -------------------------------------------------------------------------------------

def _peers(values, fmt="long", channel="c", hours=48):
    return [
        make_series(video_id=f"p{i}", channel=channel, fmt=fmt, points=[(hours, v)])
        for i, v in enumerate(values)
    ]


def test_idr_uses_median_of_same_age_peers(scoring):
    target = make_series(video_id="t", points=[(48, 5000)])
    result = compute_outlier(target, _peers([1000, 1000, 1000, 2000, 500]), scoring["outlier"])
    assert result.status == "ok"
    assert result.idr == pytest.approx(5.0)
    assert result.peer_median_views == 1000
    assert result.sample_size == 5


def test_idr_is_robust_to_one_huge_peer(scoring):
    target = make_series(video_id="t", points=[(48, 2000)])
    result = compute_outlier(target, _peers([1000, 1000, 1000, 1000, 10_000_000]), scoring["outlier"])
    assert result.idr == pytest.approx(2.0)


def test_idr_flags_insufficient_sample(scoring):
    target = make_series(video_id="t", points=[(48, 5000)])
    result = compute_outlier(target, _peers([1000, 1000]), scoring["outlier"])
    assert result.status == "insufficient_sample"
    assert result.idr is None
    assert result.sample_size == 2


def test_idr_excludes_other_formats_and_channels_and_self(scoring):
    target = make_series(video_id="t", points=[(48, 5000)])
    peers = _peers([1000] * 5, fmt="short") + _peers([1000] * 5, channel="outro") + [target]
    assert compute_outlier(target, peers, scoring["outlier"]).status == "insufficient_sample"


def test_idr_compares_at_same_age_not_current_views(scoring):
    # Pares antigos têm muitas views hoje, mas a comparação usa o valor deles às 48 h.
    target = make_series(video_id="t", points=[(48, 3000)])
    peers = [
        make_series(video_id=f"p{i}", points=[(24, 500), (72, 1500), (2000, 900_000)])
        for i in range(5)
    ]
    result = compute_outlier(target, peers, scoring["outlier"])
    assert result.peer_median_views == pytest.approx(1000)
    assert result.idr == pytest.approx(3.0)
    assert result.measured_peers == 5


def test_idr_does_not_extrapolate_peer_younger_than_target(scoring):
    target = make_series(video_id="t", points=[(480, 3000)])
    peers = _peers([100] * 5, hours=48)
    result = compute_outlier(target, peers, scoring["outlier"])
    assert result.status == "insufficient_sample"


def test_idr_uses_age_band_as_lower_quality_fallback(scoring):
    target = make_series(video_id="t", points=[(100, 3000)])
    # Idade 130 h: fora da tolerância de 15%, dentro da faixa de 1,5x.
    result = compute_outlier(target, _peers([1000] * 5, hours=130), scoring["outlier"])
    assert result.status == "ok"
    assert result.band_peers == 5
    assert result.measured_peers == 0
    assert result.confidence == "baixa"


def test_idr_too_young(scoring):
    target = make_series(video_id="t", points=[(2, 500)])
    result = compute_outlier(target, _peers([100] * 5, hours=2), scoring["outlier"])
    assert result.status == "too_young"
    assert result.idr is None


def test_idr_without_views(scoring):
    target = make_series(video_id="t", points=[(48, None)])
    assert compute_outlier(target, _peers([100] * 5), scoring["outlier"]).status == "no_views"


def test_idr_unknown_format(scoring):
    target = make_series(video_id="t", fmt="unknown", points=[(48, 100)])
    assert compute_outlier(target, [], scoring["outlier"]).status == "unknown_format"


def test_idr_zero_median_is_not_a_division_error(scoring):
    target = make_series(video_id="t", points=[(48, 100)])
    result = compute_outlier(target, _peers([0] * 5), scoring["outlier"])
    assert result.status == "ok"
    assert result.idr is None
    assert "mediana_zero" in result.warnings


def test_idr_zero_dispersion_has_no_z(scoring):
    target = make_series(video_id="t", points=[(48, 2000)])
    result = compute_outlier(target, _peers([1000] * 5), scoring["outlier"])
    assert result.robust_z is None
    assert "dispersao_zero" in result.warnings


def test_idr_confidence_levels(scoring):
    target = make_series(video_id="t", points=[(48, 2000)])
    values = list(range(1000, 1016))
    assert compute_outlier(target, _peers(values), scoring["outlier"]).confidence == "alta"
    assert compute_outlier(target, _peers(values[:8]), scoring["outlier"]).confidence == "media"
    assert compute_outlier(target, _peers(values[:5]), scoring["outlier"]).confidence == "baixa"


def test_explanations_use_brazilian_number_format_without_touching_prose(scoring):
    target = make_series(video_id="t", points=[(48, 1234567)])
    text = compute_outlier(target, _peers([1000] * 5), scoring["outlier"]).explanation
    assert "1.234.567 views" in text
    assert "(5 medidos, 0 por faixa de idade)" in text
    accelerating = make_series(points=[(100, 1000), (124, 1240), (148, 1730)])
    assert "20,4 views/h" in compute_acceleration(accelerating, scoring["acceleration"]).explanation
    data = OpportunityInput("tema", "short", _sample(30, views=25000), (), 1000)
    joined = " ".join(compute_opportunity(data, scoring["opportunity"]).justification)
    assert "2.500 views por dia" in joined
    assert "(proxy de demanda, não é volume de busca)" in joined


def test_views_at_age_rejects_wide_gap(scoring):
    series = make_series(points=[(1, 10), (5000, 50000)])
    assert views_at_age(series, 2000, scoring["outlier"]) is None


# --- Aceleração --------------------------------------------------------------------------------

def test_acceleration_detected(scoring):
    series = make_series(points=[(100, 1000), (124, 1240), (148, 1720)])
    result = compute_acceleration(series, scoring["acceleration"])
    assert result.status == "acelerando"
    assert result.previous_vph == pytest.approx(10.0)
    assert result.recent_vph == pytest.approx(20.0)
    assert result.ratio == pytest.approx(2.0)


def test_deceleration_detected(scoring):
    series = make_series(points=[(100, 1000), (124, 1480), (148, 1720)])
    assert compute_acceleration(series, scoring["acceleration"]).status == "desacelerando"


def test_stable(scoring):
    series = make_series(points=[(100, 1000), (124, 1240), (148, 1480)])
    assert compute_acceleration(series, scoring["acceleration"]).status == "estavel"


def test_acceleration_interpolates_window_edges(scoring):
    series = make_series(points=[(90, 900), (110, 1100), (130, 1300), (148, 1900)])
    result = compute_acceleration(series, scoring["acceleration"])
    assert result.previous_vph == pytest.approx(10.0)
    assert result.status == "acelerando"


def test_acceleration_needs_coverage(scoring):
    assert compute_acceleration(make_series(points=[(1, 1), (2, 2)]), scoring["acceleration"]).status == "dados_insuficientes"
    series = make_series(points=[(146, 1), (147, 2), (148, 3)])
    assert compute_acceleration(series, scoring["acceleration"]).status == "dados_insuficientes"


def test_acceleration_rejects_count_decrease(scoring):
    series = make_series(points=[(100, 1000), (124, 1240), (148, 1000)])
    result = compute_acceleration(series, scoring["acceleration"])
    assert result.status == "dados_insuficientes"
    assert "contagem_diminuiu" in result.warnings


def test_acceleration_emerging_from_zero(scoring):
    series = make_series(points=[(100, 50), (124, 50), (148, 200)])
    result = compute_acceleration(series, scoring["acceleration"])
    assert result.status == "emergente"
    assert result.ratio is None


def test_acceleration_rejects_window_crossing_count_change(scoring):
    from datetime import UTC, datetime

    series = make_series(published=datetime(2026, 8, 22, tzinfo=UTC), points=[(24, 100), (48, 200), (72, 500)])
    result = compute_acceleration(series, scoring["acceleration"])
    assert result.status == "dados_insuficientes"
    assert "cruza_mudanca_de_contagem" in result.warnings


# --- Tendências --------------------------------------------------------------------------------

def _trend(vid, channel, title, status="acelerando", fmt="short", recent=20.0, previous=10.0):
    return TrendInput(vid, channel, title, fmt, status, recent, previous)


def test_trend_requires_multiple_channels(scoring):
    items = [_trend(str(i), "a", "roma antiga") for i in range(4)]
    assert compute_trends(items, scoring["trends"]) == []


def test_trend_found_and_formats_separated(scoring):
    items = [_trend("1", "a", "Roma antiga"), _trend("2", "b", "Roma e Grécia"), _trend("3", "c", "A queda de Roma"),
             _trend("4", "d", "Roma longo", fmt="long")]
    result = compute_trends(items, scoring["trends"])
    roma = [t for t in result if t.term == "roma"]
    assert len(roma) == 1
    assert roma[0].format == "short"
    assert roma[0].videos == 3
    assert roma[0].velocity_ratio == pytest.approx(2.0)


def test_trend_ignores_videos_without_acceleration_data(scoring):
    items = [_trend(str(i), str(i), "roma", recent=None, previous=None) for i in range(5)]
    assert compute_trends(items, scoring["trends"]) == []


# --- Oportunidade --------------------------------------------------------------------------------

def _sample(n, channels=12, views=10000, age=10, subs=50000, snaps=3, fmt="short"):
    return tuple(SampleVideo(f"v{i}", f"c{i % channels}", views, age, subs, snaps, fmt) for i in range(n))


def test_opportunity_indicators_are_separate_and_scored(scoring):
    data = OpportunityInput("império romano", "short", _sample(30), ("história", "império romano"), 5000)
    result = compute_opportunity(data, scoring["opportunity"])
    assert result.status == "ok"
    assert result.demand is not None and result.competition is not None
    assert result.relevance == pytest.approx(100.0)
    assert result.confidence == pytest.approx(100.0)
    cfg = scoring["opportunity"]
    expected = cfg["weight_demand"] * result.demand + cfg["weight_competition"] * (100 - result.competition) + cfg["weight_relevance"] * 100
    assert result.score == pytest.approx(expected)


def test_opportunity_low_confidence_has_no_score(scoring):
    data = OpportunityInput("tema", "short", _sample(3, channels=1, snaps=1), (), None)
    result = compute_opportunity(data, scoring["opportunity"])
    assert result.status == "amostra_insuficiente"
    assert result.score is None
    assert any("Confiança" in line for line in result.justification)


def test_opportunity_empty_sample(scoring):
    result = compute_opportunity(OpportunityInput("tema", "short", (), (), None), scoring["opportunity"])
    assert result.score is None
    assert result.demand is None
    assert result.confidence == 0


def test_opportunity_ignores_other_format(scoring):
    data = OpportunityInput("tema", "long", _sample(30, fmt="short"), (), 100)
    assert compute_opportunity(data, scoring["opportunity"]).sample_size == 0


def test_opportunity_missing_subscribers_redistributes_weights(scoring):
    data = OpportunityInput("tema", "short", _sample(30, subs=None), (), 1000)
    result = compute_opportunity(data, scoring["opportunity"])
    assert "porte_dos_canais" not in result.competition_parts
    assert result.competition is not None
    assert any("Inscritos indisponíveis" in line for line in result.justification)


def test_opportunity_never_promises_virality(scoring):
    data = OpportunityInput("tema", "short", _sample(30), ("tema",), 1000)
    text = " ".join(compute_opportunity(data, scoring["opportunity"]).justification).lower()
    assert "viral" not in text
    assert "garant" not in text


def test_relevance_uses_accent_insensitive_tokens():
    assert relevance_score("História de Roma", ("historia", "roma")) == pytest.approx(100.0)
    assert relevance_score("Culinária", ("historia",)) == 0.0


# --- Editorial e classificação -------------------------------------------------------------------

def test_editorial_separates_formats_and_measures_cadence():
    from datetime import timedelta

    videos = [EditorialVideo(str(i), f"Roma {i}?", "short", T0 + timedelta(days=i * 7), 60, 1.0) for i in range(4)]
    videos.append(EditorialVideo("x", "Longo", "long", T0, 900, 1.0))
    profile = editorial_profile(videos, "short")
    assert profile.sample_size == 4
    assert profile.uploads_per_week == pytest.approx(1.0)
    assert profile.question_title_share == 1.0
    assert editorial_profile([], "long").sample_size == 0


def test_editorial_overperforming_terms():
    from datetime import timedelta

    idrs = [("Roma antiga", 5.0), ("Roma imperial", 6.0), ("Egito antigo", 1.0), ("Grécia clássica", 1.0), ("Pérsia real", 1.0)]
    videos = [EditorialVideo(str(i), title, "long", T0 + timedelta(days=i), 900, idr) for i, (title, idr) in enumerate(idrs)]
    top = editorial_profile(videos, "long").overperforming_terms
    assert top[0]["term"] == "roma"
    assert top[0]["lift"] > 1


@pytest.mark.parametrize("value,expected", [
    ("PT1H2M3S", 3723), ("PT59S", 59), ("P1DT1S", 86401), ("PT0S", 0), (None, None), ("", None), ("abc", None), ("P", None), ("PT", None),
])
def test_parse_duration(value, expected):
    assert parse_duration(value) == expected


def test_classify_format_labels_source():
    assert classify_format(60, 180) == ("short", "duration")
    assert classify_format(181, 180) == ("long", "duration")
    assert classify_format(600, 180, analytics_content_type="SHORTS") == ("short", "analytics")
    assert classify_format(600, 180, has_live_details=True) == ("live", "broadcast")
    assert classify_format(None, 180) == ("unknown", "missing")
    assert classify_format(0, 180) == ("unknown", "missing")
