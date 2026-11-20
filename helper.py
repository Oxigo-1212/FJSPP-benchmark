"""Reader for the standard .fjs benchmark file format."""

from pathlib import Path

from problem import Instance, make_job


def parse_fjs(text: str) -> Instance:
    """Parse the standard .fjs format (Brandimarte / Hurink benchmark files).

    Line 1: n_jobs n_machines [avg machines per op]
    Each job line: n_ops, then per op: k, then k pairs of (machine 1-based, time).
    """
    nums = iter(int(float(x)) for x in text.split())
    n_jobs, n_machines = next(nums), next(nums)
    lines = [l.split() for l in text.strip().splitlines()[1:] if l.strip()]
    jobs = []
    for line in lines[:n_jobs]:
        it = iter(map(int, line))
        ops = []
        for _ in range(next(it)):
            row = [None] * n_machines
            for _ in range(next(it)):
                m, t = next(it), next(it)
                row[m - 1] = t
            ops.append(row)
        jobs.append(ops)
    return Instance(tuple(make_job(j) for j in jobs), n_machines)


def load_fjs(path: str | Path) -> Instance:
    return parse_fjs(Path(path).read_text())
