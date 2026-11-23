"""CPLEX CP Optimizer (docplex.cp): one interval per operation, optional alternatives per machine.

Needs the `cpoptimizer` executable: found on PATH, or else next to the running Python
(the `cplex` pip package installs it into the environment's bin/), so no activation is needed.
"""

import shutil
import sys
import time
from pathlib import Path

from docplex.cp.model import CpoModel, alternative, end_of, interval_var, max as cp_max, minimize, no_overlap, start_of

from problem import Instance, eligible, operations

from .common import FEASIBLE, INFEASIBLE, OPTIMAL, TIMEOUT, UNKNOWN, Result, lower_bound, upper_bound


def solve(inst: Instance, time_limit: float | None = None, workers: int = 0, log: bool = False) -> Result:
    t0 = time.perf_counter()
    m = CpoModel("fjssp")
    H = upper_bound(inst)
    ops = operations(inst)
    elig = {op: dict(eligible(inst.jobs[op[0]], op[1])) for op in ops}

    task = {op: interval_var(start=(0, H), end=(0, H), name=f"O{op[0]}_{op[1]}") for op in ops}
    mode = {(op, k): interval_var(size=p, optional=True, name=f"O{op[0]}_{op[1]}_M{k}")
            for op in ops for k, p in elig[op].items()}
    per_machine: dict[int, list] = {}
    for op in ops:
        m.add(alternative(task[op], [mode[op, k] for k in elig[op]]))  # C1 + C2
        for k in elig[op]:
            per_machine.setdefault(k, []).append(mode[op, k])
    for i, job in enumerate(inst.jobs):  # C4
        for j in range(len(job.times) - 1):
            m.add(end_of(task[i, j]) <= start_of(task[i, j + 1]))
    for intervals in per_machine.values():  # C5
        m.add(no_overlap(intervals))
    cmax = cp_max([end_of(task[i, len(job.times) - 1]) for i, job in enumerate(inst.jobs)])  # C6
    m.add(cmax >= lower_bound(inst))
    m.add(minimize(cmax))  # (9)
    build = time.perf_counter() - t0

    params = {"LogVerbosity": "Normal" if log else "Quiet"}
    if exe := cpoptimizer_path():
        params["execfile"] = exe
    if time_limit is not None:
        params["TimeLimit"] = time_limit
    if workers:
        params["Workers"] = workers
    t0 = time.perf_counter()
    sol = m.solve(**params)
    solve_time = time.perf_counter() - t0

    st = sol.get_solve_status()
    has_sol = bool(sol.is_solution())
    schedule = None
    if has_sol:
        schedule = {}
        for op in ops:
            k = next(k for k in elig[op] if sol.get_var_solution(mode[op, k]).is_present())
            s = sol.get_var_solution(task[op]).get_start()
            schedule[op] = (k, s, s + elig[op][k])
    status = {"Optimal": OPTIMAL, "Infeasible": INFEASIBLE}.get(
        st, FEASIBLE if has_sol else TIMEOUT if sol.get_stop_cause() == "SearchStoppedByLimit" else UNKNOWN)
    infos = sol.get_solver_infos()
    bounds = sol.get_objective_bounds() if has_sol else None
    return Result(
        solver="cplex-cp",
        status=status,
        makespan=int(sol.get_objective_values()[0]) if has_sol else None,
        lower_bound=int(bounds[0]) if bounds else None,
        schedule=schedule,
        build_time=build,
        solve_time=solve_time,
        n_vars=infos.get("NumberOfIntegerVariables", 0) + infos.get("NumberOfIntervalVariables", 0),
        n_constraints=infos.get("NumberOfConstraints", 0),
    )


def cpoptimizer_path() -> str | None:
    """The CP Optimizer executable: PATH first, then the bin/ of the running environment."""
    if found := shutil.which("cpoptimizer"):
        return found
    local = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin") / "cpoptimizer"
    for candidate in (local, local.with_suffix(".exe")):
        if candidate.is_file():
            return str(candidate)
    return None
