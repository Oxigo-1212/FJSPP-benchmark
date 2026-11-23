# FJSPLIB instances

Source: FJSPLIB from Monaldo Mastrolilli's FJSP page,
<https://people.idsia.ch/~monaldo/fjsp.html#ProblemInstances> (`TextData.zip`, text versions only).

| Folder | Family | Files |
|---|---|---|
| `brandimarte/` | Brandimarte (1993), Mk01–Mk10 | 10 |
| `barnes/` | Barnes & Chambers (1996) | 21 |
| `dauzere/` | Dauzère-Pérès & Paulli (1997) | 18 |
| `hurink/{sdata,edata,rdata,vdata}/` | Hurink, Jurisch & Thole (1994), see `hurink/README.txt` | 66 each |

Format (read by `helper.load_fjs`): first line `n_jobs n_machines [avg machines per op]`;
then one line per job: number of operations, then for each operation the number of
eligible machines `k` followed by `k` pairs `machine time` (machines 1-based).
Files use CRLF line endings, as in the original archive.
