"""Thin Streamlit presentation; domain calculations live in greenfleet."""
from pathlib import Path
import json
import streamlit as st
from greenfleet.contracts import primitive
from greenfleet.ingest import demo_dataset, load_bundle_dict, validate_scenario, BundleError

st.set_page_config(page_title="GreenFleet", page_icon="🚢", layout="wide")
st.title("GreenFleet")
st.caption("Auditable fleet planning • Energy, cost and lifecycle emissions")
data = demo_dataset()
upload = st.sidebar.file_uploader("Upload a validated JSON bundle", type=["json"])
if upload:
    try:
        data = load_bundle_dict(json.loads(upload.getvalue()))
    except (BundleError, ValueError, TypeError, KeyError) as exc:
        st.error(f"Bundle validation failed: {exc}")
        st.stop()
scenario = data.scenario
if scenario.synthetic:
    st.warning("SYNTHETIC DEMONSTRATION — no real-world accuracy, savings or certification claims.")
violations = validate_scenario(scenario)
if violations:
    st.error("Scenario validation failed")
    st.dataframe([primitive(x) for x in violations])
    st.stop()
st.success("Scenario valid under the configured schema.")
st.info("Operational feasibility and regulatory compliance are evaluated separately. Regulatory coverage is unverified unless a scoped rule bundle establishes it.")
cols = st.columns(3)
cols[0].metric("Vessels", len(scenario.vessels))
cols[1].metric("Service requests", len(scenario.services))
cols[2].metric("Observations", len(data.observations))
st.subheader("Service requests")
st.dataframe([primitive(r) for r in scenario.services], hide_index=True)
with st.expander("Validation, provenance and assumptions"):
    st.json(primitive(data.manifest))
    st.write(f"Excluded observations: {len(data.quality_report)}")
    st.json(primitive(data.quality_report))

with st.expander("Prediction baselines — separate held-out protocols"):
    if st.button("Evaluate prediction baselines"):
        from greenfleet.splits import make_splits
        from greenfleet.predict import fit_predictor, prediction_report
        reports=[]
        for protocol in ("future", "unseen_vessel"):
            for method in ("engineering", "direct", "residual"):
                try:
                    model=fit_predictor(data,make_splits(data,protocol,17),method,1,17)
                    reports.append({"method":method,**prediction_report(model,data)})
                except ValueError as exc:
                    st.warning(f"{protocol}/{method}: {exc}")
        st.json(reports)
