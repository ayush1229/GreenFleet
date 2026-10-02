from __future__ import annotations
from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
from .contracts import *
from .pathways import pathway_issues, wtw_factor


def lifecycle_kg(energy_mj,factor_g_mj,electricity_kwh=0,grid_kg_kwh=0):
    return energy_mj*factor_g_mj/1000+electricity_kwh*grid_kg_kwh


def sum_totals(totals):
    values=list(totals)
    fuel=defaultdict(float)
    for t in values:
        for k,v in t.fuel_kg_by_pathway.items():
            fuel[k]+=v
    return Totals(sum(t.energy_mj for t in values),sum(t.cost for t in values),sum(t.emissions_kg_co2e for t in values),dict(fuel),sum(t.electricity_kwh for t in values))


def berth_intervals(c,case):
    if c.kind in ("service","reposition"):
        return [(c.origin,c.start,c.start+timedelta(hours=c.loading_h)),(c.destination,c.end(case)-timedelta(hours=c.unloading_h),c.end(case))]
    return [(c.origin,c.start,c.end(case))]


def grid_account(port,start,end,kw):
    energy=emissions=cost=0.
    current=start
    while current<end:
        boundary=current.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        next_time=min(end,boundary)
        key=current.replace(minute=0,second=0,microsecond=0).isoformat()
        factor=port.hourly_grid.get(key,port.grid_kg_kwh)
        tariff=port.hourly_tariff.get(key,port.tariff_kwh)
        if factor is None or tariff is None or not port.grid_source:
            raise ValueError("missing_grid_factor_or_tariff")
        kwh=kw*hours(current,next_time)
        energy+=kwh; emissions+=kwh*factor; cost+=kwh*tariff
        current=next_time
    return energy,emissions,cost


def evaluate_candidate(candidate,scenario,predictor=None):
    c,s=candidate,scenario
    v=next((v for v in s.vessels if v.id==c.vessel_id),None)
    f=next((f for f in s.pathways if f.id==c.pathway_id),None)
    e=next((e for e in s.engine_fuels if v and e.engine_id==v.engine_id and e.pathway_id==c.pathway_id),None)
    if v is None or f is None:
        return CandidateEstimate(False,Totals(),{},("unknown_reference",))
    issues=list(pathway_issues(v,f,e,s))
    prediction=c.prediction
    if predictor is not None and c.kind in ("service","reposition"):
        from .predict import OperatingPoint
        prediction=predictor.predict([OperatingPoint(v.id,v.type,v.capacity_t,v.engine_id,f.id,c.speed_kn,c.cargo_t,auxiliary_kw=v.auxiliary_kw)])[0]
    if prediction is not None and prediction.rate_kg_h is None:
        issues.append("unsupported_prediction")
    if prediction is None and c.distance_nm>0 and (v.power_coefficient is None or not v.power_source):
        issues.append("missing_power_curve")
    if issues:
        return CandidateEstimate(False,Totals(),{},tuple(issues))
    ports={p.id:p for p in s.ports}
    results={}
    for case in s.weather_cases:
        transit_h=c.distance_nm/c.speed_kn*case.time_multiplier if c.speed_kn>0 else 0
        if prediction is not None and c.distance_nm>0:
            rate=prediction.rate_kg_h
            if case.id!=s.weather_cases[0].id and prediction.upper_kg_h is not None:
                rate=max(rate,prediction.upper_kg_h)
            # Measured rate already includes input fuel and sea auxiliary consumers.
            mass=rate*transit_h*case.energy_multiplier
        else:
            useful=(v.power_coefficient or 0)*c.speed_kn**3*transit_h*3.6*case.energy_multiplier
            mass=(useful/e.efficiency+v.auxiliary_kw*transit_h*3.6*case.energy_multiplier/e.auxiliary_efficiency)/f.lhv_mj_kg
        electricity=grid_emissions=grid_cost=0.
        for port_id,start,end in berth_intervals(c,case):
            duration=hours(start,end)
            if duration<=0:
                continue
            shore=min(c.shore_kw,v.auxiliary_kw)
            mass+=max(0,v.auxiliary_kw-shore)*duration*3.6/e.auxiliary_efficiency/f.lhv_mj_kg
            if shore>0:
                try:
                    kwh,ghg,cost=grid_account(ports[port_id],start,end,shore)
                except (ValueError,KeyError):
                    return CandidateEstimate(False,Totals(),{},("missing_grid_factor_or_tariff",))
                electricity+=kwh; grid_emissions+=ghg; grid_cost+=cost
        fuel_energy=mass*f.lhv_mj_kg
        cost=grid_cost+v.hourly_cost*hours(c.start,c.end(case))
        if s.inventory_cost=="consumption":
            cost+=mass*f.price_per_kg
        elif c.kind=="purchase":
            cost+=c.purchase_kg*f.price_per_kg
        if c.kind=="service":
            cost+=ports[c.origin].port_fee+ports[c.destination].port_fee
        results[case.id]=Totals(fuel_energy+3.6*electricity,cost,fuel_energy*wtw_factor(f)/1000+grid_emissions,{f.id:mass},electricity)
    return CandidateEstimate(True,results[s.weather_cases[0].id],results,(),{"pathway":primitive(f),"engine":primitive(e),"prediction":primitive(prediction),"support":"engineering_only" if prediction is None else prediction.support_status,"power_source":v.power_source})


