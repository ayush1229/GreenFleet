from dataclasses import dataclass
from datetime import timedelta
import random
from .contracts import Dataset, Record, digest


@dataclass(frozen=True)
class SplitManifest(Record):
    protocol: str
    seed: int
    train: tuple[str, ...]
    validation: tuple[str, ...]
    calibration: tuple[str, ...]
    test: tuple[str, ...]
    excluded_ids: tuple[str, ...]
    partitions: dict

    @property
    def hash(self):
        return digest(self)


def make_splits(data: Dataset, protocol: str, seed: int) -> SplitManifest:
    if protocol not in ("future","unseen_vessel"):
        raise ValueError("unknown split protocol")
    rows = data.observations
    groups = [[],[],[],[]]
    excluded = []
    vessels = sorted({o.vessel_id for o in rows})
    def divide(seq):
        n = len(seq)
        if n < 4:
            raise ValueError("at least four independent groups required")
        a=max(1,n//2); b=max(a+1,2*n//3); c=max(b+1,5*n//6)
        c=min(c,n-1); b=min(b,c-1); a=min(a,b-1)
        return seq[:a],seq[a:b],seq[b:c],seq[c:]
    if protocol == "unseen_vessel":
        random.Random(seed).shuffle(vessels)
        for part, vs in zip(groups,divide(vessels)):
            part.extend(o for o in rows if o.vessel_id in vs)
    else:
        voyage_vessels={}
        for o in rows:
            voyage_vessels.setdefault(o.voyage_id,set()).add(o.vessel_id)
        if any(len(v)>1 for v in voyage_vessels.values()):
            raise ValueError("voyage IDs must identify a single vessel voyage")
        for vessel in vessels:
            voyages={}
            for o in rows:
                if o.vessel_id == vessel:
                    voyages.setdefault(o.voyage_id,[]).append(o)
            ordered=sorted(voyages,key=lambda v:min(x.timestamp for x in voyages[v]))
            parts=[list(x) for x in divide(ordered)]
            for i in range(3):
                next_start=min(o.timestamp for v in parts[i+1] for o in voyages[v])
                keep=[]
                for v in parts[i]:
                    if max(o.timestamp+timedelta(hours=o.duration_h) for o in voyages[v]) > next_start:
                        excluded.extend(o.id for o in voyages[v])
                    else:
                        keep.append(v)
                parts[i]=keep
            for target,vs in zip(groups,parts):
                target.extend(o for v in vs for o in voyages[v])
    names=("train","validation","calibration","test")
    details={name:{"count":len(g),"vessel_ids":sorted({x.vessel_id for x in g}),"voyage_ids":sorted({x.voyage_id for x in g}),"start":min((x.timestamp for x in g),default=None),"end":max((x.timestamp+timedelta(hours=x.duration_h) for x in g),default=None)} for name,g in zip(names,groups)}
    return SplitManifest(protocol,seed,*(tuple(sorted(o.id for o in g)) for g in groups),tuple(sorted(excluded)),details)
