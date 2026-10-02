import json
from dataclasses import replace
import pytest


def test_rejects_missing_units_and_bad_rows(tmp_path):
    from greenfleet.ingest import write_demo_bundle, load_bundle, BundleError
    write_demo_bundle(tmp_path)
    data = load_bundle(tmp_path)
    assert data.observations[0].fuel_mass_kg == 1000
    original = json.loads((tmp_path / "bundle.json").read_text())
    for mutate, code in [
        (lambda b: b["manifest"]["units"].pop("fuel_mass"), "missing_unit"),
        (lambda b: b["observations"].append(b["observations"][0]), "duplicate_id"),
        (lambda b: b["observations"][0].update(duration_h=0), "invalid_duration"),
        (lambda b: b["observations"][0].update(cargo_t=-1), "negative_cargo"),
    ]:
        b = json.loads(json.dumps(original))
        mutate(b)
        (tmp_path / "bundle.json").write_text(json.dumps(b))
        with pytest.raises(BundleError) as err:
            load_bundle(tmp_path, verify_digests=False)
        assert code in {v.code for v in err.value.violations}


def test_status_domains():
    from greenfleet.contracts import RunResult, Prediction
    with pytest.raises(ValueError):
        RunResult("unknown", (), (), "unknown", {})
    with pytest.raises(ValueError):
        RunResult("completed", (), (), "completed", {})
    with pytest.raises(ValueError):
        Prediction(None, None, None, "completed", "x")


def test_manifest_hash_and_validation(tmp_path):
    from greenfleet.ingest import demo_dataset, fingerprint_dataset, validate_scenario, write_demo_bundle, load_bundle, BundleError
    d = demo_dataset()
    assert fingerprint_dataset(d) == fingerprint_dataset(demo_dataset())
    assert validate_scenario(d.scenario) == []
    assert fingerprint_dataset(replace(d, scenario=replace(d.scenario, currency="EUR"))) != fingerprint_dataset(d)
    write_demo_bundle(tmp_path)
    b = json.loads((tmp_path / "bundle.json").read_text())
    b["observations"][0]["fuel_mass"] = 99
    (tmp_path / "bundle.json").write_text(json.dumps(b))
    with pytest.raises(BundleError, match="digest_mismatch"):
        load_bundle(tmp_path)