def waiting_actions(plan,s,case):
    """Reconstruct unavoidable idle consumption between exported actions."""
    waits=[]
    for v in s.vessels:
        path=sorted((c for c in plan.selected if c.vessel_id==v.id),key=lambda c:(c.start,c.id))
        time=v.initial_time
        port=v.initial_port
        fuel=path[0].pathway_id if path else None
        for c in path:
            if c.start>time:
                waits.append(Candidate(f"wait-{c.id}-{case.id}",v.id,"wait",port,port,fuel,time,duration_h=hours(time,c.start)))
            time=max(time,c.end(case));port=c.destination;fuel=c.pathway_id
    return waits


def _totals_for(plan,s):
    estimates=[evaluate_candidate(c,s) for c in plan.selected]
    exclusions=tuple(reason for e in estimates for reason in e.exclusions)
    cases={}
    for case in s.weather_cases:
        wait_estimates=[evaluate_candidate(w,s) for w in waiting_actions(plan,s,case)]
        exclusions+=tuple(reason for e in wait_estimates for reason in e.exclusions)
        cases[case.id]=sum_totals([e.cases[case.id] for e in estimates+wait_estimates if e.eligible])
    return cases,exclusions


def evaluate_rules(plan,s,cases):
    checks=[]
    units={"energy_mj":"MJ","emissions_kg_co2e":"kg_CO2e","cost":s.currency}
    for rule in s.rules:
        status="unknown";value=None;overlap=False;missing_inputs=False
        boundary=set();applicable=set();scoped={}
        for case in required_weather_cases(s):
            totals=[]
            # Filter actual events, including the original path's idle intervals.
            # Reconstructing a filtered subplan would invent waits before later trips.
            events=plan.selected+tuple(waiting_actions(plan,s,case))
            for c in events:
                if rule.vessel_ids and c.vessel_id not in rule.vessel_ids or rule.pathway_ids and c.pathway_id not in rule.pathway_ids:
                    continue
                end=c.end(case)
                if rule.valid_from and end<=rule.valid_from or rule.valid_to and c.start>=rule.valid_to:
                    continue
                overlap=True
                if rule.valid_from and c.start<rule.valid_from or rule.valid_to and end>rule.valid_to:
                    boundary.add(c.id)
                    continue
                estimate=evaluate_candidate(c,s)
                if not estimate.eligible:
                    missing_inputs=True
                    continue
                applicable.add(c.id)
                totals.append(estimate.cases[case.id])
            scoped[case.id]=sum_totals(totals)
        if not overlap:
            status="not_applicable"
        elif rule.applicability_known and rule.source and rule.metric in units and rule.unit==units[rule.metric] and scoped:
            value=max(getattr(t,rule.metric) for t in scoped.values())
            # All supported metrics are additive/nonnegative. A known subset that
            # already exceeds the cap is a sound failure even with an unknown boundary.
            if value>rule.threshold:
                status="fail"
            elif boundary or missing_inputs:
                status="unknown"
            else:
                status="pass"
        checks.append({"id":rule.id,"status":status,"observed":value,"threshold":rule.threshold,"unit":rule.unit,"severity":rule.severity,"scope":rule.jurisdiction,"source":rule.source,"version":rule.version,"applicable_action_ids":sorted(applicable),"boundary_crossing_ids":sorted(boundary),"calculation":"maximum required-case sum of wholly applicable events; crossing events remain unknown"})
    compliance="noncompliant" if any(r["status"]=="fail" for r in checks) else "unknown" if not s.rule_coverage_known or not s.rules or any(r["status"]=="unknown" for r in checks) else "compliant"
    return tuple(checks),compliance


def evaluate_plan(plan,scenario):
    cases,exclusions=_totals_for(plan,scenario)
    nominal=cases[scenario.weather_cases[0].id]
    prices={f.id:f.price_per_kg for f in scenario.pathways}
    consumption=sum(m*prices[f] for f,m in nominal.fuel_kg_by_pathway.items() if prices[f] is not None)
    purchases=sum(c.purchase_kg*prices[c.pathway_id] for c in plan.selected if c.kind=="purchase" and prices.get(c.pathway_id) is not None)
    rules,compliance=evaluate_rules(plan,scenario,cases)
    return PlanEvaluation(nominal,cases,consumption,purchases,rules,compliance,exclusions)
