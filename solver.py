"""SAT solver interface: the only module that touches a solver library.

Backends:
    any PySAT solver name ("cadical195", "glucose4", "minisat22", ...)
    "cryptominisat" through pycryptosat (PySAT's own "cryptosat" wrapper does not load)

A solver keeps its clauses and learned clauses between `solve` calls, so
incremental SAT reuses one solver and repeated SAT makes a new one per bound.
"""

from collections.abc import Iterable

import pycryptosat
from pysat.solvers import Solver as _PySAT

Clause = list[int]


from abc import ABC, abstractmethod


class Solver(ABC):
    """Solver interface. Subclasses implement `add_clause`, `_solve` and `close`."""

    def __init__(self, name: str):
        self.name = name
        self._model: list[int] | None = None

    @abstractmethod
    def add_clause(self, clause: Clause) -> None:
        """Add one clause permanently."""

    @abstractmethod
    def _solve(self, assumptions: Clause) -> list[int] | None:
        """Backend call: the model as signed literals when SAT, None when UNSAT."""

    @abstractmethod
    def close(self) -> None:
        """Free the backend's resources."""

    def add_clauses(self, clauses: Iterable[Clause]) -> None:
        for c in clauses:
            self.add_clause(c)

    def solve(self, assumptions: Clause = ()) -> bool:
        """True when SAT under `assumptions`; the model is then available from `model`."""
        self._model = self._solve(list(assumptions))
        return self._model is not None

    def model(self) -> list[int]:
        """Signed literals of the last SAT answer, e.g. [1, -2, 3]."""
        if self._model is None:
            raise ValueError("no model: last solve was UNSAT or solve was not called")
        return self._model

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class PySATSolver(Solver):
    NO_ASSUMPTIONS = {"kissat404"}  # PySAT silently ignores assumptions for these

    def __init__(self, name: str):
        super().__init__(name)
        self._backend = _PySAT(name=name)

    def add_clause(self, clause: Clause) -> None:
        self._s.add_clause(clause)

    def _solve(self, assumptions: Clause) -> list[int] | None:
        if assumptions and self.name in self.NO_ASSUMPTIONS:
            raise ValueError(f"{self.name} does not support assumptions")
        return self._s.get_model() if self._s.solve(assumptions=assumptions) else None

    def close(self) -> None:
        self._s.delete()


class CryptoMiniSat(Solver):
    def __init__(self):
        super().__init__("cryptominisat")
        self._backend = pycryptosat.Solver()

    def add_clause(self, clause: Clause) -> None:
        self._s.add_clause(clause)

    def _solve(self, assumptions: Clause) -> list[int] | None:
        sat, values = self._s.solve(assumptions)
        # pycryptosat returns (None, v1, v2, ...): index = variable, value = bool
        return [v if b else -v for v, b in enumerate(values) if b is not None] if sat else None

    def close(self) -> None:
        pass  # freed by Python's garbage collector


def new_solver(name: str) -> Solver:
    return CryptoMiniSat() if name == "cryptominisat" else PySATSolver(name)
