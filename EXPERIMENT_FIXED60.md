# E1: fixed 60% gun lead

Hypothesis: random lead changes cause unnecessary aim corrections, particularly
when our gun requires alignment before firing. Holding the original 60% prior
may improve consistency against changing enemy movement. This is unproven.

One behavioral change: pick_lead always chooses 0.6 instead of Thompson-sampling
1.0, 0.6 or 0.3. The factor scales target velocity in the intercept calculation;
it does not scale bullet speed. Charging mechs and NPCs retain full lead.
Movement, target selection, firing gates, weapons, upgrades and healing do not
change. Existing hit bookkeeping remains so this experiment isolates the choice
of aim fraction. Bot name remains unchanged; identify submissions by commit SHA.

Apply on a clean committed checkout. The combat.py and test_v04.py starting
contents are identical across the uploaded v0.5 archive, v0.6 and baseline-simple,
so the patch supports each. Compare against the exact parent version you use;
changing the strategy and lead together would confound the result.

```bash
git status --short
git rev-parse HEAD
git apply --check ~/Downloads/mechfight-experiment-fixed60.patch
git apply ~/Downloads/mechfight-experiment-fixed60.patch
python3 -m unittest discover -s tests -q
python3 check/check.py -- python3 -u bot.py
docker build --platform linux/amd64 -t mechfight:fixed60 .
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" mechfight:fixed60
```

After all checks pass:

```bash
git add combat.py tests/test_v04.py EXPERIMENT_FIXED60.md
git commit -m "Experiment: fixed 60 percent gun lead"
git push
git rev-parse HEAD
```

Retain the parent commit and score. If baseline-simple has not been scored,
score that parent too before attributing an improvement or drop to E1. Compare
per-match placements if available; aggregate scores and timing can vary.
The 3.77 entry remains the best reported submission, not necessarily this
experiment's matched control.

Undo immediately before committing (only if these files have no later edits):

```bash
git apply --check -R ~/Downloads/mechfight-experiment-fixed60.patch
git apply -R ~/Downloads/mechfight-experiment-fixed60.patch
```

After committing, use git revert with the experiment's specific commit SHA,
then push. Do not revert unrelated later commits.

Validation on baseline-simple: 63 tests pass, official checker 300/300 timely,
p99 22.7 ms, max 27.4 ms, zero stale/invalid replies. Docker unavailable on the
development host. This is protocol validation, not a score or accuracy test.
