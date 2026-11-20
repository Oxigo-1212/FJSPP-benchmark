"""FJSS problem space: jobs, processing times and instance construction.

A job is a 2D processing-time table:
    times[o][m] = processing time of operation o of this job on machine m,
                  or None when machine m cannot run operation o.
Start times are not stored. The encoder or decoder infers them from these
processing times.
"""

from dataclasses import dataclass

Times = tuple[tuple[int | None, ...], ...]


@dataclass(frozen=True)
class Job:
    times: Times  # rows = operations (in precedence order), columns = machines

    def __post_init__(self):
        widths = {len(row) for row in self.times} # The matrix is forced to be square
        if len(widths) > 1:
            raise ValueError(f"operations have different machine counts: {widths}")
        for o, row in enumerate(self.times):
            if all(t is None for t in row):
                raise ValueError(f"operation {o} has no eligible machine")
            if any(t is not None and t < 0 for t in row):
                raise ValueError(f"operation {o} has a negative processing time")


@dataclass(frozen=True)
class Instance:
    jobs: tuple[Job, ...]
    n_machines: int

    def __post_init__(self):
        for i, job in enumerate(self.jobs):
            if any(len(row) != self.n_machines for row in job.times):
                raise ValueError(f"job {i} does not have {self.n_machines} machine columns")


def make_job(times: list[list[int | None]]) -> Job:
    return Job(tuple(tuple(row) for row in times))

def make_instance(jobs: list[list[list[int | None]]]) -> Instance:
    built = tuple(make_job(t) for t in jobs)
    return Instance(built, len(built[0].times[0]))


def eligible(job: Job, op: int) -> list[tuple[int, int]]:
    """(machine, processing time) pairs that can run operation `op` of `job`."""
    return [(m, t) for m, t in enumerate(job.times[op]) if t is not None]

def operations(inst: Instance) -> list[tuple[int, int]]:
    """All (job, operation) pairs, in job then precedence order."""
    return [(j, o) for j, job in enumerate(inst.jobs) for o in range(len(job.times))]


def horizon(inst: Instance) -> int:
    """Makespan upper bound: every operation run one after another on its slowest machine."""
    return sum(max(t for t in row if t is not None) for job in inst.jobs for row in job.times)
