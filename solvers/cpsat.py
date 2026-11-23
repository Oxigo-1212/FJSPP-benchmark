"""OR-Tools CP-SAT: one optional interval per (operation, eligible machine), no-overlap per machine."""

import time

from ortools.sat.python import cp_model

from problem import Instance, eligible, operations

from .common import FEASIBLE, INFEASIBLE, OPTIMAL, TIMEOUT, UNKNOWN, Result, lower_bound, upper_bound


def solve(inst: Instance, time_limit: float | None = None, workers: int = 0, log: bool = False) -> Result:
    t0 = time.perf_counter()
    m = cp_model.CpModel()
    H = upper_bound(inst)
    ops = operations(inst)

    start = {op: m.new_int_var(0, H, f"S{op}") for op in ops}
    end = {op: m.new_int_var(0, H, f"C{op}") for op in ops}
    x: dict[tuple, cp_model.IntVar] = {}
    per_machine: dict[int, list] = {}
    for op in ops:
        for k, p in eligible(inst.jobs[op[0]], op[1]):
            x[op, k] = m.new_bool_var(f"X{op}{k}")
            # C2 + C5: the interval is present only on the chosen machine
            per_machine.setdefault(k, []).append(
                m.new_optional_interval_var(start[op], p, end[op], x[op, k], f"I{op}{k}"))
        m.add_exactly_one(x[op, k] for k, _ in eligible(inst.jobs[op[0]], op[1]))  # C1

    for i, job in enumerate(inst.jobs):  # C4
        for j in range(len(job.times) - 1):
            m.add(end[i, j] <= start[i, j + 1])
    for intervals in per_machine.values():  # C5
        m.add_no_overlap(intervals)

    cmax = m.new_int_var(lower_bound(inst), H, "Cmax")  # C6
    m.add_max_equality(cmax, [end[i, len(job.times) - 1] for i, job in enumerate(inst.jobs)])
    m.minimize(cmax)
    build = time.perf_counter() - t0

    solver = cp_model.CpSolver()
    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit
    if workers:
        solver.parameters.num_workers = workers
    solver.parameters.log_search_progress = log
    t0 = time.perf_counter()
    code = solver.solve(m)
    solve_time = time.perf_counter() - t0

    has_sol = code in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    schedule = None
    if has_sol:
        schedule = {}
        for op in ops:
            k, p = next((k, p) for k, p in eligible(inst.jobs[op[0]], op[1]) if solver.value(x[op, k]))
            s = solver.value(start[op])
            schedule[op] = (k, s, s + p)
    status = {cp_model.OPTIMAL: OPTIMAL, cp_model.FEASIBLE: FEASIBLE,
              cp_model.INFEASIBLE: INFEASIBLE}.get(code, TIMEOUT if time_limit else UNKNOWN)
    proto = m.proto
    return Result(
        solver="cpsat",
        status=status,
        makespan=int(solver.objective_value) if has_sol else None,
        lower_bound=int(solver.best_objective_bound) if has_sol or code == cp_model.UNKNOWN else None,
        schedule=schedule,
        build_time=build,
        solve_time=solve_time,
        n_vars=len(proto.variables),
        n_constraints=len(proto.constraints),
    )
