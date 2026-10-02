from dataclasses import replace


def test_future_and_unseen_splits():
    from greenfleet.ingest import demo_dataset
    from greenfleet.splits import make_splits
    d = demo_dataset()
    for protocol in ["future", "unseen_vessel"]:
        split = make_splits(d, protocol, seed=12)
        groups = [getattr(split, name) for name in ["train", "validation", "calibration", "test"]]
        assert all(groups)
        obs = {o.id: o for o in d.observations}
        for i, group in enumerate(groups):
            for other in groups[i + 1:]:
                assert not set(group) & set(other)
                attr = "voyage_id" if protocol == "future" else "vessel_id"
                assert not {getattr(obs[x], attr) for x in group} & {getattr(obs[x], attr) for x in other}
        if protocol == "future":
            for vessel in d.scenario.vessels:
                parts = [[obs[x].timestamp for x in g if obs[x].vessel_id == vessel.id] for g in groups]
                assert all(max(a) < min(b) for a, b in zip(parts, parts[1:]))
        assert split.hash == make_splits(d, protocol, 12).hash


def test_overlapping_voyages_are_embargoed():
    from greenfleet.ingest import demo_dataset
    from greenfleet.splits import make_splits
    d = demo_dataset()
    observations = tuple(replace(o, duration_h=100) for o in d.observations)
    split = make_splits(replace(d, observations=observations), "future", 1)
    assert split.excluded_ids
