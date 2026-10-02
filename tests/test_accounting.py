from dataclasses import replace
import pytest


def fixture():
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import Candidate
    s = demo_dataset().scenario
    v = s.vessels[0]
    c = Candidate(id="hand", vessel_id=v.id, service_id="S1", kind="service", origin="A", destination="B", pathway_id="diesel", start=s.start, speed_kn=10, distance_nm=10, cargo_t=100, loading_h=1, unloading_h=0)
    return s, c


def test_accounting_units():
    from greenfleet.accounting import lifecycle_kg
    assert lifecycle_kg(1000, 80, 10, .5) == 85


def test_no_double_counting():
    from greenfleet.accounting import evaluate_candidate
    s, c = fixture()
    v = replace(s.vessels[0], power_coefficient=.1, auxiliary_kw=10)
    f = replace(s.pathways[0], lhv_mj_kg=40, wtw_g_mj=80, wtt_g_mj=10, ttw_g_mj=70)
    s = replace(s, vessels=(v,) + s.vessels[1:], pathways=(f,))
    estimate = evaluate_candidate(c, s, None)
    # 100 kW shaft + 10 kW auxiliaries at sea, 10 kW at berth; efficiency .4.
    assert estimate.nominal.energy_mj == pytest.approx(1080)
    assert estimate.nominal.emissions_kg_co2e == pytest.approx(86.4)
    shore = evaluate_candidate(replace(c, shore_kw=10), s, None)
    assert shore.nominal.energy_mj == pytest.approx(1026)
    assert shore.nominal.electricity_kwh == 10
    assert shore.nominal.fuel_kg_by_pathway["diesel"] == pytest.approx(24.75)


def test_incompatible_engine():
    from greenfleet.accounting import evaluate_candidate
    s, c = fixture()
    e = evaluate_candidate(c, replace(s, engine_fuels=()), None)
    assert not e.eligible
    assert "incompatible_engine" in e.exclusions


def test_missing_factor_excludes_option():
    from greenfleet.accounting import evaluate_candidate
    s, c = fixture()
    s = replace(s, pathways=(replace(s.pathways[0], wtw_g_mj=None, wtt_g_mj=None, ttw_g_mj=None),))
    assert "missing_lifecycle_factor" in evaluate_candidate(c, s, None).exclusions


def test_purchase_vs_consumption_cost():
    from greenfleet.accounting import evaluate_plan
    from greenfleet.contracts import Candidate, Plan
    s, c = fixture()
    purchase = Candidate(id="buy", kind="purchase", vessel_id=c.vessel_id, origin="A", destination="A", pathway_id="diesel", start=s.start, purchase_kg=100, duration_h=1)
    plan = Plan((c, purchase))
    e = evaluate_plan(plan, s)
    assert e.nominal.cost == pytest.approx(100 * s.pathways[0].price_per_kg)
    assert e.consumption_cost > 0
    assert e.purchase_cost == e.nominal.cost
