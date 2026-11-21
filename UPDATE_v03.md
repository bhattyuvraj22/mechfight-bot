# Oval Sentinel v0.3 — update from v0.2

## Baseline and evidence

User-reported practice scores: v0.1 **2.44**, v0.2 **3.38**. v0.3 is an unscored candidate targeting 6+. No match replays or per-match death records were available. The following behaviours were reproduced in controlled observations; how much each affected real placements is unknown.

| Weakness reproduced in v0.2 | v0.3 change |
| --- | --- |
| A low-HP mech stands still in the open against an enemy 170 m away. Exposure cost is flat past 140 m, despite default gun range 230 m. | Exposure varies with estimated weapon reach; direct retreat is evaluated early, and low-HP ranged escapes can boost. Enemy upgrades are unknown, so reach remains an estimate. |
| With only a gun, the bot advances toward an enemy 170 m away while ignoring a weapon 40 m behind it. | EQUIP prioritizes reachable weapons when exposed threats are distant, while close combat and zone urgency retain priority. |
| Boost restarts as soon as energy barely exceeds 32, repeatedly delaying regeneration. | Continue a boost down to 22 energy, then wait until above 58 to restart. Urgent zone escape can use the reserve. These thresholds are initial policy choices, not score-tuned optima. |
| A low-HP mech ignores a nearby landed supply drop and waits for slower regeneration. | CAPTURE approaches short clear routes only, rejects waiting/contested drops, checks known threat arrival time and future zone safety, and holds inside the ring. Unseen enemies are still possible. |
| During a gun reload with no usable secondary, the bot stays in its ordinary fighting posture. | RELOAD seeks safer positioning while the gun is unavailable; a ready suitable secondary can keep it fighting. |

## Scope

The patch changes only **bot.py**, **tests/test_bot.py**, and adds this note. Combat aiming, navigation, map geometry, Dockerfile, and the protocol wrapper are unchanged from v0.2. All earlier retreat-fire and corner fixes remain.

No mortar firing, planned jet climbs, foliage stealth, or new dependencies were added. Supply-drop tactics and equipment priority are hypotheses to evaluate in the next practice run, not guaranteed improvements.

## Validation performed

- **42 unit/scenario tests passed.** Six targeted new scenarios were also run against v0.2: six assertion failures, zero execution errors. All six pass with v0.3.
- Official checker: **300/300 timely answers**, zero wrong ticks, invalid lines, or stale queued answers. Ready: 124 ms. Response times: p50 2.8 ms, p90 7.2 ms, p99 15.2 ms, maximum 23.5 ms.
- Direct recorded-observation benchmark: 300 decisions, p99 19.280 ms, maximum 24.063 ms, zero over 50 ms.
- Synthetic crowded benchmark: 240 decisions, p99 25.754 ms, maximum 26.534 ms, zero over 50 ms. Peak process memory including fixtures: 30.26 MiB.

These measurements used Linux/Python 3.12.14 locally, not the scorer's constrained Docker runtime. Fixed observations and synthetic scenes are not gameplay simulations and do not produce placement scores. Docker is unavailable in this environment; image build and exact sandbox verification remain pending on your machine.

## Apply, check, then push

Run from your existing repository root, with the patch downloaded to Downloads:

```bash
git apply --check ~/Downloads/mechfight-v0.2-to-v0.3.patch &&
git apply ~/Downloads/mechfight-v0.2-to-v0.3.patch
```

If this reports a conflict, stop and inspect the error; do not force application. The patch expects the previous v0.2 code, including its 29-test file.

```bash
python3 -m unittest discover -s tests -v &&
python3 check/check.py -- python3 -u bot.py
```

With Docker Desktop running:

```bash
docker build --platform linux/amd64 -t oval-sentinel:v0.3 . &&
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" oval-sentinel:v0.3
```

After all checks pass:

```bash
git add bot.py tests/test_bot.py UPDATE_v03.md &&
git commit -m "Improve ranged escape, equipment and recovery" &&
git push origin main &&
git rev-parse HEAD
```

Submit the new commit ID with the same repository URL. Keep the 3.38-scoring v0.2 commit as the comparison baseline. If the new score regresses, the first policies to isolate are supply-drop detours and equipment priority, separately from the stationary-retreat correction.
