"""Every solver must find the proven optimum and return a schedule that passes the validator.

A solver is skipped (not failed) when its package, the cpoptimizer binary or a large
enough license is missing.
"""

import importlib.util

import pytest

from solvers import get_solver, validate
from solvers.common import OPTIMAL

from .conftest import INSTANCES

PACKAGE = {"cpsat": "ortools", "gurobi-mip": "gurobipy", "cplex-mip": "docplex", "cplex-cp": "docplex", "sat": "pysat"}

SAT_CONFIGS = [
    dict(backend=b, search=s, incremental=inc, amo="seqcounter")
    for b in ("cadical195", "glucose4", "cryptominisat")
    for s in ("linear", "binary")
    for inc in (True, False)
] + [dict(backend="cadical195", search="linear", incremental=True, amo=a) for a in ("binary", "commander", "product")]

CASES = [pytest.param(n, {}, id=n) for n in ("cpsat", "gurobi-mip", "cplex-mip", "cplex-cp")] + [
    pytest.param("sat", c, id="sat-{backend}-{search}-{amo}-{}".format("inc" if c["incremental"] else "rep", **c))
    for c in SAT_CONFIGS
]

LICENSE_ERRORS = ("size-limited license", "Promotional version", "Problem size limits")


def run(name, inst, **opts):
    if importlib.util.find_spec(PACKAGE[name]) is None:
        pytest.skip(f"{PACKAGE[name]} not installed")
    if name == "cplex-cp":
        from solvers.cplex_cp import cpoptimizer_path
        if cpoptimizer_path() is None:
            pytest.skip("cpoptimizer executable not found")
    try:
        return get_solver(name)(inst, **opts)
    except Exception as e:
        if any(s in str(e) for s in LICENSE_ERRORS):
            pytest.skip(f"{name}: model exceeds the installed license")
        raise


@pytest.mark.parametrize("name, opts", CASES)
def test_finds_optimum(name, opts, known):
    _, inst, opt = known
    r = run(name, inst, time_limit=60, **opts)
    assert r.status == OPTIMAL
    assert r.makespan == opt
    assert r.lower_bound == opt
    assert validate(inst, r.schedule, H=opt) == []


def test_sat_time_limit_interrupts_a_call():
    """Mk02 does not finish in 2 s; an interruptible backend must stop near the limit."""
    from helper import load_fjs
    from .conftest import DATA

    inst = load_fjs(DATA / "brandimarte" / "Mk02.fjs")
    r = run("sat", inst, time_limit=2, backend="glucose4", search="binary")
    assert r.extra["interruptible"]
    assert r.solve_time < 3
    assert r.status in ("feasible", "optimal")
    assert validate(inst, r.schedule) == []


def test_solver_returns_none_when_interrupted():
    from solver import new_solver

    with new_solver("glucose4") as s:
        s.add_clauses([[1, 2], [-1, 2]])
        assert s.solve(time_limit=0) is None
        assert s.solve() is True
        assert 2 in s.model()


def test_cadical_reports_not_interruptible():
    from solver import new_solver

    with new_solver("cadical195") as s:
        assert not s.interruptible
