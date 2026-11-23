"""Shared instances for the tests."""

import random
from pathlib import Path

import pytest

from helper import load_fjs
from problem import make_instance

DATA = Path(__file__).resolve().parent.parent / "data" / "fjsplib"
N = None


def pdf_example():
    """Section 4 of the write-up: 2 jobs x 2 machines, optimum 6."""
    return make_instance([[[3, 4], [N, 2]], [[2, 3], [3, N]]])


def random_instance(n_jobs: int, n_machines: int, n_ops: int, seed: int):
    rnd = random.Random(seed)
    jobs = []
    for _ in range(n_jobs):
        ops = []
        for _ in range(n_ops):
            row = [rnd.randint(1, 9) if rnd.random() < 0.5 else None for _ in range(n_machines)]
            if all(t is None for t in row):
                row[rnd.randrange(n_machines)] = rnd.randint(1, 9)
            ops.append(row)
        jobs.append(ops)
    return make_instance(jobs)


# name -> (loader, proven optimal makespan)
INSTANCES = {
    "pdf": (pdf_example, 6),
    "rand4x3x3": (lambda: random_instance(4, 3, 3, seed=1), 25),
    "mk01": (lambda: load_fjs(DATA / "brandimarte" / "Mk01.fjs"), 40),
}


@pytest.fixture(params=sorted(INSTANCES))
def known(request):
    """(name, instance, optimal makespan) for each instance with a proven optimum."""
    load, opt = INSTANCES[request.param]
    return request.param, load(), opt
