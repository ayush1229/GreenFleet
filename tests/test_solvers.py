from dataclasses import replace
import pytest


def tiny():
    from greenfleet.contracts import Candidate, CandidateSet
    from greenfleet.ingest import demo_dataset
    s = demo_dataset().scenario
    v = replace(s.vessels[0], auxiliary_kw=0, power_coefficient=.1)
    r = replace(s.services[0], distance_nm=10, loading_h=0, unloading_h=0, demand_t=100)
    s = replace(s,vessels=(v,),services=(r,),weather_cases=(s.weather_cases[0],))
    a = Candidate("slow",v.id,"service","A","B","diesel",s.start,r.id,10,10,100)
    b = replace(a,id="fast",speed_kn=12)
    return s,CandidateSet((a,b))


def test_exact_hand_frontier():
    from greenfleet.solvers import exact_tiny_solve
    from greenfleet.accounting import evaluate_plan
    s,c = tiny()
    result = exact_tiny_solve(s,c)
    assert result.status == "completed"
    assert len(result.plans) == 1
    t = evaluate_plan(result.plans[0],s).nominal
    assert (t.energy_mj,t.cost,t.emissions_kg_co2e) == pytest.approx((900,0,72))
    assert result.metadata["evaluations"] == 4


def test_greedy_is_checked():
    from greenfleet.solvers import greedy_solve
    from greenfleet.contracts import SearchConfig
    from greenfleet.feasibility import validate_plan
    s,c = tiny()
    result = greedy_solve(s,c,SearchConfig(budget=10))
    assert result.status == "completed"
    assert all(not validate_plan(p,s,c) for p in result.plans)


def test_infeasible_witness():
    from greenfleet.solvers import solve
    from greenfleet.contracts import SearchConfig
    s,c = tiny()
    s = replace(s,services=(replace(s.services[0],demand_t=1e9),))
    r = solve(s,c,"greedy",SearchConfig())
    assert r.status == "infeasible_proven"
    assert r.metadata["proof"]["service_id"] == s.services[0].id


def test_exhausted_search_is_not_proof():
    from greenfleet.solvers import exact_tiny_solve
    from greenfleet.contracts import CandidateSet
    s,c = tiny()
    r = exact_tiny_solve(s,CandidateSet((),complete=False,candidate_limit_reached=True))
    assert r.status == "no_feasible_solution_found"
