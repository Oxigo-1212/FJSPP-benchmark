"""Gurobi MIP: the model of section 3 (C1-C6) with big-M for the implication (7).

Big-M = UB from (22). Pairs of operations of the same job are left out of C5,
since precedence (4) already keeps them apart.
"""

import time
from itertools import combinations

import gurobipy as gp
from gurobipy import GRB

from problem import Instance, eligible, operations

from .common import (FEASIBLE, INFEASIBLE, OPTIMAL, TIMEOUT, UNKNOWN, Result, lower_bound,
                     same_job_pairs_skipped, upper_bound)


def solve(inst: Instance, time_limit: float | None = None, threads: int = 0, log: bool = False) -> Result:
    t0 = time.perf_counter()
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", int(log))
    env.start()
    m = gp.Model("fjssp", env=env)
    M = upper_bound(inst)
    ops = operations(inst)
    elig = {op: dict(eligible(inst.jobs[op[0]], op[1])) for op in ops}

    X = {(op, k): m.addVar(vtype=GRB.BINARY, name=f"X{op}{k}") for op in ops for k in elig[op]}
    S = {op: m.addVar(lb=0, ub=M, name=f"S{op}") for op in ops}  # C3
    C = {op: m.addVar(lb=0, ub=M, name=f"C{op}") for op in ops}
    cmax = m.addVar(lb=lower_bound(inst), ub=M, name="Cmax")

    for op in ops:
        m.addConstr(gp.quicksum(X[op, k] for k in elig[op]) == 1)  # C1 (1)
        m.addConstr(C[op] == S[op] + gp.quicksum(p * X[op, k] for k, p in elig[op].items()))  # C2 (2)
    for i, job in enumerate(inst.jobs):
        for j in range(len(job.times) - 1):
            m.addConstr(C[i, j] <= S[i, j + 1])  # C4 (4)
        m.addConstr(C[i, len(job.times) - 1] <= cmax)  # C6 (8)

    for a, b in combinations(ops, 2):  # C5 (5)-(7)
        if same_job_pairs_skipped(a, b):
            continue
        for k in elig[a].keys() & elig[b].keys():
            yab = m.addVar(vtype=GRB.BINARY, name=f"Y{a}{b}{k}")
            yba = m.addVar(vtype=GRB.BINARY, name=f"Y{b}{a}{k}")
            for y in (yab, yba):
                m.addConstr(y <= X[a, k])
                m.addConstr(y <= X[b, k])
            m.addConstr(yab + yba >= X[a, k] + X[b, k] - 1)
            m.addConstr(C[a] <= S[b] + M * (1 - yab))
            m.addConstr(C[b] <= S[a] + M * (1 - yba))

    m.setObjective(cmax, GRB.MINIMIZE)  # (9)
    if time_limit is not None:
        m.Params.TimeLimit = time_limit
    if threads:
        m.Params.Threads = threads
    m.update()
    build = time.perf_counter() - t0

    t0 = time.perf_counter()
    m.optimize()
    solve_time = time.perf_counter() - t0

    has_sol = m.SolCount > 0
    schedule = None
    if has_sol:
        schedule = {}
        for op in ops:
            k = max(elig[op], key=lambda k: X[op, k].X)
            s = round(S[op].X)
            schedule[op] = (k, s, s + elig[op][k])
    status = {GRB.OPTIMAL: OPTIMAL, GRB.INFEASIBLE: INFEASIBLE}.get(
        m.Status, FEASIBLE if has_sol else TIMEOUT if m.Status == GRB.TIME_LIMIT else UNKNOWN)
    result = Result(
        solver="gurobi-mip",
        status=status,
        makespan=round(m.ObjVal) if has_sol else None,
        lower_bound=_ceil_bound(m.ObjBound) if m.Status != GRB.INFEASIBLE else None,
        schedule=schedule,
        build_time=build,
        solve_time=solve_time,
        n_vars=m.NumVars,
        n_constraints=m.NumConstrs,
        extra={"mip_gap": m.MIPGap if has_sol else None},
    )
    m.dispose()
    env.dispose()
    return result


def _ceil_bound(v: float) -> int:
    """Makespans are integers, so a fractional bound rounds up (with a tolerance)."""
    return int(-(-round(v * 1e6) // 10**6))
