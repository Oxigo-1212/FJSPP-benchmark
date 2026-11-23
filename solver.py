"""SAT solver interface: the only module that touches a solver library.

Backends:
    any PySAT solver name ("cadical195", "glucose4", "minisat22", ...)
    "cryptominisat" through pycryptosat (PySAT's own "cryptosat" wrapper does not load)

A solver keeps its clauses and learned clauses between `solve` calls, so
incremental SAT reuses one solver and repeated SAT makes a new one per bound.

`solve(..., time_limit=seconds)` stops the call after that many seconds and
returns None (unknown) instead of True/False. Backends whose PySAT wrapper has no
interrupt (CaDiCaL, Kissat, Lingeling) ignore the limit; `interruptible` says which.
"""

import threading
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
        self.interruptible = True

    @abstractmethod
    def add_clause(self, clause: Clause) -> None:
        """Add one clause permanently."""

    @abstractmethod
    def _solve(self, assumptions: Clause, time_limit: float | None) -> bool | None:
        """Backend call: True (SAT, model stored in `_model`), False (UNSAT) or None (time limit hit)."""

    @abstractmethod
    def close(self) -> None:
        """Free the backend's resources."""

    def add_clauses(self, clauses: Iterable[Clause]) -> None:
        for c in clauses:
            self.add_clause(c)

    def solve(self, assumptions: Clause = (), time_limit: float | None = None) -> bool | None:
        """True when SAT under `assumptions` (the model is then available from `model`),
        False when UNSAT, None when `time_limit` seconds passed without an answer."""
        if time_limit is not None and time_limit <= 0:
            self._model = None
            return None
        self._model = None
        return self._solve(list(assumptions), time_limit)

    def model(self) -> list[int]:
        """Signed literals of the last SAT answer, e.g. [1, -2, 3]."""
        if self._model is None:
            raise ValueError("no model: last solve was not SAT or solve was not called")
        return self._model

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class PySATSolver(Solver):
    NO_ASSUMPTIONS = {"kissat404"}  # PySAT silently ignores assumptions for these

    def __init__(self, name: str):
        super().__init__(name)
        self._s = _PySAT(name=name)
        try:  # CaDiCaL, Kissat and Lingeling raise here: no interruptible solve in PySAT
            self._s.clear_interrupt()
        except NotImplementedError:
            self.interruptible = False

    def add_clause(self, clause: Clause) -> None:
        self._s.add_clause(clause)

    def _solve(self, assumptions: Clause, time_limit: float | None) -> bool | None:
        if assumptions and self.name in self.NO_ASSUMPTIONS:
            raise ValueError(f"{self.name} does not support assumptions")
        if time_limit is None or not self.interruptible:
            sat = self._s.solve(assumptions=assumptions)
        else:
            timer = threading.Timer(time_limit, self._s.interrupt)
            timer.start()
            try:
                sat = self._s.solve_limited(assumptions=assumptions, expect_interrupt=True)
            finally:
                timer.cancel()
                self._s.clear_interrupt()
        if sat:
            self._model = self._s.get_model()
        return sat

    def close(self) -> None:
        self._s.delete()


class CryptoMiniSat(Solver):
    def __init__(self):
        super().__init__("cryptominisat")
        self._s = pycryptosat.Solver()

    def add_clause(self, clause: Clause) -> None:
        self._s.add_clause(clause)

    def _solve(self, assumptions: Clause, time_limit: float | None) -> bool | None:
        sat, values = self._s.solve(assumptions, time_limit=time_limit) if time_limit is not None \
            else self._s.solve(assumptions)
        # pycryptosat returns (None, v1, v2, ...): index = variable, value = bool; sat is None when the limit hit
        if sat:
            self._model = [v if b else -v for v, b in enumerate(values) if b is not None]
        return sat

    def close(self) -> None:
        pass  # freed by Python's garbage collector


def new_solver(name: str) -> Solver:
    return CryptoMiniSat() if name == "cryptominisat" else PySATSolver(name)
