"""Shared pieces for every solver: result record, bounds (8.1) and validator (8.3).

A schedule maps each operation (job, op) to (machine, start, end), machines 0-based,
the same shape `encoder.decode` returns.
"""

import math
from dataclasses import dataclass, field

from problem import Instance, eligible, operations

Op = tuple[int, int]
Schedule = dict[Op, tuple[int, int, int]]

OPTIMAL, FEASIBLE, INFEASIBLE, TIMEOUT, UNKNOWN = "optimal", "feasible", "infeasible", "timeout", "unknown"


@dataclass
class Result:
    """What section 9 asks to record for every run."""

    solver: str
    status: str  # OPTIMAL | FEASIBLE (limit hit with a solution) | INFEASIBLE | TIMEOUT (no solution) | UNKNOWN
    makespan: int | None
    lower_bound: int | None
    schedule: Schedule | None
    build_time: float  # model / CNF generation, seconds
    solve_time: float  # time inside the solver, seconds
    n_vars: int
    n_constraints: int  # clauses for SAT
    extra: dict = field(default_factory=dict)

    @property
    def total_time(self) -> float:
        return self.build_time + self.solve_time


def min_times(inst: Instance) -> list[list[int]]:
    """min_k p_ijk for every operation."""
    return [[min(t for t in row if t is not None) for row in job.times] for job in inst.jobs]


def lower_bound(inst: Instance) -> int:
    """(20)-(21): max of the longest job and the machine-load bound."""
    mins = min_times(inst)
    lb_job = max((sum(job) for job in mins), default=0)
    lb_load = math.ceil(sum(map(sum, mins)) / inst.n_machines)
    return max(lb_job, lb_load)


def upper_bound(inst: Instance) -> int:
    """(22): every operation on its fastest machine, run one after another."""
    return sum(map(sum, min_times(inst)))


def sequential_schedule(inst: Instance) -> Schedule:
    """The schedule behind (22): fastest machine per operation, all jobs in sequence."""
    schedule, t = {}, 0
    for op in operations(inst):
        k, p = min(eligible(inst.jobs[op[0]], op[1]), key=lambda kp: kp[1])
        schedule[op] = (k, t, t + p)
        t += p
    return schedule


def makespan(schedule: Schedule) -> int:
    return max((end for _, _, end in schedule.values()), default=0)


def validate(inst: Instance, schedule: Schedule, H: int | None = None) -> list[str]:
    """Section 8.3 checks. Returns the list of violations (empty when the schedule is valid)."""
    errors = []
    ops = operations(inst)
    if set(schedule) != set(ops):
        missing, extra = set(ops) - set(schedule), set(schedule) - set(ops)
        errors.append(f"operations missing {sorted(missing)} / unknown {sorted(extra)}")
        return errors

    # 1, 2: eligible machine, non-negative start, duration matches the chosen machine
    for op in ops:
        k, s, c = schedule[op]
        times = dict(eligible(inst.jobs[op[0]], op[1]))
        if k not in times:
            errors.append(f"O{op} on machine {k}, not in its eligible set {sorted(times)}")
            continue
        if s < 0:
            errors.append(f"O{op} starts at {s} < 0")
        if c - s != times[k]:
            errors.append(f"O{op} on machine {k}: C-S = {c - s} != p = {times[k]}")

    # 3: job precedence
    for i, job in enumerate(inst.jobs):
        for j in range(len(job.times) - 1):
            if schedule[(i, j)][2] > schedule[(i, j + 1)][1]:
                errors.append(f"O{(i, j)} ends at {schedule[(i, j)][2]} after O{(i, j + 1)} starts at {schedule[(i, j + 1)][1]}")

    # 4: no overlap on a machine
    by_machine: dict[int, list[tuple[int, int, Op]]] = {}
    for op, (k, s, c) in schedule.items():
        by_machine.setdefault(k, []).append((s, c, op))
    for k, items in by_machine.items():
        items.sort()
        for (s1, c1, a), (s2, _, b) in zip(items, items[1:]):
            if s2 < c1:
                errors.append(f"machine {k}: O{b} starts at {s2} before O{a} ends at {c1}")

    # 5: makespan within the bound
    if H is not None and makespan(schedule) > H:
        errors.append(f"makespan {makespan(schedule)} > H = {H}")
    return errors


def same_job_pairs_skipped(a: Op, b: Op) -> bool:
    """Operations of one job never overlap: precedence (4) already orders them.

    The MIP and CP models skip such pairs in C5; the SAT encoder keeps them as written.
    """
    return a[0] == b[0]
