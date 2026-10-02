from dataclasses import replace
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import json


def test_unknown_compliance_separate_from_completed_run(tmp_path):
    from greenfleet.runs import execute_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig
    r=execute_run(demo_dataset().scenario,RunConfig(),tmp_path)
    assert r.status=="completed"
    assert r.compliance_status=="unknown"
    assert r.plans


def test_cancelled_run_has_no_final_recommendation(tmp_path):
    from greenfleet.runs import execute_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig
    event=Event();event.set()
    r=execute_run(demo_dataset().scenario,RunConfig(),tmp_path,cancel=event.is_set)
    assert r.status=="cancelled"
    assert not r.plans
    saved=json.loads((tmp_path/r.metadata["run_id"]/"result.json").read_text())
    assert saved["plans"]==[]


def test_duplicate_clicks_do_not_overwrite_artifacts(tmp_path):
    from greenfleet.runs import execute_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(execute_run,demo_dataset().scenario,RunConfig(),tmp_path)
        b=pool.submit(execute_run,demo_dataset().scenario,RunConfig(),tmp_path)
        first,second=a.result(),b.result()
    assert first.metadata["run_id"]!=second.metadata["run_id"]
    assert len(list(tmp_path.glob("*/result.json")))==2


def test_mid_search_cancel_discards_archive(tmp_path):
    from greenfleet.runs import execute_run
    from greenfleet.ingest import demo_dataset
    from greenfleet.contracts import RunConfig,SearchConfig
    event=Event()
    def progress(done,total):
        if done>=4:
            event.set()
    r=execute_run(demo_dataset().scenario,RunConfig(method="qie",search=SearchConfig(budget=100)),tmp_path,cancel=event.is_set,progress=progress)
    assert r.status=="cancelled"
    assert not r.plans
