"""Smoke tests for cli.py."""

import csv
import json

import pytest

from cli import main

from .conftest import DATA

MK01 = str(DATA / "brandimarte" / "Mk01.fjs")


def test_solve_prints_valid_optimal_schedule(capsys):
    main(["solve", MK01, "-s", "cpsat", "-t", "30"])
    out = capsys.readouterr().out
    assert "status     optimal" in out
    assert "makespan   40" in out
    assert "valid      yes" in out
    assert out.count("\n  M") == 6  # one schedule line per machine


def test_solve_json(capsys):
    main(["solve", MK01, "-s", "sat", "--backend", "glucose4", "--json"])
    r = json.loads(capsys.readouterr().out)
    assert (r["status"], r["makespan"], r["valid"]) == ("optimal", 40, True)
    assert len(r["schedule"]) == 55


def test_bench_writes_csv(tmp_path):
    out = tmp_path / "r.csv"
    main(["bench", MK01, "-s", "cpsat", "sat", "--sat-backends", "glucose4", "-t", "30", "-o", str(out)])
    rows = list(csv.DictReader(out.open()))
    assert [r["solver"] for r in rows] == ["cpsat", "sat[glucose4]"]
    assert all(r["status"] == "optimal" and r["makespan"] == "40" and r["valid"] == "True" for r in rows)


def test_info_lists_folder(capsys):
    main(["info", str(DATA / "brandimarte")])
    assert capsys.readouterr().out.count("Mk") == 10


def test_missing_file_exits():
    with pytest.raises(SystemExit):
        main(["solve", "does-not-exist.fjs"])


@pytest.mark.parametrize("text, expected", [("0", None), ("none", None), ("2.5", 2.5)])
def test_time_limit_zero_means_none(text, expected):
    from cli import time_limit
    assert time_limit(text) == expected


def test_solve_without_time_limit(capsys):
    main(["solve", MK01, "-t", "0", "-q"])
    assert "status     optimal" in capsys.readouterr().out
