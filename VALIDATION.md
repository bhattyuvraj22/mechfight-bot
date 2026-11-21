# First-draft validation — 21 November 2026

Environment: Linux development workspace, Python 3.12.14. These are local measurements, not the competition's one-CPU Docker sandbox and not a gameplay score.

## Completed

`python3 -m unittest discover -s tests -v`

- 18 tests passed.
- Includes thin-wall shot blocking, courtyard holes, bridge clearance under body growth, corner clearance, A* around a building, roof exit, moving-target interception, actual-aim gating, blocked targets, laser charge/release, lightning energy reserves, healing, zone urgency, upgrades, and pickup decisions.

`python3 check/check.py -- python3 -u bot.py`

```text
ready in 104 ms: name 'Oval-Sentinel-v0.1'
observations: 300  answered in time: 300  missed the 50 ms budget: 0
answer time ms: p50 2.2  p90 7.0  p99 12.6  max 17.6
answers to older queued observations: 0
wrong tick: 0  bad lines: 0  debug drawings: 0
PASS
```

`python3 check/benchmark.py`

| Workload | Decisions | p50 | p99 | Maximum | Over 50 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recorded observations, direct calls | 300 | 1.958 ms | 10.699 ms | 14.692 ms | 0 |
| Synthetic crowded scenes, direct calls | 240 | 11.317 ms | 25.655 ms | 31.950 ms | 0 |

Peak process RSS in that benchmark: 30.31 MiB (includes the benchmark fixtures).
Direct calls omit stdin/stdout and process scheduling. Timing varies by machine and load. The soft computation budget does not guarantee a server deadline.

## Pending

- Build the pinned Python 3.13.2 Linux/AMD64 image.
- Run the official checker with the exact read-only, unprivileged, one-CPU Docker flags in README.md.
- Push a public repository and obtain the first 48-match practice score.

No match simulator or authoritative house-bot implementation is included in the kit. No claim of a 6+ score has been established.
