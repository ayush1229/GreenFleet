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
