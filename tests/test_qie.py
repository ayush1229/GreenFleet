import numpy as np


def test_seed_and_budget():
    from greenfleet.qie import SearchProblem,qie_search
    from greenfleet.contracts import SearchConfig
    calls=[]
    p=SearchProblem(5,lambda bits: calls.append(tuple(bits)) or float(sum(bits)))
    cfg=SearchConfig(budget=29,seed=5,population_size=8)
    a=qie_search(p,cfg)
    assert len(calls)==29
    b=qie_search(SearchProblem(5,lambda bits:float(sum(bits))),cfg)
    assert a.best_bits==b.best_bits
    assert a.samples==b.samples


def test_probabilities_bounded():
    from greenfleet.qie import SearchProblem,qie_search
    from greenfleet.contracts import SearchConfig
    cfg=SearchConfig(budget=200,rotation=1,epsilon=.05,reset_interval=2)
    t=qie_search(SearchProblem(8,lambda bits:float(sum(bits))),cfg)
    assert all(np.sin(.05)**2-1e-10<=p<=np.cos(.05)**2+1e-10 for row in t.probabilities for p in row)
    assert t.resets>0
