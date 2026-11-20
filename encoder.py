"""FJSS -> CNF encoder (constraints S1-S7 of the write-up).

Variables (order encoding over the horizon H):
    X[i,j,k]     operation O_ij runs on machine k
    sa[i,j,t]    O_ij starts at or after t      (t in 1..H; constant 1 for t <= 0, 0 for t > H)
    eb[i,j,t]    O_ij ends at or before t       (t in 0..H-1; constant 0 for t < 0, 1 for t >= H)
    Y[a,b,k]     O_a runs before O_b on machine k

Boundary constants are folded away: no variable is created for them, a clause
with a true constant is dropped, and a false constant is removed from its clause.

The encoder only knows H. The makespan limit T of each solve comes from
`bound(enc, T)`, which returns assumptions, so one encoding serves every T <= H.
"""

from collections.abc import Callable
from dataclasses import dataclass
from math import isqrt
from itertools import combinations

from pysat.card import CardEnc, EncType
from pysat.formula import IDPool

from problem import Instance, eligible, operations

Clause = list[int]
Lit = int | bool  # a variable literal, or a folded boundary constant


@dataclass(frozen=True)
class Encoding:
    inst: Instance
    H: int
    clauses: list[Clause]
    pool: IDPool

    @property
    def n_vars(self) -> int:
        return self.pool.top

    @property
    def n_clauses(self) -> int:
        return len(self.clauses)


def encode(inst: Instance, H: int, amo: str) -> Encoding:
    """Build S1-S7 for horizon H, with the at-most-one encoding named `amo`."""
    pool = IDPool()
    clauses: list[Clause] = []
    add = lambda *lits: _add(clauses, lits)
    sa = lambda op, t: _sa(pool, H, op, t)
    eb = lambda op, t: _eb(pool, H, op, t)
    x = lambda op, k: pool.id(("x", *op, k))

    ops = operations(inst)
    machines = {op: eligible(inst.jobs[op[0]], op[1]) for op in ops}

    for op in ops:
        # S1: ⋁ₖ X_ijk  ∧  AMO({X_ijk : k ∈ m(O_ij)})   (exactly one machine)
        xs = [x(op, k) for k, _ in machines[op]]
        add(*xs)
        clauses.extend(AMO[amo](xs, pool))
        # S2: ∀t  sa_ij,t+1 → sa_ij,t
        for t in range(0, H + 1):
            add(_neg(sa(op, t + 1)), sa(op, t))
        # S3: ∀t  eb_ij,t → eb_ij,t+1
        for t in range(-1, H):
            add(_neg(eb(op, t)), eb(op, t + 1))
        # S4: ∀k, t  X_ijk → (eb_ij,t ↔ ¬sa_ij,t−p+1),  p = p_ijk
        for k, p in machines[op]:
            for t in range(0, H + 1):
                add(-x(op, k), _neg(eb(op, t)), _neg(sa(op, t - p + 1)))
                add(-x(op, k), sa(op, t - p + 1), eb(op, t))

    # S5: ∀t  ¬eb_ij,t → sa_i(j+1),t+1   (S_i,j+1 ≥ C_ij)
    for i, job in enumerate(inst.jobs):
        for j in range(len(job.times) - 1):
            for t in range(0, H + 1):
                add(eb((i, j), t), sa((i, j + 1), t + 1))

    # S6, S7: ∀a ≠ b, ∀k ∈ m(a) ∩ m(b)  (machine capacity)
    for a, b in combinations(ops, 2):
        shared = {k for k, _ in machines[a]} & {k for k, _ in machines[b]}
        for k in shared:
            y_ab, y_ba = pool.id(("y", *a, *b, k)), pool.id(("y", *b, *a, k))
            add(-x(a, k), -x(b, k), y_ab, y_ba)  # (16) X_ak ∧ X_bk → Y_abk ∨ Y_bak
            for y in (y_ab, y_ba):  # (17), (18) Y → X_ak ∧ X_bk
                add(-y, x(a, k))
                add(-y, x(b, k))
            for t in range(0, H + 1):  # S7: Y_abk ∧ ¬eb_a,t → sa_b,t+1  (S_b ≥ C_a), and symmetric
                add(-y_ab, eb(a, t), sa(b, t + 1))
                add(-y_ba, eb(b, t), sa(a, t + 1))

    return Encoding(inst, H, clauses, pool)


