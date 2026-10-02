"""Reproducible paired experiments; synthetic demonstrations are not empirical claims."""
from __future__ import annotations
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import csv
import json
import os
import platform
import numpy as np
import psutil
import yaml
from .contracts import *
from .ingest import demo_dataset,load_bundle,fingerprint_dataset
from .splits import make_splits
from .predict import fit_predictor,prediction_report
from .candidates import build_candidates
from .solvers import solve,balanced_score,exact_tiny_solve
from .accounting import evaluate_plan
from .feasibility import validate_plan


def hypervolume(objectives,reference_point,normalization):
    if not len(objectives):
        return None
    from pymoo.indicators.hv import HV
    return float(HV(ref_point=np.array(reference_point))(np.array(objectives)/normalization))


def evaluate_heldout_decision(plan,development,heldout,candidates):
    # Re-score the same immutable deployment; do not choose again with hindsight.
    a=evaluate_plan(plan,development)
    b=evaluate_plan(plan,heldout)
    checked=validate_plan(plan,heldout,replace(candidates,scenario_hash=digest(heldout)))
    return {"chosen_plan_hash":plan.hash,"development":primitive(a.nominal),"realized":primitive(b.nominal),"violations":primitive(checked),"regret":None,"replay_label":"independently simulated conditions; not observed counterfactuals"}


def paired_interval(values_a,values_b,seed=17):
    pairs=[(a,b) for a,b in zip(values_a,values_b) if a is not None and b is not None]
    if not pairs:
        return {"paired_n":0,"mean_difference":None,"ci95":None}
    differences=np.array([a-b for a,b in pairs]);rng=np.random.default_rng(seed)
    means=np.mean(rng.choice(differences,(2000,len(differences)),replace=True),axis=1)
    return {"paired_n":len(pairs),"mean_difference":float(np.mean(differences)),"ci95":[float(x) for x in np.quantile(means,[.025,.975])],"unit":"paired seed; feasible pairs only"}


def hardware_manifest():
    return {"python":platform.python_version(),"platform":platform.platform(),"cpu":platform.processor(),"cpu_count":os.cpu_count(),"memory_bytes":psutil.virtual_memory().total,"dependencies":{n:version(n) for n in ("numpy","pandas","scikit-learn","scipy","pymoo","streamlit","plotly","pyarrow")}}


def _write_json(path,value):
    with Path(path).open("x",encoding="utf-8") as f:
        json.dump(primitive(value),f,indent=2,allow_nan=False)


def _case_studies(s,config):
    variants={"conventional":s,"shore_off":replace(s,shore_enabled=False),"increased_demand":replace(s,services=tuple(replace(r,demand_t=r.demand_t*1.5) for r in s.services)),"adverse_weather":replace(s,weather_cases=(s.weather_cases[0],WeatherCase("storm",1.5,1.4))),"price_increase":replace(s,pathways=tuple(replace(f,price_per_kg=f.price_per_kg*1.5 if f.price_per_kg is not None else None) for f in s.pathways)),"grid_intensity_increase":replace(s,ports=tuple(replace(p,grid_kg_kwh=p.grid_kg_kwh*2 if p.grid_kg_kwh is not None else None) for p in s.ports)),"pathway_intensity_change":replace(s,pathways=tuple(replace(f,wtw_g_mj=f.wtw_g_mj*.8 if f.wtw_g_mj is not None else None) for f in s.pathways))}
    rows=[]
    for name,scenario in variants.items():
        c=build_candidates(scenario)
        r=solve(scenario,c,"greedy",config)
        rows.append({"case":name,"status":r.status,"candidate_hash":c.hash,"totals":primitive(evaluate_plan(r.plans[0],scenario).nominal) if r.plans else None,"violations":primitive(r.violations),"candidate_limit_reached":c.candidate_limit_reached})
    for fuel in ("LNG","methanol","hydrogen","ammonia"):
        present=tuple(f for f in s.pathways if f.fuel_name.lower()==fuel.lower())
        if not present:
            rows.append({"case":fuel,"status":"excluded","reason":"No validated vessel, engine, pathway and port dataset supplied; no substitute factors invented."})
        else:
            allowed={f.id for f in present}
            c=build_candidates(s)
            c=replace(c,items=tuple(x for x in c.items if x.pathway_id in allowed),complete=False)
            r=solve(s,c,"greedy",config)
            rows.append({"case":fuel,"status":r.status,"totals":primitive(evaluate_plan(r.plans[0],s).nominal) if r.plans else None,"exclusions":primitive(c.exclusions)})
    return rows


