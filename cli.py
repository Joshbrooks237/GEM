#!/usr/bin/env python3
"""Pegmatite command line."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.loop import ExperimentConfig, resume_experiment, run_experiment
from selection.fitness import FitnessConfig
from ledger.report import compare_runs, write_report
from ledger.db import Ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Pegmatite: a scarcity experiment for emergent coding conventions",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "runs",
        help="directory that holds run folders (default: runs/)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="start a new run")
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--generations", type=int, default=50)
    run.add_argument("--agents", type=int, default=3)
    run.add_argument("--provider", choices=("scripted", "openai"), default="scripted")
    run.add_argument("--runner", choices=("local", "docker"), default=None)
    run.add_argument("--shock-generation", type=int, default=25)
    run.add_argument("--ecology", choices=("exp2", "exp3"), default="exp2")
    run.add_argument("--heldout-every", type=int, default=10)
    run.add_argument("--base-pass", type=float, default=None)
    run.add_argument("--resource-weight", type=float, default=None)
    run.add_argument("--reuse-weight", type=float, default=None)
    run.add_argument("--explainability-weight", type=float, default=None)
    run.add_argument("--resource-cap", type=float, default=None)

    resume = sub.add_parser("resume", help="continue an unfinished run")
    resume.add_argument("run_id")
    resume.add_argument("--generations", type=int, default=None)

    report = sub.add_parser("report", help="write report.md for a run")
    report.add_argument("run_id")

    compare = sub.add_parser("compare", help="compare two runs")
    compare.add_argument("run_a")
    compare.add_argument("run_b")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            runner = args.runner
            if runner is None:
                runner = "docker" if args.provider == "openai" else "local"
            overrides = {}
            if args.base_pass is not None:
                overrides["base_pass"] = args.base_pass
            if args.resource_weight is not None:
                overrides["resource_weight"] = args.resource_weight
            if args.reuse_weight is not None:
                overrides["reuse_weight"] = args.reuse_weight
            if args.explainability_weight is not None:
                overrides["explainability_weight"] = args.explainability_weight
            if args.resource_cap is not None:
                overrides["resource_cap"] = args.resource_cap
            model = ""
            if args.provider == "openai":
                model = os.environ.get("PEGMATITE_MODEL", "gpt-4o-mini")
            config = ExperimentConfig(
                seed=args.seed,
                generations=args.generations,
                n_agents=args.agents,
                provider=args.provider,
                runner=runner,
                shock_generation=args.shock_generation,
                heldout_every=args.heldout_every,
                ecology=args.ecology,
                model=model,
                fitness=FitnessConfig(**overrides) if overrides else FitnessConfig(),
            )
            run_id = run_experiment(config, args.run_dir)
            print(run_id)
            return 0
        if args.cmd == "resume":
            resume_experiment(args.run_id, args.run_dir, generations=args.generations)
            print(args.run_id)
            return 0
        if args.cmd == "report":
            folder = args.run_dir / args.run_id
            ledger = Ledger(folder / "ledger.sqlite")
            try:
                if ledger.get_run(args.run_id) is None:
                    raise FileNotFoundError(args.run_id)
                path = write_report(ledger, folder)
            finally:
                ledger.close()
            print(path)
            return 0
        if args.cmd == "compare":
            print(compare_runs(args.run_dir, args.run_a, args.run_b))
            return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
