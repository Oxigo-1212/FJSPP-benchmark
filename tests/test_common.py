"""Bounds (8.1), validator (8.3) and the dataset files."""

import pytest

from helper import load_fjs
from solvers.common import lower_bound, makespan, sequential_schedule, upper_bound, validate

from .conftest import DATA, pdf_example


def test_bounds_on_pdf_example():
    inst = pdf_example()
    assert lower_bound(inst) == 5  # job bound 3+2 = 5, load bound ceil((3+2+2+3)/2) = 5
    assert upper_bound(inst) == 10


def test_sequential_schedule_is_valid_and_meets_upper_bound():
    inst = load_fjs(DATA / "brandimarte" / "Mk01.fjs")
    s = sequential_schedule(inst)
    assert validate(inst, s) == []
    assert makespan(s) == upper_bound(inst)


# the valid schedule from section 4 of the write-up (machines 0-based)
PDF_SCHEDULE = {(0, 0): (0, 0, 3), (0, 1): (1, 3, 5), (1, 0): (1, 0, 3), (1, 1): (0, 3, 6)}


def test_validator_accepts_pdf_schedule():
    assert validate(pdf_example(), PDF_SCHEDULE, H=6) == []


@pytest.mark.parametrize("change, expected", [
    ({(0, 1): (0, 3, 5)}, "not in its eligible set"),  # O12 only runs on machine 2
    ({(0, 0): (0, 0, 4)}, "C-S"),                       # wrong duration
    ({(0, 1): (1, 2, 4)}, "after"),                     # O12 starts before O11 ends
    ({(1, 1): (0, 2, 5), (1, 0): (1, -1, 2)}, "machine 0"),  # O22 overlaps O11 on M1
    ({(1, 0): (1, -1, 2), (1, 1): (0, 3, 6)}, "< 0"),   # negative start
])
def test_validator_rejects(change, expected):
    errors = validate(pdf_example(), PDF_SCHEDULE | change)
    assert any(expected in e for e in errors), errors


def test_validator_rejects_missing_operation_and_makespan_over_h():
    inst = pdf_example()
    assert validate(inst, {k: v for k, v in PDF_SCHEDULE.items() if k != (1, 1)})
    assert any("makespan" in e for e in validate(inst, PDF_SCHEDULE, H=5))


@pytest.mark.parametrize("path", sorted(DATA.rglob("*.fjs")), ids=lambda p: str(p.relative_to(DATA)))
def test_dataset_file_parses(path):
    inst = load_fjs(path)
    first = path.read_text().split()
    assert len(inst.jobs) == int(first[0])
    assert inst.n_machines == int(first[1])
    assert lower_bound(inst) <= upper_bound(inst)
