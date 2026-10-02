from dataclasses import replace
from datetime import timedelta


def setup_two_trips():
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import Candidate, CandidateSet, Plan, Tank
    s = demo_dataset().scenario
    v = replace(s.vessels[0], power_coefficient=.1, auxiliary_kw=0, tanks={"diesel": Tank(1000, 30, 0)})
    s1 = replace(s.services[0], distance_nm=10, loading_h=0, unloading_h=0, demand_t=100)
    s2 = replace(s1, id="S2", origin="B", destination="A", release=s.start + timedelta(hours=2))
    s = replace(s, vessels=(v,), services=(s1,s2), weather_cases=(s.weather_cases[0],))
    c1 = Candidate("one", v.id, "service", "A", "B", "diesel", s.start, "S1", 10, 10, 100)
    c2 = replace(c1, id="two", origin="B", destination="A", start=s2.release, service_id="S2")
    # Each consumes 22.5 kg: 100 kW * 3600 / .4 / 40 = 22500 g.
    return s, c1, c2


def check(s, *cs):
    from greenfleet.contracts import CandidateSet, Plan
    from greenfleet.feasibility import validate_plan
    return validate_plan(Plan(tuple(cs)), s, CandidateSet(tuple(cs)))


def test_two_trip_fuel_balance():
    from greenfleet.contracts import Candidate
    s, a, b = setup_two_trips()
    assert "fuel_reserve" in {v.code for v in check(s,a,b)}
    buy = Candidate("buy", a.vessel_id, "purchase", "B", "B", "diesel", s.start+timedelta(hours=1), purchase_kg=20, duration_h=1)
    assert check(s, a, buy, b) == []


def test_port_contention():
    from greenfleet.contracts import Candidate
    s,a,b = setup_two_trips()
    v2 = replace(s.vessels[0], id="V2")
    s2 = replace(s.services[0], id="S2")
    s = replace(s, vessels=s.vessels+(v2,), services=(s.services[0],s2), ports=(replace(s.ports[0], shore_sockets=1, shore_kw=10, fuel_stock={"diesel":30}), s.ports[1]))
    a = replace(a, loading_h=1, shore_kw=10)
    b = replace(a, id="two", vessel_id="V2", service_id="S2")
    s = replace(s, services=tuple(replace(x, loading_h=1) for x in s.services))
    assert "shore_capacity" in {v.code for v in check(s,a,b)}
    buy1 = Candidate("p1", a.vessel_id, "purchase", "A", "A", "diesel", s.start, purchase_kg=20, duration_h=1)
    buy2 = replace(buy1, id="p2", vessel_id="V2")
    codes = {v.code for v in check(s,buy1,buy2)}
    assert "port_fuel_stock" in codes


def test_location_and_time():
    s,a,b = setup_two_trips()
    assert "location" in {v.code for v in check(s, replace(a, origin="B"), b)}
    assert "overlap" in {v.code for v in check(s,a,replace(b,start=s.start))}
    assert "route_mismatch" in {v.code for v in check(s,replace(a,distance_nm=0),b)}


def test_weather_case_deadline():
    from greenfleet.contracts import WeatherCase
    s,a,b = setup_two_trips()
    s = replace(s, services=(replace(s.services[0], deadline=s.start+timedelta(hours=1.5)),), weather_cases=(s.weather_cases[0],WeatherCase("storm",2,1.2)))
    assert "deadline" in {v.code for v in check(s,a)}


def test_known_hard_rule_rejected_unknown_separate():
    from greenfleet.contracts import Rule
    s,a,_ = setup_two_trips()
    s = replace(s, services=(s.services[0],), rules=(Rule("cap","demo","demo-1","energy_mj","MJ",1,"synthetic"),), rule_coverage_known=True)
    assert "hard_rule" in {v.code for v in check(s,a)}
