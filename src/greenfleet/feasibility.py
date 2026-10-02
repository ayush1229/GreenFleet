from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from .contracts import *
from .accounting import evaluate_candidate,evaluate_plan,berth_intervals

EPS=1e-7


@dataclass(frozen=True)
class Proof(Record):
    kind: str
    service_id: str
    demand_t: float
    maximum_capacity_t: float
    scenario_hash: str


def prove_simple_infeasibility(s):
    # A global capacity bound is intentionally weaker than speculative eligibility pruning.
    capacity=max((v.capacity_t for v in s.vessels),default=0)
    for r in s.services:
        if not r.allow_split and r.demand_t>capacity:
            return Proof("unsplittable_capacity",r.id,r.demand_t,capacity,digest(s))
    return None


def validate_plan(plan,scenario,candidates,*,partial=False):
    s=scenario
    out=[]
    def fail(code,*ids,observed=None,limit=None,unit=None):
        out.append(Violation(code,tuple(ids),observed,limit,unit))
    universe={c.id:c for c in candidates.items}
    vessels={v.id:v for v in s.vessels};ports={p.id:p for p in s.ports};services={r.id:r for r in s.services}
    selected=plan.selected
    if candidates.scenario_hash and candidates.scenario_hash!=digest(s):
        fail("scenario_hash_mismatch")
    seen=set();unsafe=False
    for c in selected:
        if c.id in seen:
            fail("duplicate_candidate",c.id)
        seen.add(c.id)
        if universe.get(c.id)!=c:
            fail("outside_candidate_universe",c.id)
        if c.vessel_id not in vessels or c.origin not in ports or c.destination not in ports or c.pathway_id not in {f.id for f in s.pathways}:
            fail("unknown_reference",c.id);unsafe=True;continue
        v=vessels[c.vessel_id]
        if c.kind not in ("service","reposition","purchase","changeover"):
            fail("invalid_action",c.id);unsafe=True
        if any(not math.isfinite(x) or x<0 for x in (c.speed_kn,c.distance_nm,c.cargo_t,c.loading_h,c.unloading_h,c.shore_kw,c.purchase_kg,c.duration_h)):
            fail("invalid_action_value",c.id);unsafe=True
        if c.kind in ("service","reposition") and (not v.min_speed_kn<=c.speed_kn<=v.max_speed_kn or c.distance_nm<=0):
            fail("invalid_speed_or_distance",c.id)
        if c.cargo_t>v.capacity_t+EPS:
            fail("vessel_capacity",c.id)
        if c.kind=="service":
            r=services.get(c.service_id)
            if r is None:
                fail("unknown_service",c.id);unsafe=True
            elif (c.origin,c.destination,c.distance_nm,c.loading_h,c.unloading_h)!=(r.origin,r.destination,r.distance_nm,r.loading_h,r.unloading_h):
                fail("route_mismatch",c.id,r.id)
            if r and c.start<r.release:
                fail("release",c.id,r.id)
        elif c.kind=="reposition":
            distance=s.routes_nm.get(f"{c.origin}>{c.destination}")
            if distance is None:
                distance=next((r.distance_nm for r in s.services if (r.origin,r.destination)==(c.origin,c.destination)),None)
            if distance is None or abs(c.distance_nm-distance)>EPS or c.cargo_t!=0:
                fail("route_mismatch",c.id)
        elif c.origin!=c.destination or c.duration_h<=0 or c.distance_nm!=0:
            fail("invalid_port_action",c.id)
        if c.kind!="purchase" and c.purchase_kg!=0:
            fail("invalid_purchase",c.id)
        if c.kind=="purchase" and (c.purchase_kg<=0 or c.purchase_kg>ports[c.origin].bunkering_kg_h*c.duration_h+EPS):
            fail("bunkering_rate",c.id)
        if c.shore_kw>min(v.shore_acceptance_kw,v.auxiliary_kw)+EPS or c.shore_kw>0 and not s.shore_enabled:
            fail("shore_acceptance",c.id)
        if v.draft_limit_m>min(ports[c.origin].draft_limit_m,ports[c.destination].draft_limit_m):
            fail("port_draft",c.id)
    if unsafe:
        return out
    for r in s.services:
        choices=[c for c in selected if c.service_id==r.id and c.kind=="service"]
        delivered=sum(c.cargo_t for c in choices)
        if delivered>r.demand_t+EPS or not partial and abs(delivered-r.demand_t)>EPS or not r.allow_split and (len(choices)>1 or not partial and len(choices)!=1):
            fail("cargo_balance",r.id,observed=delivered,limit=r.demand_t,unit="t")
    estimates={c.id:evaluate_candidate(c,s) for c in selected}
    for c in selected:
        for reason in estimates[c.id].exclusions:
            fail(reason,c.id)
    for case in s.weather_cases:
        if not case.required:
            continue
        reservations=defaultdict(list);pumps=defaultdict(list);berths=defaultdict(list)
        for v in s.vessels:
            path=sorted((c for c in selected if c.vessel_id==v.id),key=lambda c:(c.start,c.id))
            time=v.initial_time;port=v.initial_port
            inventory={f:t.initial_kg for f,t in v.tanks.items()}
            active_fuel=None
            def consume(c,estimate):
                if not estimate.eligible:
                    return
                for f,m in estimate.cases[case.id].fuel_kg_by_pathway.items():
                    if f not in inventory:
                        fail("missing_tank",v.id,c.id,f);continue
                    inventory[f]-=m
                    if inventory[f]<v.tanks[f].reserve_kg-EPS:
                        fail("fuel_reserve",v.id,c.id,case.id,f,observed=inventory[f],limit=v.tanks[f].reserve_kg,unit="kg")
            for c in path:
                if c.start<time:
                    fail("overlap",v.id,c.id,case.id)
                if c.origin!=port:
                    fail("location",v.id,c.id,port,c.origin)
                if c.start>time:
                    fuel=active_fuel or c.pathway_id
                    wait=Candidate("wait-"+c.id,v.id,"wait",port,port,fuel,time,duration_h=hours(time,c.start))
                    consume(wait,evaluate_candidate(wait,s))
                if active_fuel and active_fuel!=c.pathway_id and c.kind!="changeover":
                    fail("missing_changeover",v.id,c.id)
                if c.kind=="changeover" or active_fuel is None:
                    active_fuel=c.pathway_id
                end=c.end(case)
                if c.start<s.start or end>s.end:
                    fail("horizon",c.id,case.id)
                if any(c.start<b and end>a for a,b in v.maintenance):
                    fail("maintenance",v.id,c.id)
                if c.kind=="service" and end>services[c.service_id].deadline:
                    fail("deadline",c.id,c.service_id,case.id)
                consume(c,estimates[c.id])
                if c.kind=="purchase" and c.pathway_id in inventory:
                    inventory[c.pathway_id]+=c.purchase_kg
                    if inventory[c.pathway_id]>v.tanks[c.pathway_id].capacity_kg+EPS:
                        fail("tank_capacity",v.id,c.id,c.pathway_id)
                    pumps[c.origin].append((c.start,end,1,c.id))
                for pid,a,b in berth_intervals(c,case):
                    if a==b:
                        continue
                    p=ports[pid]
                    if p.berth_windows and not any(x<=a and b<=y for x,y in p.berth_windows):
                        fail("port_window",pid,c.id,case.id)
                    berths[pid].append((a,b,1,c.id))
                    if c.shore_kw>0:
                        reservations[pid].append((a,b,c.shore_kw,c.id))
                time=max(time,end);port=c.destination
        def concurrent(records,pid,limit_count,limit_power,code):
            times=sorted({x for a,b,_,_ in records for x in (a,b)})
            for t in times:
                active=[r for r in records if r[0]<=t<r[1]]
                if len(active)>limit_count or sum(r[2] for r in active)>limit_power+EPS:
                    fail(code,pid,case.id,*(r[3] for r in active))
        for pid,rs in reservations.items():
            concurrent(rs,pid,ports[pid].shore_sockets,ports[pid].shore_kw,"shore_capacity")
        for pid,rs in pumps.items():
            concurrent(rs,pid,ports[pid].pumps,float("inf"),"pump_capacity")
        for pid,rs in berths.items():
            concurrent(rs,pid,ports[pid].berths,float("inf"),"berth_capacity")
    for p in s.ports:
        for f in {c.pathway_id for c in selected if c.kind=="purchase" and c.origin==p.id}:
            stock=p.fuel_stock.get(f,0)
            events=[(t,0,q,"replenishment") for t,pf,q in p.replenishments if pf==f]
            events += [(c.start,1,-c.purchase_kg,c.id) for c in selected if c.kind=="purchase" and c.origin==p.id and c.pathway_id==f]
            for t,_,quantity,key in sorted(events):
                stock+=quantity
                if stock<-EPS:
                    fail("port_fuel_stock",p.id,f,key,observed=stock,limit=0,unit="kg")
    evaluation=evaluate_plan(plan,s)
    for r in evaluation.rule_results:
        if r["status"]=="fail" and r["severity"]=="hard":
            fail("hard_rule",r["id"],observed=r["observed"],limit=r["threshold"],unit=r["unit"])
    if s.require_certified_compliance and evaluation.compliance_status!="compliant":
        fail("compliance_unverified")
    return list(dict.fromkeys(out))
