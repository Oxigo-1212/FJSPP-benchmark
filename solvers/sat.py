"""SAT solver: encoder.py (S1-S7) driven by the search of section 8.2.

Options:
    backend      any name `solver.new_solver` accepts ("cadical195", "glucose4", "cryptominisat", ...)
    amo          at-most-one encoding for S1: "binary", "seqcounter", "commander", "product"
    search       "linear" tries H = LB, LB+1, ... and stops at the first SAT;
                 "binary" halves [LB, UB]: SAT lowers UB to the found makespan, UNSAT raises LB to H+1
    incremental  True: encode once at H = UB and bound each call with assumptions (one solver kept);
                 False: build F_H from scratch with a new solver for every H

The time limit covers the whole search: each solver call gets the time left and is
interrupted when it runs out. CNF generation itself is not interrupted, and backends
without interrupt support (CaDiCaL, Kissat) only check the limit between calls;
`extra["interruptible"]` records which case applied.
"""

import time

from encoder import bound, decode, encode
from problem import Instance
from solver import new_solver

from .common import FEASIBLE, OPTIMAL, Result, lower_bound, makespan, sequential_schedule, upper_bound


def solve(inst: Instance, time_limit: float | None = None, backend: str = "cadical195",
          amo: str = "seqcounter", search: str = "linear", incremental: bool = True) -> Result:
    if search not in ("linear", "binary"):
        raise ValueError(f"unknown search {search!r}")
    start = time.perf_counter()
    deadline = None if time_limit is None else start + time_limit

    lo, hi = lower_bound(inst), upper_bound(inst)
    best = sequential_schedule(inst)  # feasible at hi by (22)
    build_time = solve_time = 0.0
    n_vars = n_clauses = calls = 0

    with new_solver(backend) as probe:
        interruptible = probe.interruptible
    shared = None
    if incremental:
        t0 = time.perf_counter()
        enc = encode(inst, hi, amo)
        s = new_solver(backend)
        s.add_clauses(enc.clauses)
        build_time += time.perf_counter() - t0
        n_vars, n_clauses = enc.n_vars, enc.n_clauses
        shared = (enc, s)

    def remaining() -> float | None:
        return None if deadline is None else deadline - time.perf_counter()

    def check(T: int):
        """Solve F_T; return the decoded schedule, False when UNSAT, None when interrupted."""
        nonlocal build_time, solve_time, n_vars, n_clauses, calls
        calls += 1
        if shared:
            enc, s = shared
            t0 = time.perf_counter()
            sat = s.solve(bound(enc, T), time_limit=remaining())
            solve_time += time.perf_counter() - t0
            return decode(enc, s.model())[0] if sat else sat
        t0 = time.perf_counter()
        enc = encode(inst, T, amo)
        with new_solver(backend) as s:
            s.add_clauses(enc.clauses)
            build_time += time.perf_counter() - t0
            n_vars, n_clauses = max(n_vars, enc.n_vars), max(n_clauses, enc.n_clauses)
            t0 = time.perf_counter()
            sat = s.solve(time_limit=remaining())
            solve_time += time.perf_counter() - t0
            return decode(enc, s.model())[0] if sat else sat

    try:
        while lo < hi:
            if deadline is not None and time.perf_counter() >= deadline:
                break
            T = lo if search == "linear" else (lo + hi) // 2
            found = check(T)
            if found is None:  # time limit hit inside the call
                break
            if found is False:
                lo = T + 1
            else:
                best, hi = found, makespan(found)
    finally:
        if shared:
            shared[1].close()

    return Result(
        solver=f"sat[{backend},{amo},{search},{'incremental' if incremental else 'repeated'}]",
        status=OPTIMAL if lo >= hi else FEASIBLE,
        makespan=makespan(best),
        lower_bound=min(lo, hi),
        schedule=best,
        build_time=build_time,
        solve_time=solve_time,
        n_vars=n_vars,
        n_constraints=n_clauses,
        extra={"sat_calls": calls, "interruptible": interruptible},
    )
