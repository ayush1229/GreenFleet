from dataclasses import replace


def test_candidate_cap_cannot_prove_infeasibility():
    from greenfleet.ingest import demo_dataset
    from greenfleet.candidates import build_candidates
    s = demo_dataset().scenario
    c = build_candidates(replace(s, max_candidates=1), None)
    assert len(c.items) == 1
    assert c.candidate_limit_reached
    assert not c.complete


def test_candidates_stable_and_missing_factor_logged():
    from greenfleet.ingest import demo_dataset
    from greenfleet.candidates import build_candidates
    s = demo_dataset().scenario
    a = build_candidates(s,None)
    assert a.hash == build_candidates(s,None).hash
    assert len({x.id for x in a.items}) == len(a.items)
    assert a.stats["considered"] >= len(a.items)
    bad = replace(s, pathways=(replace(s.pathways[0],price_per_kg=None),))
    excluded = build_candidates(bad,None)
    assert not excluded.items
    assert excluded.exclusions["missing_price"] > 0


def test_reposition_uses_declared_speed_grid():
    from greenfleet.ingest import demo_dataset
    from greenfleet.candidates import build_candidates
    s=demo_dataset().scenario
    s=replace(s,vessels=(s.vessels[0],),max_candidates=10000)
    c=build_candidates(s,None)
    choices={x.speed_kn for x in c.items if x.kind=="reposition" and x.start==s.start and x.origin=="A" and x.destination=="B"}
    assert choices=={10,10.5,11}
