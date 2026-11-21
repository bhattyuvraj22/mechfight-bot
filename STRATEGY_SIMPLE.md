# Baseline-simple: a small candidate built directly on the 3.77 submission

## Evidence ledger

| Version | Reported practice score | What we can conclude |
|---|---:|---|
| v0.1 | 2.44 | Initial baseline |
| v0.2 | 3.38 | Better reported result than v0.1 |
| v0.3 | 3.19 | That bundle regressed relative to v0.2 |
| User's experimental v0.4 | 3.77 | Best reported submission; source for this patch |
| v0.5 | 3.58 | Bundle did not beat 3.77 |
| v0.6 | Not reported | No score evidence; not the source of this patch |
| Baseline-simple | Not scored | Current candidate |

These aggregate scores cannot identify which individual changes helped or hurt.
We do not have per-match placements, death causes, damage logs, or rerun variance.
The claim that v0.5 became too conservative is a hypothesis, not a demonstrated
cause. Preserve the exact 3.77 commit as the best scored entry.

## Strategy

1. Rotate when the zone requires it.
2. Otherwise take the baseline's favourable fights and wounded-target finishes.
   Compute commitment against the enemy actually selected for shooting; still
   count nearby enemies when estimating incoming damage.
3. Once FIGHT is chosen, authorize shooting. Existing weapon-specific aim,
   range, line-of-sight, ammunition and energy checks still apply.
4. Keep the baseline's recovery and outnumbered-retreat decisions.
5. When safe, retain its cube collection, drone hunting and upgrade priorities.

Only two runtime decision fixes are included. There is no two-second readiness
cap, stricter finish threshold, new RELOAD mode, changed retreat curve, modified
supply-drop policy, new evasion scheduler, or new aiming model. Existing behavior
is retained deliberately so we can interpret the next result.

The fixes may still reduce score: rejecting a commitment based on a hidden weak
enemy can change a formerly successful encounter; shooting during a selected
finish can delay regeneration. This is a testable candidate, not a final proven
winner. Local checks cannot measure placement.

## Validation

63 tests passed: 58 baseline tests plus 5 focused regression tests. New fixtures
use complete weapon stats from the actual config. Existing tests are untouched.
Official checker: 300/300 timely, zero stale/invalid replies, p99 19.4 ms and max
24.9 ms. Synthetic crowd benchmark: 240 decisions, p99 32.137 ms, max 44.417 ms,
zero over 50 ms. Peak RSS 30.32 MiB. Host timing is not a container guarantee.
Docker unavailable here; run the amd64 check locally.

## Apply to the newly uploaded archive

This patch is based on mechfight-draft(1).zip. Its bot.py matches v0.5, despite
v0.6 having been reported as applied. Use this patch only on that uploaded code.
It restores the 3.77 runtime with the two fixes above. It replaces obsolete v0.5
regression tests with baseline-simple tests; older UPDATE documents describe
historical candidates and do not describe this runtime.

Run from your repository root; no checkout or worktree is necessary:

```bash
git apply --check ~/Downloads/mechfight-upload-to-simple.patch
git apply ~/Downloads/mechfight-upload-to-simple.patch
python3 -m unittest discover -s tests -q
python3 check/check.py -- python3 -u bot.py
docker build --platform linux/amd64 -t mechfight:simple .
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" mechfight:simple
```

Stop if the patch check fails; do not force it onto different code. After all
checks pass, review git diff and commit:

```bash
git add bot.py tactics.py tests/test_bot.py tests/test_v05.py tests/test_simple.py STRATEGY_SIMPLE.md
git commit -m "Restore 3.77 strategy with target and firing consistency fixes"
git push
git rev-parse HEAD
```

Submit that exact SHA and retain the 3.77 entry. No practice score for this
candidate is available yet. Docker remains to be checked on your machine.
