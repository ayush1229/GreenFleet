"""Thin Streamlit orchestration; calculations use the tested domain engine."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
import io
import json
import zipfile
import pandas as pd
import plotly.express as px
import streamlit as st
from greenfleet.contracts import primitive, digest, RunConfig, SearchConfig, Rule
from greenfleet.ingest import demo_dataset, load_bundle_dict, validate_scenario, BundleError, scenario_from_dict
from greenfleet.runs import execute_run
from greenfleet.reporting import export_run
from greenfleet.accounting import evaluate_plan
from greenfleet.solvers import balanced_score

ROOT = Path(__file__).parent
st.set_page_config(page_title="GreenFleet", page_icon="🚢", layout="wide")
st.title("GreenFleet")
st.caption("Auditable fleet planning · Energy, operating cost and lifecycle emissions")


@st.cache_resource
def workers():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="greenfleet")


data = demo_dataset()
with st.sidebar:
    st.header("Scenario")
    upload = st.file_uploader("JSON data bundle", type=["json"])
    if upload:
        try:
            data = load_bundle_dict(json.loads(upload.getvalue()))
        except (BundleError, ValueError, TypeError, KeyError) as exc:
            st.error(f"Bundle validation failed: {exc}")
            st.stop()
    preset = st.selectbox("Demonstration case", ["Feasible / unknown rules", "Impossible demand", "Missing lifecycle factor", "Known hard emissions limit"])
    demand = st.slider("Demand multiplier", .5, 3., 1., .1)
    shore = st.toggle("Allow shore power", value=True)
    weather = st.slider("Adverse transit multiplier", 1., 2., 1.2, .05)
    price = st.slider("Fuel price multiplier", .5, 3., 1., .1)
    certified = st.checkbox("Require verified configured-rule compliance")
    cap = st.number_input("Candidate cap", min_value=10, max_value=200000, value=2000, step=100)
    st.divider()
    method = st.selectbox("Fleet method", ["greedy", "alns", "nsga2", "qie"])
    predictor_method = st.selectbox("Fuel predictor", ["engineering", "direct", "residual", "qie_tuned", "qie_residual"])
    budget = st.number_input("Evaluator budget", min_value=4, max_value=100000, value=128, step=16)
    seed = st.number_input("Random seed", min_value=0, value=17)
    timeout = st.number_input("Search time limit (seconds)", min_value=1., value=30.)
    st.caption("QIE tunes a classical regression model. All methods share an independent feasibility checker.")

s = data.scenario
s = replace(s, services=tuple(replace(r, demand_t=r.demand_t*demand) for r in s.services), shore_enabled=shore, require_certified_compliance=certified, max_candidates=int(cap), pathways=tuple(replace(f, price_per_kg=f.price_per_kg*price if f.price_per_kg is not None else None) for f in s.pathways), weather_cases=tuple(replace(w, time_multiplier=weather) if i else w for i, w in enumerate(s.weather_cases)))
if preset == "Impossible demand":
    s = replace(s, services=(replace(s.services[0], demand_t=max(v.capacity_t for v in s.vessels)+1),)+s.services[1:])
elif preset == "Missing lifecycle factor":
    s = replace(s, pathways=tuple(replace(f, wtw_g_mj=None, wtt_g_mj=None, ttw_g_mj=None) for f in s.pathways))
elif preset == "Known hard emissions limit":
    s = replace(s, rules=(Rule("demo-cap", "synthetic scope", "demo-1", "emissions_kg_co2e", "kg_CO2e", 1, "synthetic acceptance fixture"),), rule_coverage_known=True)
data = replace(data, scenario=s)
if s.synthetic:
    st.warning("SYNTHETIC DEMONSTRATION — no real-world accuracy, savings or certification claims.")
violations = validate_scenario(s)
if violations:
    st.error("Scenario validation failed")
    st.dataframe([primitive(x) for x in violations])
    st.stop()
st.success("Scenario valid under the configured schema.")
cols = st.columns(4)
cols[0].metric("Vessels", len(s.vessels))
cols[1].metric("Requests", len(s.services))
cols[2].metric("Horizon", "7 days" if (s.end-s.start).days == 7 else str(s.end-s.start))
cols[3].metric("Regulatory coverage", "Configured" if s.rule_coverage_known else "Unverified")


def start_run(selected_method):
    event = Event()
    state = {"done": 0, "total": int(budget)}
    def progress(done, total):
        state.update(done=done, total=total)
    config = RunConfig(selected_method, SearchConfig(budget=int(budget), seed=int(seed), timeout_s=float(timeout)), predictor_method)
    future = workers().submit(execute_run, s, config, ROOT/"outputs"/"runs", cancel=event.is_set, progress=progress, dataset=data)
    st.session_state["job"] = {"future": future, "event": event, "progress": state, "scenario_hash": digest(s)}


@st.fragment(run_every="1s")
def run_panel():
    job = st.session_state.get("job")
    if not job:
        st.info("Run a conventional baseline or compare a fleet method to inspect verified plans.")
        return
    if not job["future"].done():
        state = job["progress"]
        st.progress(min(1., state["done"]/max(1, state["total"])), text=f"{state['done']} evaluator calls · preparing or searching")
        if st.button("Cancel run"):
            job["event"].set()
            st.info("Cancellation requested. Partial plans will be withheld.")
        return
    result = job["future"].result()
    st.subheader(f"Run: {result.status.replace('_', ' ')}")
    run_s = scenario_from_dict(primitive(result.metadata["scenario"]))
    if job["scenario_hash"] != digest(s):
        st.info("Showing the saved scenario from this run. Controls have changed; start a new run to apply them.")
    st.caption(f"{result.metadata['run_id']} · {result.metadata.get('method', method)} · {result.metadata.get('evaluations', 0)} evaluations")
    if result.compliance_status == "unknown":
        st.warning("Compliance unverified. Any plan shown is operationally feasible only under the configured constraints.")
    else:
        st.info(f"Compliance: {result.compliance_status} — configured scope and date only.")
    if result.metadata.get("candidate_limit_reached"):
        st.warning("Candidate cap reached. Results cover a limited candidate set; narrow the scenario or increase the cap for wider coverage.")
    if result.plans:
        evaluations = [evaluate_plan(p, run_s) for p in result.plans]
        rows = [{"plan": i+1, "Energy (MJ)": e.nominal.energy_mj, f"Cost ({run_s.currency})": e.nominal.cost, "Lifecycle emissions (kg CO2e)": e.nominal.emissions_kg_co2e} for i, e in enumerate(evaluations)]
        st.plotly_chart(px.scatter(pd.DataFrame(rows), x=f"Cost ({run_s.currency})", y="Lifecycle emissions (kg CO2e)", color="Energy (MJ)", hover_name="plan", title="Verified feasible Pareto plans"), width="stretch")
        choice = st.radio("Plan selection", ["Balanced", "Lowest cost", "Lowest emissions"], horizontal=True)
        key = {"Balanced": lambda i: balanced_score(evaluations[i].nominal.objectives, run_s), "Lowest cost": lambda i: evaluations[i].nominal.cost, "Lowest emissions": lambda i: evaluations[i].nominal.emissions_kg_co2e}[choice]
        idx = min(range(len(result.plans)), key=key)
        plan, evaluation = result.plans[idx], evaluations[idx]
        st.caption(f"Fixed weights: {run_s.weights}. Normalization bounds: {run_s.normalization}. Inventory cost convention: {run_s.inventory_cost}.")
        st.dataframe([{k: v for k, v in primitive(c).items() if k != "prediction"} for c in plan.selected], hide_index=True, width="stretch")
        st.dataframe([{"Weather case": name, "Energy MJ": t.energy_mj, f"Cost {run_s.currency}": t.cost, "kg CO2e": t.emissions_kg_co2e, "Electricity kWh": t.electricity_kwh} for name, t in evaluation.cases.items()], hide_index=True)
        st.caption(f"Nominal purchase cost: {evaluation.purchase_cost:.3f}; consumed-fuel value: {evaluation.consumption_cost:.3f}. These are not added twice.")
        with st.expander("Rule checks and fuel masses"):
            st.json(primitive(evaluation.rule_results))
            st.json(primitive(evaluation.nominal.fuel_kg_by_pathway))
    else:
        st.info("No final recommendation is available for this run.")
        if result.metadata.get("proof"):
            st.json(primitive(result.metadata["proof"]))
        if result.metadata.get("error"):
            st.error(result.metadata["error"])
        if result.violations:
            st.dataframe([primitive(v) for v in result.violations], hide_index=True)
    with st.expander("Exclusions, support, provenance and search record"):
        st.json(primitive(result.metadata))
    if "zip" not in job:
        files = export_run(result, ROOT/"outputs"/"exports")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for file in files:
                z.writestr(file.name, file.read_bytes())
        job["zip"] = buffer.getvalue()
    st.download_button("Download auditable CSV / JSON / Markdown report", job["zip"], file_name=result.metadata["run_id"]+".zip", mime="application/zip")


planner, prediction, benchmarks, assumptions = st.tabs(["Fleet planner", "Prediction", "Benchmark evidence", "Data and assumptions"])
with planner:
    st.dataframe([primitive(r) for r in s.services], hide_index=True, width="stretch")
    active = st.session_state.get("job") and not st.session_state["job"]["future"].done()
    a, b = st.columns(2)
    if a.button("Run greedy baseline", disabled=bool(active), width="stretch"):
        start_run("greedy")
    if b.button("Run selected method", disabled=bool(active), type="primary", width="stretch"):
        start_run(method)
    run_panel()
with prediction:
    st.caption("Known-vessel future and unseen-vessel evaluations remain separate. Unsupported operating points have no numeric ML estimate.")
    if st.button("Evaluate prediction baselines"):
        from greenfleet.splits import make_splits
        from greenfleet.predict import fit_predictor, prediction_report
        reports = []
        with st.spinner("Fitting training-only models and evaluating held-out partitions..."):
            for protocol in ("future", "unseen_vessel"):
                for name in ("engineering", "direct", "residual", "random_tuned", "qie_tuned"):
                    try:
                        p = fit_predictor(data, make_splits(data, protocol, int(seed)), name, 4, int(seed))
                        reports.append({"method": name, "fit_count": p.fit_count, **prediction_report(p, data)})
                    except ValueError as exc:
                        st.warning(f"{protocol}/{name}: {exc}")
        st.session_state["prediction_reports"] = reports
    if "prediction_reports" in st.session_state:
        st.json(st.session_state["prediction_reports"])
with benchmarks:
    files = sorted((ROOT/"outputs"/"benchmarks").glob("benchmark-*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        path = st.selectbox("Saved benchmark", files, format_func=lambda p: p.parent.name)
        report = json.loads(path.read_text(encoding="utf-8"))
        st.dataframe(report["summary"], hide_index=True)
        st.json({k: report[k] for k in ("seeds", "candidate_hash", "candidate_limit_reached", "paired_intervals", "limitations")})
        st.download_button("Download benchmark manifest", path.read_bytes(), file_name="benchmark-manifest.json")
    else:
        st.info("No benchmark evidence saved yet. Run the paired synthetic protocol from the command line.")
        st.code(".venv\\Scripts\\python -m greenfleet.cli benchmark --config configs/demo.yaml")
with assumptions:
    st.json(primitive(data.manifest))
    st.write(f"Excluded observations: {len(data.quality_report)}")
    st.json(primitive(data.quality_report))
    st.markdown((ROOT/"docs"/"decision-log.md").read_text(encoding="utf-8"))
    st.json({"pathways": primitive(s.pathways), "engine_fuels": primitive(s.engine_fuels), "weather": primitive(s.weather_cases), "rules": primitive(s.rules)})
