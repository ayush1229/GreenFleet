from __future__ import annotations
from dataclasses import replace
from itertools import product
from time import perf_counter
from .contracts import *
from .accounting import evaluate_candidate,evaluate_plan
from .feasibility import validate_plan,prove_simple_infeasibility


def dominates(a,b):
    return all(x<=y+1e-9 for x,y in zip(a,b)) and any(x<y-1e-9 for x,y in zip(a,b))


def balanced_score(objectives,s):
    return sum(w*x/n for w,x,n in zip(s.weights,objectives,s.normalization))


class SearchStopped(Exception):
    pass


class Evaluator:
    """One accounting/feasibility gate, shared by every solver and repair attempt."""
    def __init__(self,s,c,config,method,cancel=None,progress=None):
        self.s,self.c,self.config,self.method=s,c,config,method
        self.cancel,self.progress=cancel,progress
        self.started=perf_counter();self.evaluations=0;self.repair_calls=0
        self.archive={};self.objectives={};self.last_violations=();self.log=[]
        self.stop_reason="budget";self.cancelled=False
        self.candidate_hash=c.hash
        self.evaluator_hash=digest({"version":"greenfleet-evaluator-1","scenario":s,"model":c.model_id})

    def check_stop(self):
        if self.cancel and self.cancel():
            self.cancelled=True;self.stop_reason="cancelled";raise SearchStopped()
        if self.config.timeout_s is not None and perf_counter()-self.started>=self.config.timeout_s:
            self.stop_reason="timeout";raise SearchStopped()
        if self.evaluations>=self.config.budget:
            self.stop_reason="budget";raise SearchStopped()

    def complete(self,plan):
        for r in self.s.services:
            cs=[c for c in plan.selected if c.kind=="service" and c.service_id==r.id]
            if abs(sum(c.cargo_t for c in cs)-r.demand_t)>1e-7 or not r.allow_split and len(cs)!=1:
                return False
        return True

    def check(self,plan,partial=False):
        self.check_stop()
        self.evaluations+=1
        violations=validate_plan(plan,self.s,self.c,partial=partial)
        evaluation=evaluate_plan(plan,self.s)
        obj=evaluation.nominal.objectives
        if evaluation.exclusions:
            violations+= [Violation(x) for x in evaluation.exclusions]
        self.last_violations=tuple(violations)
        if not violations and self.complete(plan):
            # Partial construction cannot bypass a final independent check.
            final=validate_plan(plan,self.s,self.c)
            if not final:
                self.add_archive(plan,obj)
        self.log.append({"evaluation":self.evaluations,"feasible":not violations and self.complete(plan),"violations":len(violations),"archive_size":len(self.archive),"best_balanced":min((balanced_score(x,self.s) for x in self.objectives.values()),default=None),"elapsed_s":perf_counter()-self.started})
        if self.progress:
            self.progress(self.evaluations,self.config.budget)
        return tuple(violations),obj

    def add_archive(self,plan,obj):
        key=plan.hash
        if any(dominates(other,obj) or all(abs(a-b)<1e-9 for a,b in zip(other,obj)) for other in self.objectives.values()):
            return
        for old in list(self.archive):
            if dominates(obj,self.objectives[old]):
                self.archive.pop(old);self.objectives.pop(old)
        self.archive[key]=plan;self.objectives[key]=obj

    def result(self,proof=None,exact_complete=False):
        if self.cancel and self.cancel():
            self.cancelled=True;self.stop_reason="cancelled"
        plans=tuple(self.archive[k] for k in sorted(self.archive))
        if self.cancelled:
            status="cancelled";plans=()
        elif plans:
            status="completed"
        elif proof or exact_complete and self.c.complete:
            status="infeasible_proven"
        else:
            status="no_feasible_solution_found"
        compliance="unknown"
        if plans:
            statuses={evaluate_plan(p,self.s).compliance_status for p in plans}
            compliance="noncompliant" if "noncompliant" in statuses else "unknown" if "unknown" in statuses else "compliant"
        metadata={"method":self.method,"seed":self.config.seed,"config":primitive(self.config),"evaluations":self.evaluations,"repair_calls":self.repair_calls,"candidate_hash":self.candidate_hash,"evaluator_hash":self.evaluator_hash,"model_id":self.c.model_id,"scenario_hash":digest(self.s),"candidate_limit_reached":self.c.candidate_limit_reached,"candidate_complete":self.c.complete,"candidate_counts":self.c.stats,"exclusions":self.c.exclusions,"synthetic":self.s.synthetic,"runtime_s":perf_counter()-self.started,"stop_reason":self.stop_reason,"convergence":self.log,"normalization":self.s.normalization,"weights":self.s.weights,"proof":primitive(proof) if proof else None,"exact_enumeration_complete":exact_complete,"compliance_label":"operationally feasible under configured constraints; compliance unverified" if compliance=="unknown" else "configured rule set only"}
        return RunResult(status,plans,self.last_violations,compliance,metadata)


