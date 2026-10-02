# GreenFleet

A local, auditable fleet-planning research prototype implementing the supplied
GreenFleet plan. Included data and physical coefficients are **synthetic**.
Do not interpret demonstration metrics as real-world accuracy or savings.

## Windows setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\python -m pip install -e . --no-deps
.venv\Scripts\python -m streamlit run app.py
```

Use the virtual environment's Python directly; activation is optional.
Tests: `.venv\Scripts\python -m pytest -q`.
See `docs/user-guide.md` for CLI, bundle upload, exports and benchmark instructions.
Pending domain decisions are recorded in `docs/decision-log.md`.
