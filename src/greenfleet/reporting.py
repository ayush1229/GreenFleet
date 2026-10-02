from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import csv
import io
import re
from .contracts import *
from .ingest import scenario_from_dict
from .accounting import evaluate_plan,evaluate_candidate,waiting_actions
from .feasibility import validate_plan
from .runs import atomic_write,atomic_json


def safe_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@","\t","\r")):
        return "'"+value
    return value


def _csv(path,rows,columns):
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=columns,extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k:safe_cell(v) for k,v in row.items() if k in columns})
    atomic_write(path,out.getvalue())


def export_run(result,output_dir):
    run_id=re.sub(r"[^A-Za-z0-9_-]","_",str(result.metadata.get("run_id","run")))[:100]
    root=Path(output_dir)/(run_id+"-export-"+uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    scenario=scenario_from_dict(primitive(result.metadata["scenario"]))
    summaries=[];deployment=[];purchases=[];rules=[];inventory=[]
    plans=result.plans if result.status=="completed" else ()
    for plan in plans:
        checked=validate_plan(plan,scenario,CandidateSet(plan.selected,complete=False))
        if checked:
            raise ValueError("refusing to export an independently invalid recommendation")
        evaluation=evaluate_plan(plan,scenario)
        summaries.append({"plan_hash":plan.hash,**primitive(evaluation)})
        for c in sorted(plan.selected,key=lambda x:(x.start,x.vessel_id,x.id)):
            row={"plan_hash":plan.hash,**primitive(c),"end_utc":c.end().isoformat(),"conservative_end_utc":max(c.end(w) for w in required_weather_cases(scenario)).isoformat(),"support":c.prediction.support_status if c.prediction else "engineering_only"}
            deployment.append(row)
            if c.kind=="purchase":
                purchases.append(row)
        rules.extend({"plan_hash":plan.hash,**r} for r in evaluation.rule_results)
        for case in scenario.weather_cases:
            waits=waiting_actions(plan,scenario,case)
            for v in scenario.vessels:
                stock={f:t.initial_kg for f,t in v.tanks.items()}
                actions=sorted([c for c in plan.selected+tuple(waits) if c.vessel_id==v.id],key=lambda c:(c.start,c.id))
                for c in actions:
                    estimate=evaluate_candidate(c,scenario)
                    for f,mass in estimate.cases[case.id].fuel_kg_by_pathway.items():
                        before=stock[f]
                        purchased=c.purchase_kg if c.kind=="purchase" and c.pathway_id==f else 0
                        stock[f]+=purchased-mass
                        inventory.append({"plan_hash":plan.hash,"weather_case":case.id,"vessel_id":v.id,"candidate_id":c.id,"pathway_id":f,"before_kg":before,"purchased_kg":purchased,"consumed_kg":mass,"after_kg":stock[f],"reserve_kg":v.tanks[f].reserve_kg,"capacity_kg":v.tanks[f].capacity_kg})
    atomic_json(root/"summary.json",{"run_id":run_id,"status":result.status,"compliance_status":result.compliance_status,"synthetic":scenario.synthetic,"currency":scenario.currency,"plans":summaries,"violations":primitive(result.violations)})
    atomic_json(root/"provenance.json",result.metadata)
    _csv(root/"deployment.csv",deployment,["plan_hash","id","kind","vessel_id","service_id","origin","destination","pathway_id","start","end_utc","conservative_end_utc","speed_kn","distance_nm","cargo_t","loading_h","unloading_h","shore_kw","support"])
    _csv(root/"purchases.csv",purchases,["plan_hash","id","vessel_id","origin","pathway_id","start","end_utc","purchase_kg","duration_h"])
    _csv(root/"rules.csv",rules,["plan_hash","id","status","observed","threshold","unit","severity","scope","source","version"])
    _csv(root/"inventory.csv",inventory,["plan_hash","weather_case","vessel_id","candidate_id","pathway_id","before_kg","purchased_kg","consumed_kg","after_kg","reserve_kg","capacity_kg"])
    text="# GreenFleet run report\n\n"
    if scenario.synthetic:
        text+="**SYNTHETIC DEMONSTRATION — not evidence of operational savings or certification.**\n\n"
    text+=f"Run: `{run_id}`\n\nStatus: **{result.status}**. Compliance: **{result.compliance_status}**.\n\n"
    if result.compliance_status=="unknown":
        text+="Operationally feasible plans, if present, are under configured constraints; compliance is unverified.\n\n"
    if not plans:
        text+="No final recommendation. See violations and run log.\n\n"
    text+=f"Method: {result.metadata.get('method',result.metadata.get('config',{}).get('method','unknown'))}. Currency: {scenario.currency}, price date: {scenario.price_date}.\n\n"
    text+="| Plan | Energy MJ | Financial cost | Lifecycle kg CO2e | Electricity kWh |\n|---|---:|---:|---:|---:|\n"
    for summary in summaries:
        t=summary["nominal"]
        text+=f"| {summary['plan_hash'][:12]} | {t['energy_mj']:.3f} | {t['cost']:.3f} | {t['emissions_kg_co2e']:.3f} | {t['electricity_kwh']:.3f} |\n"
    text+=f"\nInventory convention: {scenario.inventory_cost}. Purchase and consumed-fuel value are reported separately.\n\n"
    text+="Nominal and every weather case, factors, rule checks, seeds, normalization, split/model/candidate hashes and exclusions are in summary.json and provenance.json. Candidate caps and heuristic failure cannot prove global infeasibility.\n"
    atomic_write(root/"report.md",text)
    return sorted(root.iterdir())
