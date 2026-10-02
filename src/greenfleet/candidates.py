from collections import Counter
from dataclasses import replace
from datetime import timedelta
import math
from .contracts import *
from .ingest import validate_scenario, BundleError
from .accounting import evaluate_candidate


def _slots(start,end,step,extras=()):
    n=int(hours(start,end)//step)
    return sorted({start+timedelta(hours=i*step) for i in range(n+1)} | {t for t in extras if start<=t<=end})


def build_candidates(scenario,predictor=None):
    s=scenario
    errors=validate_scenario(s)
    if errors:
        raise BundleError(errors)
    items=[];seen=set();excluded=Counter();considered=0;limited=False
    ports={p.id:p for p in s.ports}
    def accept(c):
        nonlocal considered,limited
        considered+=1
        v=next(v for v in s.vessels if v.id==c.vessel_id)
        if any(v.draft_limit_m>ports[p].draft_limit_m for p in (c.origin,c.destination)):
            excluded["draft"]+=1;return True
        estimate=evaluate_candidate(c,s,predictor)
        if not estimate.eligible:
            excluded.update(estimate.exclusions);return True
        if c.start<s.start or c.end(min(s.weather_cases,key=lambda w:w.time_multiplier))>s.end:
            excluded["outside_horizon"]+=1;return True
        if predictor is not None and c.kind in ("service","reposition"):
            from .predict import OperatingPoint
            p=predictor.predict([OperatingPoint(v.id,v.type,v.capacity_t,v.engine_id,c.pathway_id,c.speed_kn,c.cargo_t,auxiliary_kw=v.auxiliary_kw)])[0]
            c=replace(c,prediction=p)
        key=digest(replace(c,id=""))
        if key in seen:
            excluded["duplicate"]+=1;return True
        if len(items)>=s.max_candidates:
            limited=True;return False
        seen.add(key);items.append(replace(c,id=key[:20]));return True
    def generate():
        for r in sorted(s.services,key=lambda r:(r.release,r.id)):
            for v in sorted(s.vessels,key=lambda v:v.id):
                loads=sorted({r.demand_t*f for f in (s.load_bands if r.allow_split else (1,)) if r.demand_t*f<=v.capacity_t})
                if not loads:
                    excluded["capacity"]+=1;continue
                speeds=[v.min_speed_kn+i*s.speed_step_kn for i in range(int((v.max_speed_kn-v.min_speed_kn)/s.speed_step_kn)+1)]
                if speeds[-1]<v.max_speed_kn:
                    speeds.append(v.max_speed_kn)
                for f in sorted(v.tanks):
                    for speed in speeds:
                        latest=r.deadline-timedelta(hours=r.loading_h+r.unloading_h+r.distance_nm/speed)
                        for start in _slots(r.release,r.deadline,s.departure_step_h,(latest,)):
                            c=Candidate("",v.id,"service",r.origin,r.destination,f,start,r.id,speed,r.distance_nm,loading_h=r.loading_h,unloading_h=r.unloading_h)
                            if c.end(min(s.weather_cases,key=lambda w:w.time_multiplier))>r.deadline:
                                excluded["best_case_deadline"]+=1;continue
                            shore=min(v.auxiliary_kw,v.shore_acceptance_kw,ports[r.origin].shore_kw,ports[r.destination].shore_kw)
                            for load in loads:
                                for kw in ((0,shore) if s.shore_enabled and shore>0 else (0,)):
                                    yield replace(c,cargo_t=load,shore_kw=kw)
        route_map=dict(s.routes_nm)
        for r in s.services:
            route_map.setdefault(f"{r.origin}>{r.destination}",r.distance_nm)
        # Explicit reposition arcs share route accounting and all speed choices.
        for v in sorted(s.vessels,key=lambda v:v.id):
            for route,distance in sorted(route_map.items()):
                origin,dest=route.split(">")
                for start in _slots(s.start,s.end,s.departure_step_h):
                    for fuel in sorted(v.tanks):
                        for speed in (v.min_speed_kn,v.max_speed_kn):
                            yield Candidate("",v.id,"reposition",origin,dest,fuel,start,speed_kn=speed,distance_nm=distance)
            # Bunkering and changeover are genuine selectable actions, never hidden purchases.
            for p in s.ports:
                for start in _slots(s.start,s.end,s.departure_step_h):
                    for fuel,tank in sorted(v.tanks.items()):
                        if fuel in p.fuel_stock or any(f==fuel for _,f,_ in p.replenishments):
                            for quantity in s.purchase_bands_kg:
                                if quantity<=tank.capacity_kg:
                                    yield Candidate("",v.id,"purchase",p.id,p.id,fuel,start,purchase_kg=quantity,duration_h=quantity/p.bunkering_kg_h)
                        if len(v.tanks)>1:
                            yield Candidate("",v.id,"changeover",p.id,p.id,fuel,start,duration_h=.5)
    for c in generate():
        if not accept(c):
            break
    return CandidateSet(tuple(items),complete=not limited and not excluded,candidate_limit_reached=limited,exclusions=dict(excluded),stats={"considered":considered,"retained":len(items),"excluded":sum(excluded.values()),"enumeration_stopped":int(limited)},model_id=getattr(predictor,"model_id","engineering"),scenario_hash=digest(s))
