from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
import json
from .contracts import RunConfig, SearchConfig
from .ingest import demo_dataset, load_bundle, write_demo_bundle
from .runs import execute_run
from .reporting import export_run
from .benchmarks import run_benchmarks


def main():
    parser = ArgumentParser(description="GreenFleet synthetic research demonstrator")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="execute and export a local fleet run")
    demo.add_argument("--bundle", type=Path)
    demo.add_argument("--method", choices=["greedy", "exact_tiny", "alns", "nsga2", "qie"], default="greedy")
    demo.add_argument("--predictor", default="engineering")
    demo.add_argument("--budget", type=int, default=128)
    demo.add_argument("--seed", type=int, default=17)
    demo.add_argument("--output", type=Path, default=Path("outputs/runs"))
    demo.add_argument("--case", choices=["feasible", "impossible", "missing-factor", "unknown-rules"], default="feasible")
    bench = sub.add_parser("benchmark")
    bench.add_argument("--config", type=Path, default=Path("configs/demo.yaml"))
    bench.add_argument("--output", type=Path, default=Path("outputs/benchmarks"))
    bundle = sub.add_parser("fixture")
    bundle.add_argument("--output", type=Path, default=Path("data/demo"))
    args = parser.parse_args()
    if args.command == "fixture":
        print(write_demo_bundle(args.output))
        return
    if args.command == "benchmark":
        print(run_benchmarks(args.config, args.output))
        return
    data = load_bundle(args.bundle) if args.bundle else demo_dataset()
    s = data.scenario
    if args.case == "impossible":
        s = replace(s, services=(replace(s.services[0], demand_t=max(v.capacity_t for v in s.vessels)+1),)+s.services[1:])
    elif args.case == "missing-factor":
        s = replace(s, pathways=tuple(replace(f, wtw_g_mj=None, wtt_g_mj=None, ttw_g_mj=None) for f in s.pathways))
    config = RunConfig(args.method, SearchConfig(budget=args.budget, seed=args.seed), args.predictor)
    result = execute_run(s, config, args.output, dataset=replace(data, scenario=s))
    paths = export_run(result, args.output.parent/"exports")
    print(json.dumps({"status": result.status, "compliance": result.compliance_status, "run": result.metadata["output_directory"], "export": str(paths[0].parent)}, indent=2))
    if result.status == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
