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


@pytest.mark.parametrize("method", ["alns", "nsga2", "qie"])
def test_same_candidate_and_evaluator_hash(method):
    from greenfleet.solvers import solve,exact_tiny_solve
    from greenfleet.contracts import SearchConfig
    from greenfleet.feasibility import validate_plan
    from greenfleet.accounting import evaluate_plan
    s,c=tiny()
    r=solve(s,c,method,SearchConfig(budget=40,seed=3,population_size=4))
    exact=exact_tiny_solve(s,c)
    assert r.metadata["candidate_hash"]==exact.metadata["candidate_hash"]==c.hash
    assert r.metadata["evaluator_hash"]==exact.metadata["evaluator_hash"]
    assert r.metadata["evaluations"]<=40
    assert r.status=="completed"
    assert all(not validate_plan(p,s,c) for p in r.plans)
    assert min(evaluate_plan(p,s).nominal.energy_mj for p in r.plans)==pytest.approx(900)


def test_alns_preserves_paths_inventory():
    from greenfleet.solvers import solve
    from greenfleet.contracts import Candidate,CandidateSet,SearchConfig
    from greenfleet.feasibility import validate_plan
    from test_feasibility import setup_two_trips
    from datetime import timedelta
    s,a,b=setup_two_trips()
    buy=Candidate("buy",a.vessel_id,"purchase","B","B","diesel",s.start+timedelta(hours=1),purchase_kg=20,duration_h=1)
    c=CandidateSet((a,b,buy))
    r=solve(s,c,"alns",SearchConfig(budget=50,seed=4))
    assert r.plans
    assert all(not validate_plan(p,s,c) for p in r.plans)
    assert all("buy" in {x.id for x in p.selected} for p in r.plans)


def test_nondominated_feasible_archive():
    from greenfleet.solvers import Evaluator
    from greenfleet.contracts import SearchConfig,Plan
    s,c=tiny();e=Evaluator(s,c,SearchConfig(),"test")
    e.check(Plan((c.items[1],)))
    e.check(Plan((c.items[0],)))
    e.check(Plan(c.items))
    assert len(e.archive)==1
    assert next(iter(e.archive.values())).selected[0].id=="slow"
