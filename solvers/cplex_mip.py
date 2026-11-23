"""CPLEX MIP (docplex.mp): the same section-3 model as gurobi_mip.py, big-M = UB from (22)."""

import time
from itertools import combinations

from docplex.mp.model import Model
from docplex.util.status import JobSolveStatus

from problem import Instance, eligible, operations

from .common import (FEASIBLE, INFEASIBLE, OPTIMAL, TIMEOUT, UNKNOWN, Result, lower_bound,
                     same_job_pairs_skipped, upper_bound)
from .gurobi_mip import _ceil_bound

# CPLEX status codes: 3/103 infeasible, 4/119 infeasible or unbounded (LP / MIP)
CPLEX_INFEASIBLE = {3, 4, 103, 119}


def solve(inst: Instance, time_limit: float | None = None, threads: int = 0, log: bool = False) -> Result:
    t0 = time.perf_counter()
    m = Model("fjssp")
    M = upper_bound(inst)
    ops = operations(inst)
    elig = {op: dict(eligible(inst.jobs[op[0]], op[1])) for op in ops}

    X = {(op, k): m.binary_var(f"X{op}{k}") for op in ops for k in elig[op]}
    S = {op: m.continuous_var(0, M, f"S{op}") for op in ops}  # C3
    C = {op: m.continuous_var(0, M, f"C{op}") for op in ops}
    cmax = m.continuous_var(lower_bound(inst), M, "Cmax")

    for op in ops:
        m.add_constraint(m.sum(X[op, k] for k in elig[op]) == 1)  # C1 (1)
        m.add_constraint(C[op] == S[op] + m.sum(p * X[op, k] for k, p in elig[op].items()))  # C2 (2)
    for i, job in enumerate(inst.jobs):
        for j in range(len(job.times) - 1):
            m.add_constraint(C[i, j] <= S[i, j + 1])  # C4 (4)
        m.add_constraint(C[i, len(job.times) - 1] <= cmax)  # C6 (8)

    for a, b in combinations(ops, 2):  # C5 (5)-(7)
        if same_job_pairs_skipped(a, b):
            continue
        for k in elig[a].keys() & elig[b].keys():
            yab, yba = m.binary_var(f"Y{a}{b}{k}"), m.binary_var(f"Y{b}{a}{k}")
            for y in (yab, yba):
                m.add_constraint(y <= X[a, k])
                m.add_constraint(y <= X[b, k])
            m.add_constraint(yab + yba >= X[a, k] + X[b, k] - 1)
            m.add_constraint(C[a] <= S[b] + M * (1 - yab))
            m.add_constraint(C[b] <= S[a] + M * (1 - yba))

    m.minimize(cmax)  # (9)
    if time_limit is not None:
        m.parameters.timelimit = time_limit
    if threads:
        m.parameters.threads = threads
    build = time.perf_counter() - t0

    t0 = time.perf_counter()
    sol = m.solve(log_output=log)
    solve_time = time.perf_counter() - t0

    details = m.solve_details
    schedule = None
    if sol is not None:
        schedule = {}
        for op in ops:
            k = max(elig[op], key=lambda k: sol.get_value(X[op, k]))
            s = round(sol.get_value(S[op]))
            schedule[op] = (k, s, s + elig[op][k])
    if sol is not None:
        status = OPTIMAL if sol.solve_status == JobSolveStatus.OPTIMAL_SOLUTION else FEASIBLE
    elif details.status_code in CPLEX_INFEASIBLE:
        status = INFEASIBLE
    else:
        status = TIMEOUT if details.has_hit_limit() else UNKNOWN

    result = Result(
        solver="cplex-mip",
        status=status,
        makespan=round(sol.objective_value) if sol is not None else None,
        lower_bound=_ceil_bound(details.best_bound) if status != INFEASIBLE and details.best_bound is not None else None,
        schedule=schedule,
        build_time=build,
        solve_time=solve_time,
        n_vars=m.number_of_variables,
        n_constraints=m.number_of_constraints,
        extra={"mip_gap": details.mip_relative_gap if sol is not None else None},
    )
    m.end()
    return result
