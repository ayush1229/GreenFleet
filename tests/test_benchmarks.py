import json
from dataclasses import replace
import pytest


def test_paired_manifest(tmp_path):
    from greenfleet.benchmarks import run_benchmarks
    config=tmp_path/"config.yaml"
    config.write_text("seeds: 2\nbudget: 12\nmax_candidates: 50\nmethods: [alns, qie]\nwall_clock_s: 0.05\nprediction: false\ncase_studies: false\nscales: []\n")
    p=run_benchmarks(config,tmp_path/"outputs")
    manifest=json.loads(p.read_text())
    assert manifest["synthetic"] is True
    assert manifest["hardware"]["python"]
    assert manifest["hardware"]["cpu_count"]>0
    assert manifest["hardware"]["memory_bytes"]>0
    assert manifest["normalization"]==[1000000,100000,100000]
    assert manifest["seeds"]==[0,1]
    rows=manifest["runs"]
    for key in ("dataset_hash","split_hash","candidate_hash","factor_hash"):
        assert len({r[key] for r in rows})==1
    matched=[r for r in rows if r["comparison"]=="equal_evaluations"]
    assert all(r["budget"]==12 and r["evaluations"]<=12 for r in matched)
    assert {r["method"] for r in matched}=={"alns","qie"}
    assert len(rows)==8


def test_undefined_metrics():
    from greenfleet.benchmarks import hypervolume
    from greenfleet.predict import metrics
    assert hypervolume([], [2,2,2],[1,1,1]) is None
    assert metrics([0,0],[0,1])["wape"] is None
    assert hypervolume([[1,1,1]], [2,2,2],[1,1,1])==pytest.approx(1)


def test_heldout_decision_evaluation():
    from greenfleet.benchmarks import evaluate_heldout_decision
    from greenfleet.contracts import Plan
    from test_solvers import tiny
    s,c=tiny();p=Plan((c.items[0],))
    heldout=replace(s,weather_cases=(replace(s.weather_cases[0],energy_multiplier=2),))
    result=evaluate_heldout_decision(p,s,heldout,c)
    assert result["chosen_plan_hash"]==p.hash
    assert result["development"]["energy_mj"]==pytest.approx(900)
    assert result["realized"]["energy_mj"]==pytest.approx(1800)
    assert result["regret"] is None
    assert result["replay_label"]=="independently simulated conditions; not observed counterfactuals"


def test_generated_heldout_reports_realized_adverse_case():
    from greenfleet.benchmarks import evaluate_heldout_decision
    from greenfleet.contracts import Plan,WeatherCase
    from test_solvers import tiny
    s,c=tiny();p=Plan((c.items[0],))
    heldout=replace(s,weather_cases=(s.weather_cases[0],WeatherCase("independent_adverse",1.3,1.25)))
    report=evaluate_heldout_decision(p,s,heldout,c,realized_case="independent_adverse")
    assert report["chosen_plan_hash"]==p.hash
    assert report["realized"]["energy_mj"]==pytest.approx(1462.5)
    assert report["realized_case"]=="independent_adverse"
    assert set(report["realized_cases"])=={"nominal","independent_adverse"}