def tiny_frontier_comparison(seeds,budget):
    s=demo_dataset().scenario
    v=replace(s.vessels[0],auxiliary_kw=0,power_coefficient=.1)
    r=replace(s.services[0],distance_nm=10,loading_h=0,unloading_h=0,demand_t=100)
    s=replace(s,vessels=(v,),services=(r,),weather_cases=(s.weather_cases[0],))
    slow=Candidate("tiny-slow",v.id,"service","A","B","diesel",s.start,r.id,10,10,100)
    c=CandidateSet((slow,replace(slow,id="tiny-fast",speed_kn=12)))
    # The fast option uses an explicitly expanded validated speed interval.
    s=replace(s,vessels=(replace(v,max_speed_kn=12),))
    exact=exact_tiny_solve(s,c)
    frontier=[evaluate_plan(p,s).nominal.objectives for p in exact.plans]
    rows=[]
    for seed in seeds:
        for method in ("greedy","alns","nsga2","qie"):
            result=solve(s,c,method,SearchConfig(budget=budget,seed=seed))
            values=[evaluate_plan(p,s).nominal.objectives for p in result.plans]
            gap=float(np.mean([min(np.linalg.norm((np.array(a)-b)/s.normalization) for b in values) for a in frontier])) if values else None
            rows.append({"method":method,"seed":seed,"status":result.status,"normalized_exact_frontier_gap":gap,"evaluations":result.metadata["evaluations"]})
    return {"synthetic":True,"candidate_hash":c.hash,"frontier":frontier,"exact_evaluations":exact.metadata["evaluations"],"runs":rows}


