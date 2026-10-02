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


def repair_plan(preferred,evaluator,weights=None,insertion="greedy"):
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
    def request_priority(r):
        values=sorted(score(c)[2] for c in e.c.items if c.service_id==r.id)
        regret=(values[1]-values[0]) if len(values)>1 else float("inf")
        return (r.release,-regret if insertion=="regret" else 0,r.deadline,r.id)
    for r in sorted(s.services,key=request_priority):
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
    if method in ("alns","nsga2","qie"):
        return {"alns":alns_solve,"nsga2":nsga2_solve,"qie":qie_solve}[method](scenario,candidates,config,cancel,progress)
    raise ValueError(f"unknown solver {method}")


def alns_solve(scenario,candidates,config,cancel=None,progress=None):
    import numpy as np
    e=Evaluator(scenario,candidates,config,"alns",cancel,progress)
    proof=prove_simple_infeasibility(scenario)
    if proof:
        return e.result(proof)
    rng=np.random.default_rng(config.seed)
    operator_weights=np.ones(3);iterations=0;operator_log=[]
    scalarizations=[scenario.weights,(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)]
    try:
        current=repair_plan((),e)
        while True:
            e.check_stop()
            op=int(rng.choice(3,p=operator_weights/operator_weights.sum()))
            services=[c for c in current.selected if c.kind=="service"]
            count=max(1,len(services)//2)
            if op==0:
                removed={c.id for c in rng.choice(services,min(count,len(services)),replace=False)} if services else set()
            elif op==1:
                removed={c.id for c in sorted(services,key=lambda c:balanced_score(evaluate_candidate(c,scenario).nominal.objectives,scenario),reverse=True)[:count]}
            else:
                origin=services[int(rng.integers(len(services)))].origin if services else None
                removed={c.id for c in services if c.origin==origin}
            keep=[c for c in current.selected if c.id not in removed]
            # Diversification changes choices only within the shared, frozen candidate set.
            alternatives=[c for c in candidates.items if c.kind=="service" and c.id not in removed]
            if alternatives:
                keep.append(alternatives[int(rng.integers(len(alternatives)))])
            before=len(e.archive)
            weights=scalarizations[iterations%len(scalarizations)]
            proposed=repair_plan(keep,e,weights,insertion="regret" if iterations%2 else "greedy")
            new=evaluate_plan(proposed,scenario).nominal.objectives
            old=evaluate_plan(current,scenario).nominal.objectives
            delta=sum(w*(a-b)/n for w,a,b,n in zip(weights,new,old,scenario.normalization))
            feasible=e.complete(proposed) and not e.last_violations
            temperature=.01/(1+iterations*.05)
            accepted=feasible and (delta<=0 or rng.random()<np.exp(-min(delta/temperature,700)))
            if accepted:
                current=proposed
            reward=5 if len(e.archive)>before else 2 if accepted else .5
            operator_weights[op]=.8*operator_weights[op]+.2*reward
            operator_log.append({"iteration":iterations,"removal":["random","worst_cost","related_origin"][op],"insertion":"regret" if iterations%2 else "greedy","accepted":bool(accepted),"weights":weights})
            iterations+=1
    except SearchStopped:
        pass
    result=e.result()
    return replace(result,metadata={**result.metadata,"alns_operator_log":operator_log,"operator_weights":operator_weights.tolist(),"adaptation":"prototype scalarized multi-objective ALNS"})


def qie_solve(scenario,candidates,config,cancel=None,progress=None):
    from .qie import SearchProblem,qie_search
    e=Evaluator(scenario,candidates,config,"qie",cancel,progress)
    proof=prove_simple_infeasibility(scenario)
    if proof:
        return e.result(proof)
    if not candidates.items:
        e.check(Plan(()));return e.result()
    trace=None;generations=[]
    def evaluate(bits):
        p=repair_plan([c for c,b in zip(candidates.items,bits) if b],e)
        violations,obj=e.check(p)
        return (len(violations)/max(1,len(scenario.services)),*(x/n for x,n in zip(obj,scenario.normalization)))
    try:
        repair_plan((),e)
        trace=qie_search(SearchProblem(len(candidates.items),evaluate,True,generations.append),config)
    except SearchStopped:
        pass
    r=e.result()
    return replace(r,metadata={**r.metadata,"qie_generations":generations,"qie_encoding":"one bit per immutable action; deterministic repair; feasibility/nondomination/crowding ranking"})


def nsga2_solve(scenario,candidates,config,cancel=None,progress=None):
    import numpy as np
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.operators.sampling.rnd import BinaryRandomSampling
    from pymoo.operators.crossover.pntx import TwoPointCrossover
    from pymoo.operators.mutation.bitflip import BitflipMutation
    from pymoo.optimize import minimize
    e=Evaluator(scenario,candidates,config,"nsga2",cancel,progress)
    proof=prove_simple_infeasibility(scenario)
    if proof:
        return e.result(proof)
    if not candidates.items:
        e.check(Plan(()));return e.result()
    class FleetProblem(ElementwiseProblem):
        def __init__(self):
            super().__init__(n_var=len(candidates.items),n_obj=3,n_ieq_constr=1,xl=0,xu=1,vtype=bool)
        def _evaluate(self,x,out,*args,**kwargs):
            p=repair_plan([c for c,b in zip(candidates.items,x) if b],e)
            violations,obj=e.check(p)
            out["F"]=np.array(obj)/scenario.normalization
            out["G"]=np.array([len(violations)/max(1,len(scenario.services))])
    try:
        repair_plan((),e)
        algorithm=NSGA2(pop_size=config.population_size,sampling=BinaryRandomSampling(),crossover=TwoPointCrossover(),mutation=BitflipMutation(),eliminate_duplicates=False)
        minimize(FleetProblem(),algorithm,("n_eval",config.budget),seed=config.seed,verbose=False)
    except SearchStopped:
        pass
    return e.result()