def bound(enc: Encoding, T: int) -> Clause:
    """Assumptions for 'makespan <= T': the last operation of every job ends by T."""
    if not 0 <= T <= enc.H:
        raise ValueError(f"T={T} outside 0..H={enc.H}")
    lits = [_eb(enc.pool, enc.H, (i, len(job.times) - 1), T) for i, job in enumerate(enc.inst.jobs)]
    return [l for l in lits if l is not True]


def decode(enc: Encoding, model: list[int]) -> tuple[dict, int]:
    """Schedule {(i, j): (machine, start, end)} and its makespan, read from a model."""
    true = {l for l in model if l > 0}
    schedule = {}
    for op in operations(enc.inst):
        k, p = next((k, p) for k, p in eligible(enc.inst.jobs[op[0]], op[1])
                    if enc.pool.obj2id.get(("x", *op, k)) in true)
        start = max((t for t in range(1, enc.H + 1)
                     if enc.pool.obj2id.get(("sa", *op, t)) in true), default=0)
        schedule[op] = (k, start, start + p)
    return schedule, max(end for _, _, end in schedule.values())


# --- literals with boundary constants (10) -------------------------------------

def _sa(pool: IDPool, H: int, op, t: int) -> Lit:
    if t <= 0:
        return True
    if t > H:
        return False
    return pool.id(("sa", *op, t))


def _eb(pool: IDPool, H: int, op, t: int) -> Lit:
    if t < 0:
        return False
    if t >= H:
        return True
    return pool.id(("eb", *op, t))


def _neg(l: Lit) -> Lit:
    return (not l) if isinstance(l, bool) else -l


def _add(clauses: list[Clause], lits) -> None:
    if any(l is True for l in lits):
        return
    clauses.append([l for l in lits if l is not False])


# --- at-most-one encodings ---------------------------------------------------------

def _ceil_sqrt(n: int) -> int:
    return isqrt(n - 1) + 1


def _pairwise(xs: list[int]) -> list[Clause]:
    return [[-a, -b] for a, b in combinations(xs, 2)]


def _cardenc(kind: int) -> Callable[[list[int], IDPool], list[Clause]]:
    return lambda xs, pool: CardEnc.atmost(xs, 1, vpool=pool, encoding=kind).clauses if len(xs) > 1 else []


def _commander(xs: list[int], pool: IDPool) -> list[Clause]:
    """note.md 5.1: groups of ceil(sqrt n), pairwise inside, x -> c, pairwise over commanders."""
    if len(xs) <= 1:
        return []
    g = _ceil_sqrt(len(xs))
    groups = [xs[s:s + g] for s in range(0, len(xs), g)]
    if len(groups) == 1:
        return _pairwise(xs)
    out, cs = [], []
    for grp in groups:
        c = pool.id(("cmd", *grp))
        cs.append(c)
        out += _pairwise(grp) + [[-v, c] for v in grp]
    return out + _pairwise(cs)


def _product(xs: list[int], pool: IDPool) -> list[Clause]:
    """note.md 5.2: grid with ceil(sqrt n) columns; x -> row, x -> col, pairwise on rows and cols."""
    if len(xs) <= 1:
        return []
    cols = _ceil_sqrt(len(xs))
    rows = -(-len(xs) // cols)
    r = [pool.id(("row", xs[0], i)) for i in range(rows)]
    c = [pool.id(("col", xs[0], j)) for j in range(cols)]
    out = []
    for n, v in enumerate(xs):
        out += [[-v, r[n // cols]], [-v, c[n % cols]]]
    return out + _pairwise(r) + _pairwise(c)


AMO: dict[str, Callable[[list[int], IDPool], list[Clause]]] = {
    "binary": _cardenc(EncType.bitwise),
    "seqcounter": _cardenc(EncType.seqcounter),
    "commander": _commander,
    "product": _product,
}
