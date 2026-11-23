"""FJSSP command line.

    python cli.py solve data/fjsplib/brandimarte/Mk01.fjs -s cpsat -t 30
    python cli.py bench data/fjsplib/brandimarte -t 20 -o results.csv
    python cli.py info  data/fjsplib/hurink/edata

Run `python cli.py COMMAND -h` for the options of each command.
"""

import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

from helper import load_fjs
from problem import eligible, operations
from solvers import SOLVERS, get_solver, lower_bound, upper_bound, validate

LICENSE_ERRORS = ("size-limited license", "Promotional version", "Problem size limits")
BENCH_FIELDS = ["instance", "jobs", "machines", "ops", "LB0", "UB0", "solver", "status", "makespan", "lower_bound",
                "build_time", "solve_time", "total_time", "n_vars", "n_constraints", "valid", "note"]


# --- helpers -----------------------------------------------------------------------

def instance_files(paths: list[str]) -> list[Path]:
    """.fjs files from a mix of files and folders (folders are searched recursively)."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(p.rglob("*.fjs"))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"not found: {p}")
    if not files:
        sys.exit("no .fjs files found")
    return files


def time_limit(text: str) -> float | None:
    """-t value: seconds, or 0 / 'none' for no limit."""
    if text.lower() in ("0", "none", "inf"):
        return None
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("time limit must be >= 0")
    return value or None


def sat_options(args, backend: str | None = None) -> dict:
    return dict(backend=backend or args.backend, search=args.search, amo=args.amo, incremental=not args.repeated)


def sat_clause_estimate(inst) -> float:
    """Rough clause count of the encoding at H = UB, dominated by S7 (2 per shared machine per t)."""
    H = upper_bound(inst)
    ms = {op: {k for k, _ in eligible(inst.jobs[op[0]], op[1])} for op in operations(inst)}
    pairs = sum(len(ms[a] & ms[b]) for a, b in combinations(ms, 2))
    return 2 * pairs * (H + 1) + (H + 1) * sum(2 + 2 * len(m) for m in ms.values())


def error_note(e: Exception) -> str:
    text = str(e).strip()
    if any(s in text for s in LICENSE_ERRORS):
        return "license size limit"
    return (text.splitlines()[-1] if text else type(e).__name__)[:100]


def add_sat_args(p: argparse.ArgumentParser, many_backends: bool) -> None:
    g = p.add_argument_group("SAT options")
    if many_backends:
        g.add_argument("--sat-backends", nargs="+", default=["glucose4", "cadical195"], metavar="NAME",
                       help="SAT backends to run (default: glucose4 cadical195)")
    else:
        g.add_argument("--backend", default="cadical195",
                       help="SAT backend: cadical195, glucose4, cryptominisat, minisat22, ... (default cadical195)")
    g.add_argument("--search", choices=["linear", "binary"], default="binary", help="makespan search (default binary)")
    g.add_argument("--amo", choices=["binary", "seqcounter", "commander", "product"], default="seqcounter",
                   help="at-most-one encoding (default seqcounter)")
    g.add_argument("--repeated", action="store_true", help="rebuild the CNF per bound instead of incremental SAT")


# --- solve ---------------------------------------------------------------------------

def cmd_solve(args) -> None:
    path = instance_files([args.instance])[0]
    inst = load_fjs(path)
    opts = sat_options(args) if args.solver == "sat" else {}
    try:
        r = get_solver(args.solver)(inst, time_limit=args.time_limit, **opts)
    except Exception as e:
        sys.exit(f"{args.solver} failed: {error_note(e)}")
    errors = validate(inst, r.schedule) if r.schedule else []

    if args.json:
        out = dict(instance=path.stem, solver=r.solver, status=r.status, makespan=r.makespan,
                   lower_bound=r.lower_bound, build_time=r.build_time, solve_time=r.solve_time,
                   total_time=r.total_time, n_vars=r.n_vars, n_constraints=r.n_constraints,
                   valid=not errors if r.schedule else None,
                   schedule=[dict(job=i + 1, op=j + 1, machine=k + 1, start=s, end=c)
                             for (i, j), (k, s, c) in sorted(r.schedule.items())] if r.schedule else None)
        print(json.dumps(out, indent=2))
        return

    print(f"instance   {path.stem}  ({len(inst.jobs)} jobs, {inst.n_machines} machines, {len(operations(inst))} ops)")
    print(f"solver     {r.solver}")
    print(f"status     {r.status}")
    print(f"makespan   {r.makespan}   (lower bound {r.lower_bound})")
    print(f"time       build {r.build_time:.2f}s + solve {r.solve_time:.2f}s = {r.total_time:.2f}s")
    print(f"size       {r.n_vars} variables, {r.n_constraints} {'clauses' if args.solver == 'sat' else 'constraints'}")
    if r.schedule:
        print(f"valid      {'yes' if not errors else 'NO'}")
        for e in errors:
            print(f"  ! {e}")
    if r.schedule and not args.quiet:
        print("\nschedule (jobs, operations and machines numbered from 1; O<job>.<op> [start, end))")
        by_machine: dict[int, list] = {}
        for (i, j), (k, s, c) in r.schedule.items():
            by_machine.setdefault(k, []).append((s, c, i, j))
        width = len(str(inst.n_machines))
        for k in range(inst.n_machines):
            items = sorted(by_machine.get(k, []))
            line = "  ".join(f"O{i + 1}.{j + 1}[{s},{c})" for s, c, i, j in items) or "(idle)"
            print(f"  M{k + 1:<{width}}  {line}")
    if errors:
        sys.exit(1)


# --- bench ---------------------------------------------------------------------------

def cmd_bench(args) -> None:
    runs = []
    for name in args.solvers:
        if name == "sat":
            runs += [(f"sat[{b}]", "sat", sat_options(args, b)) for b in args.sat_backends]
        else:
            runs.append((name, name, {}))

    files = instance_files(args.instances)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, BENCH_FIELDS)
        w.writeheader()
        for path in files:
            inst = load_fjs(path)
            base = dict(instance=path.stem, jobs=len(inst.jobs), machines=inst.n_machines,
                        ops=len(operations(inst)), LB0=lower_bound(inst), UB0=upper_bound(inst))
            est = sat_clause_estimate(inst) if "sat" in args.solvers else 0
            for label, name, opts in runs:
                row = dict(base, solver=label)
                if name == "sat" and est > args.max_sat_clauses:
                    row.update(status="skipped", note=f"~{est / 1e6:.0f}M clauses")
                else:
                    try:
                        r = get_solver(name)(inst, time_limit=args.time_limit, **opts)
                        row.update(status=r.status, makespan=r.makespan, lower_bound=r.lower_bound,
                                   build_time=f"{r.build_time:.2f}", solve_time=f"{r.solve_time:.2f}",
                                   total_time=f"{r.total_time:.2f}", n_vars=r.n_vars, n_constraints=r.n_constraints,
                                   valid=(not validate(inst, r.schedule)) if r.schedule else "")
                    except Exception as e:
                        row.update(status="error", note=error_note(e))
                w.writerow(row)
                f.flush()
                print(f"{row['instance']:10} {label:18} {row['status']:9} makespan={row.get('makespan', '-')!s:6} "
                      f"lb={row.get('lower_bound', '-')!s:6} t={row.get('total_time', '-')!s:7} "
                      f"valid={row.get('valid', '-')} {row.get('note', '')}", flush=True)
    print(f"wrote {args.out}")


# --- info ----------------------------------------------------------------------------

def cmd_info(args) -> None:
    print(f"{'instance':12} {'jobs':>5} {'mach':>5} {'ops':>5} {'flex':>5} {'LB':>6} {'UB':>7}")
    for path in instance_files(args.instances):
        inst = load_fjs(path)
        ops = operations(inst)
        flex = sum(len(eligible(inst.jobs[i], j)) for i, j in ops) / len(ops)
        print(f"{path.stem:12} {len(inst.jobs):>5} {inst.n_machines:>5} {len(ops):>5} {flex:>5.2f} "
              f"{lower_bound(inst):>6} {upper_bound(inst):>7}")


# --- entry point ---------------------------------------------------------------------

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="cli.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("solve", help="solve one instance and print the schedule")
    p.add_argument("instance", help=".fjs file")
    p.add_argument("-s", "--solver", choices=list(SOLVERS), default="cpsat", help="default cpsat")
    p.add_argument("-t", "--time-limit", type=time_limit, default=60, help="seconds, 0 for no limit (default 60)")
    p.add_argument("-q", "--quiet", action="store_true", help="summary only, no schedule")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    add_sat_args(p, many_backends=False)
    p.set_defaults(func=cmd_solve)

    p = sub.add_parser("bench", help="run solvers on many instances and write a CSV")
    p.add_argument("instances", nargs="+", help=".fjs files or folders (searched recursively)")
    p.add_argument("-s", "--solvers", nargs="+", choices=list(SOLVERS), default=list(SOLVERS), help="default all")
    p.add_argument("-t", "--time-limit", type=time_limit, default=20,
                   help="seconds per run, 0 for no limit (default 20)")
    p.add_argument("-o", "--out", default="results.csv", help="CSV output (default results.csv)")
    p.add_argument("--max-sat-clauses", type=float, default=30e6, help="skip SAT above this estimated CNF size")
    add_sat_args(p, many_backends=True)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("info", help="size, flexibility and bounds of instances")
    p.add_argument("instances", nargs="+", help=".fjs files or folders")
    p.set_defaults(func=cmd_info)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