def run_benchmarks(config_path: Path,output_dir: Path) -> Path:
    cfg=yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    data=load_bundle(Path(cfg["bundle"])) if cfg.get("bundle") else demo_dataset()
    s=replace(data.scenario,max_candidates=int(cfg.get("max_candidates",data.scenario.max_candidates)),normalization=tuple(cfg.get("normalization",data.scenario.normalization)),weights=tuple(cfg.get("weights",data.scenario.weights)))
    data=replace(data,scenario=s)
    seeds=list(range(int(cfg.get("seeds",20))))
    methods=cfg.get("methods",["greedy","alns","nsga2","qie"])
    budget=int(cfg.get("budget",128));wall=float(cfg.get("wall_clock_s",1))
    root=Path(output_dir)/("benchmark-"+uuid4().hex)
    root.mkdir(parents=True)
    start=perf_counter();candidates=build_candidates(s);generation_s=perf_counter()-start
    split=make_splits(data,"future",17)
    reference=cfg.get("reference_point",[2.,2.,2.])
    frozen={"dataset_hash":fingerprint_dataset(data),"split_hash":split.hash,"candidate_hash":candidates.hash,"factor_hash":digest((s.pathways,s.engine_fuels,s.ports)),"normalization":s.normalization,"weights":s.weights,"reference_point":reference,"seeds":seeds,"methods":methods,"budget":budget,"wall_clock_s":wall,"candidate_generation_s":generation_s,"candidate_counts":candidates.stats,"candidate_limit_reached":candidates.candidate_limit_reached,"config":cfg,"selection_rule":"lowest fixed weighted normalized nominal objective among independently feasible plans; feasibility rate and runtime guardrails; synthetic demonstration only"}
    _write_json(root/"frozen-inputs.json",frozen)
    rows=[];heldout=[];process=psutil.Process()
    heldout_s=replace(s,weather_cases=(s.weather_cases[0],WeatherCase("independent_adverse",1.3,1.25)))
    for comparison in ("equal_evaluations","equal_wall_clock"):
        for seed in seeds:
            for method in methods:
                config=SearchConfig(budget=budget if comparison=="equal_evaluations" else 1000000,seed=seed,timeout_s=None if comparison=="equal_evaluations" else wall)
                peak=[process.memory_info().rss]
                def sample_memory(done,total):
                    peak[0]=max(peak[0],process.memory_info().rss)
                t=perf_counter()
                try:
                    result=solve(s,candidates,method,config,progress=sample_memory)
                    objectives=[evaluate_plan(p,s).nominal.objectives for p in result.plans]
                    best=min(result.plans,key=lambda p:balanced_score(evaluate_plan(p,s).nominal.objectives,s)) if result.plans else None
                    row={"comparison":comparison,"method":method,"seed":seed,"budget":config.budget,"timeout_s":config.timeout_s,"status":result.status,"evaluations":result.metadata["evaluations"],"repair_calls":result.metadata["repair_calls"],"runtime_s":perf_counter()-t,"stop_reason":result.metadata["stop_reason"],"hypervolume":hypervolume(objectives,reference,s.normalization),"objectives":objectives,"selected_totals":primitive(evaluate_plan(best,s).nominal) if best else None,"peak_rss_bytes":peak[0],"evaluator_hash":result.metadata["evaluator_hash"],"convergence":result.metadata["convergence"]}
                    if best:
                        heldout.append({"comparison":comparison,"method":method,"seed":seed,**evaluate_heldout_decision(best,s,heldout_s,candidates)})
                except Exception as exc:
                    row={"comparison":comparison,"method":method,"seed":seed,"budget":config.budget,"status":"failed","error":f"{type(exc).__name__}: {exc}","runtime_s":perf_counter()-t,"evaluations":None,"hypervolume":None,"selected_totals":None,"peak_rss_bytes":peak[0]}
                row.update({k:frozen[k] for k in ("dataset_hash","split_hash","candidate_hash","factor_hash")})
                rows.append(row)
    predictions=[]
    if cfg.get("prediction",True):
        for protocol in ("future","unseen_vessel"):
            split=make_splits(data,protocol,17)
            for seed in seeds:
                for method in ("engineering","direct","residual","random_tuned","qie_tuned"):
                    t=perf_counter()
                    try:
                        p=fit_predictor(data,split,method,int(cfg.get("fit_budget",4)),seed)
                        predictions.append({"method":method,"seed":seed,"fit_count":p.fit_count,"fit_budget":int(cfg.get("fit_budget",4)),"end_to_end_s":perf_counter()-t,**prediction_report(p,data)})
                    except ValueError as exc:
                        predictions.append({"method":method,"seed":seed,"protocol":protocol,"status":"excluded","reason":str(exc)})
    scales=[]
    for n in cfg.get("scales",[10,50,100]):
        fleet=tuple(replace(s.vessels[i%len(s.vessels)],id=f"scale-V{i}") for i in range(n))
        scaled=replace(s,vessels=fleet)
        t=perf_counter();cs=build_candidates(scaled)
        entry={"vessels":n,"candidate_generation_s":perf_counter()-t,"candidate_count":len(cs.items),"candidate_limit_reached":cs.candidate_limit_reached}
        if cs.candidate_limit_reached:
            entry.update(status="not_benchmarked",reason="candidate cap reached; narrow scenario before a complete scale comparison")
        else:
            entry["runs"]=[primitive(solve(scaled,cs,m,SearchConfig(budget=budget,timeout_s=wall)).metadata) for m in methods]
        scales.append(entry)
    ablations=[]
    if cfg.get("prediction",True):
        dev=make_splits(data,"future",17)
        for label,predict_method,fleet_method in (("conventional","engineering","greedy"),("predictor_tuning_only","qie_tuned","greedy"),("fleet_search_only","engineering","qie"),("combined","qie_tuned","qie")):
            p=fit_predictor(data,dev,predict_method,int(cfg.get("fit_budget",4)),17)
            t=perf_counter();cs=build_candidates(s,p);elapsed=perf_counter()-t
            r=solve(s,cs,fleet_method,SearchConfig(budget=budget,seed=17))
            ablations.append({"label":label,"predictor":predict_method,"solver":fleet_method,"candidate_generation_s":elapsed,"model_fit_s":p.fit_seconds,"status":r.status,"candidate_hash":cs.hash,"model_id":p.model_id,"totals":[primitive(evaluate_plan(x,s).nominal) for x in r.plans]})
    summary=[]
    for comparison in ("equal_evaluations","equal_wall_clock"):
        for method in methods:
            subset=[r for r in rows if r["comparison"]==comparison and r["method"]==method]
            feasible=[r for r in subset if r["status"]=="completed"]
            summary.append({"comparison":comparison,"method":method,"runs":len(subset),"feasible_fraction":len(feasible)/len(subset) if subset else None,"median_runtime_s":float(np.median([r["runtime_s"] for r in subset])) if subset else None,"median_hypervolume":float(np.median([r["hypervolume"] for r in feasible])) if feasible else None,"median_objectives":[float(np.median([r["selected_totals"][key] for r in feasible])) for key in ("energy_mj","cost","emissions_kg_co2e")] if feasible else None})
    intervals=[]
    for comparison in ("equal_evaluations","equal_wall_clock"):
        for method in methods[1:]:
            a=[next((r["hypervolume"] for r in rows if r["method"]==method and r["seed"]==seed and r["comparison"]==comparison),None) for seed in seeds]
            b=[next((r["hypervolume"] for r in rows if r["method"]==methods[0] and r["seed"]==seed and r["comparison"]==comparison),None) for seed in seeds]
            intervals.append({"comparison":comparison,"method":method,"reference_method":methods[0],**paired_interval(a,b)})
    manifest={**frozen,"synthetic":s.synthetic,"hardware":hardware_manifest(),"runs":rows,"prediction":predictions,"heldout_decisions":heldout,"tiny_frontier":tiny_frontier_comparison(seeds,budget),"case_studies":_case_studies(s,SearchConfig(budget=budget)) if cfg.get("case_studies",True) else [],"scales":scales,"ablations":ablations,"summary":summary,"paired_intervals":intervals,"limitations":["Synthetic results demonstrate software behavior only." if s.synthetic else "Operational interpretation requires domain review.","Fixed engineering/direct/residual references use zero/one fit; QIE and random tuners share the declared fit budget.","Greedy can stop before the shared evaluation ceiling; actual calls and repair attempts are recorded.","Peak RSS is sampled at shared evaluations, not a continuous OS high-water mark.","Exact-frontier acceptance is established on the committed tiny test fixture; a capped fleet universe has no global exact frontier.","Held-out replay is simulated and cannot establish observed counterfactual regret."]}
    _write_json(root/"manifest.json",manifest)
    with (root/"summary.csv").open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]) if summary else ["method"])
        writer.writeheader();writer.writerows(summary)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4))
    for method in methods:
        traces=[r for r in rows if r["method"]==method and r["comparison"]=="equal_evaluations"]
        points={}
        for r in traces:
            for row in r.get("convergence",[]):
                if row["best_balanced"] is not None:
                    points.setdefault(row["evaluation"],[]).append(row["best_balanced"])
        xs=sorted(points)
        ax.plot(xs,[np.median(points[x]) for x in xs],label=method)
    ax.set(xlabel="Shared evaluator calls (including repair trials)",ylabel="Fixed normalized weighted objective",title="Synthetic convergence — feasible runs only" if s.synthetic else "Convergence — feasible runs only")
    ax.legend();fig.tight_layout();fig.savefig(root/"convergence.svg");plt.close(fig)
    text="# GreenFleet benchmark\n\n"+("**SYNTHETIC DEMONSTRATION. No empirical superiority or savings claim.**\n\n" if s.synthetic else "Domain review required.\n\n")
    text+=f"Paired seeds: {len(seeds)}. Candidate cap: {s.max_candidates}. Cap reached: {candidates.candidate_limit_reached}.\n\n"
    text+="| Comparison | Method | Feasible fraction | Median seconds | Median hypervolume |\n|---|---|---:|---:|---:|\n"
    for row in summary:
        text+=f"| {row['comparison']} | {row['method']} | {row['feasible_fraction']} | {row['median_runtime_s']:.4f} | {row['median_hypervolume']} |\n"
    text+="\nSee manifest.json for per-seed outcomes, null metrics, held-out replay, case studies, hashes and limitations.\n"
    (root/"report.md").write_text(text,encoding="utf-8")
    return root/"manifest.json"
