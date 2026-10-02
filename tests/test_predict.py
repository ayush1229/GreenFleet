from dataclasses import replace
import pytest


def test_no_preprocessing_leakage():
    from greenfleet.ingest import demo_dataset
    from greenfleet.splits import make_splits
    from greenfleet.predict import fit_predictor
    d = demo_dataset()
    split = make_splits(d, "future", 0)
    p = fit_predictor(d, split, "direct", 1, 1)
    altered = replace(d, observations=tuple(replace(o, wave_m=999, fuel_mass_kg=1e9) if o.id in split.test else o for o in d.observations))
    q = fit_predictor(altered, split, "direct", 1, 1)
    assert p.model_id == q.model_id
    assert p.preprocessing_statistics == q.preprocessing_statistics
    assert set(p.fit_ids) == set(split.train)
    assert not set(p.calibration_ids) & set(p.fit_ids)


def test_unsupported_speed():
    from greenfleet.ingest import demo_dataset
    from greenfleet.splits import make_splits
    from greenfleet.predict import fit_predictor, point_from_observation
    d = demo_dataset()
    p = fit_predictor(d, make_splits(d, "future", 0), "direct", 1, 0)
    point = replace(point_from_observation(d.observations[0], d.scenario), speed_kn=100)
    result = p.predict([point])[0]
    assert result.support_status == "unsupported"
    assert result.rate_kg_h is None


@pytest.mark.parametrize("method", ["engineering", "direct", "residual"])
def test_predictor_metrics_intervals_and_plausibility(method):
    from greenfleet.ingest import demo_dataset
    from greenfleet.splits import make_splits
    from greenfleet.predict import fit_predictor, prediction_report
    d = demo_dataset()
    p = fit_predictor(d, make_splits(d, "future", 1), method, 1, 1)
    report = prediction_report(p, d)
    assert report["test_count"] > 0
    assert report["mae"] >= 0
    assert 0 <= report["coverage"] <= 1
    assert report["synthetic"] is True
    assert report["plausibility"]["negative_rates"] == 0
