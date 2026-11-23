"""Solvers compared in section 9: the SAT solver against CPLEX CP, CPLEX MIP, Gurobi and CP-SAT.

Every module exposes `solve(inst, time_limit=None, **options) -> Result`.
Modules are imported on first use, so a missing commercial package only breaks its own solver.
"""

from importlib import import_module

from .common import Result, lower_bound, upper_bound, validate

SOLVERS = {
    "sat": "sat",
    "cpsat": "cpsat",
    "gurobi-mip": "gurobi_mip",
    "cplex-mip": "cplex_mip",
    "cplex-cp": "cplex_cp",
}


def get_solver(name: str):
    """The `solve` function of the solver called `name` (a key of SOLVERS)."""
    if name not in SOLVERS:
        raise ValueError(f"unknown solver {name!r}; choose from {sorted(SOLVERS)}")
    return import_module(f".{SOLVERS[name]}", __name__).solve


__all__ = ["SOLVERS", "Result", "get_solver", "lower_bound", "upper_bound", "validate"]
