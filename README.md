# FJSSP-benchmark

## Setup

```bash
uv venv -p 3.14
uv pip install -r requirements.txt
```

Gurobi and CPLEX install with size-limited free licenses; larger instances need full licenses
(their tests are skipped and the benchmark reports `license size limit`). CPLEX CP uses the
`cpoptimizer` binary from the `cplex` package, found automatically in `.venv/bin`.

## Tests

```bash
.venv/bin/python -m pytest
```

Checks every solver (and SAT backend / search / AMO variant) against proven optima, the
validator, the bounds, the SAT time limit, and that every instance in `data/fjsplib` parses.

## Command line

```bash
.venv/bin/python cli.py solve data/fjsplib/brandimarte/Mk01.fjs -s cpsat -t 30
.venv/bin/python cli.py bench data/fjsplib/brandimarte -t 20 -o results.csv
.venv/bin/python cli.py info  data/fjsplib/hurink/edata
```

- `solve` runs one solver (`-s`: `cpsat`, `cplex-cp`, `gurobi-mip`, `cplex-mip`, `sat`) on one
  instance and prints the status, makespan, lower bound, timings, model size and the schedule per
  machine. `--json` prints it as JSON; `--backend`, `--search`, `--amo`, `--repeated` tune `sat`.
- `bench` runs the selected solvers (default all) on files or folders and writes the section-9
  metrics (makespan, lower bound, status, build/solve/total time, variables, constraints, validity)
  to a CSV. CaDiCaL cannot be interrupted inside a call, so its runs can exceed the time limit;
  pass `--sat-backends glucose4` to avoid it.
- `info` lists jobs, machines, operations, average machines per operation, LB and UB.

`-t 0` removes the time limit (each solver runs until it proves the optimum).
`python cli.py COMMAND -h` lists every option.