def repair_plan(preferred,evaluator,weights=None):
    """Deterministic insertion from the frozen universe. Every trial consumes budget."""
    e=evaluator;s=e.s
    e.repair_calls+=1
    preferred_ids={c.id for c in preferred}
    selected=[]
    costs={}
    def score(c):
        if c.id not in costs:
            estimate=evaluate_candidate(c,s)
            costs[c.id]=sum(w*x/n for w,x,n in zip(weights or s.weights,estimate.nominal.objectives,s.normalization)) if estimate.eligible else float("inf")
        return (c.id not in preferred_ids,c.start,costs[c.id],c.id)
    helpers=[c for c in e.c.items if c.kind!="service"]
    for r in sorted(s.services,key=lambda x:(x.release,x.deadline,x.id)):
        remaining=r.demand_t
        options=sorted((c for c in e.c.items if c.service_id==r.id and c.kind=="service"),key=score)
        for c in options:
            if remaining<=1e-7:
                break
            if c.cargo_t>remaining+1e-7 or c in selected:
                continue
            trial=selected+[c]
            violations,_=e.check(Plan(tuple(trial)),partial=True)
            if violations:
                # Connect only a reachable explicit reposition, then a recorded purchase/changeover.
                for kind,codes in (("reposition",{"location"}),("changeover",{"missing_changeover"}),("purchase",{"fuel_reserve"})):
                    if not codes.intersection(v.code for v in violations):
                        continue
                    choices=[h for h in helpers if h.kind==kind and h.vessel_id==c.vessel_id and h.id not in {x.id for x in trial} and h.start<c.start and all(h.end(w)<=c.start for w in s.weather_cases if w.required)]
                    choices.sort(key=lambda h:(h.id not in preferred_ids,-h.start.timestamp(),h.purchase_kg,h.id))
                    for h in choices:
                        proposed=trial+[h]
                        new_violations,_=e.check(Plan(tuple(proposed)),partial=True)
                        if not new_violations or len(new_violations)<len(violations):
                            trial=proposed;violations=new_violations
                            break
            if not violations:
                selected=trial;remaining-=c.cargo_t
    plan=Plan(tuple(sorted(selected,key=lambda c:(c.start,c.vessel_id,c.id))),{"candidate_hash":e.candidate_hash,"evaluator_hash":e.evaluator_hash})
    e.check(plan)
    return plan


def greedy_solve(scenario,candidates,config,cancel=None,progress=None):
    e=Evaluator(scenario,candidates,config,"greedy",cancel,progress)
    proof=prove_simple_infeasibility(scenario)
    if proof:
        return e.result(proof)
    try:
        repair_plan((),e)
        e.stop_reason="greedy_complete"
    except SearchStopped:
        pass
    return e.result()


def exact_tiny_solve(scenario,candidates,config=None,cancel=None,progress=None):
    if len(candidates.items)>20:
        raise ValueError("exact enumeration limited to 20 choice bits")
    n=2**len(candidates.items)
    e=Evaluator(scenario,candidates,config or SearchConfig(budget=n),"exact_tiny",cancel,progress)
    proof=prove_simple_infeasibility(scenario)
    if proof:
        return e.result(proof)
    complete=False
    try:
        for bits in product((0,1),repeat=len(candidates.items)):
            e.check(Plan(tuple(c for c,b in zip(candidates.items,bits) if b)))
        complete=True;e.stop_reason="exhaustive"
    except SearchStopped:
        pass
    return e.result(exact_complete=complete)


def solve(scenario,candidates,method,config,cancel=None,progress=None):
    if method=="greedy":
        return greedy_solve(scenario,candidates,config,cancel,progress)
    if method=="exact_tiny":
        return exact_tiny_solve(scenario,candidates,config,cancel,progress)
    raise ValueError(f"unknown solver {method}")
