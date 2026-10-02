import csv
import json
from pathlib import Path
import pytest


def test_export_matches_evaluation(tmp_path):
    from greenfleet.runs import execute_run
    from greenfleet.reporting import export_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig
    from greenfleet.accounting import evaluate_plan
    s=demo_dataset().scenario
    r=execute_run(s,RunConfig(),tmp_path/"runs")
    paths=export_run(r,tmp_path/"exports")
    totals=json.loads(next(p for p in paths if p.name=="summary.json").read_text())
    assert totals["plans"][0]["nominal"]["energy_mj"]==pytest.approx(evaluate_plan(r.plans[0],s).nominal.energy_mj)
    rows=list(csv.DictReader(next(p for p in paths if p.name=="deployment.csv").open()))
    assert len(rows)==len(r.plans[0].selected)
    assert any(p.name=="purchases.csv" for p in paths)
    assert any(p.name=="rules.csv" for p in paths)
    assert any(p.name=="provenance.json" for p in paths)
    provenance=json.loads(next(p for p in paths if p.name=="provenance.json").read_text())
    assert provenance["scenario"]["pathways"][0]["source"].startswith("synthetic")


def test_export_unique_and_csv_formula_safe(tmp_path):
    from greenfleet.reporting import safe_cell,export_run
    from greenfleet.runs import execute_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig
    assert safe_cell("=HYPERLINK('x')").startswith("'")
    r=execute_run(demo_dataset().scenario,RunConfig(),tmp_path/"runs")
    a=export_run(r,tmp_path/"exports")
    before={p:p.read_bytes() for p in a}
    b=export_run(r,tmp_path/"exports")
    assert a[0].parent!=b[0].parent
    assert all(p.read_bytes()==content for p,content in before.items())
