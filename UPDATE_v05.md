# v0.5 candidate, based on the uploaded 3.77 bot

This is a candidate, not a demonstrated score improvement. Preserve the exact
3.77 commit. Local replay observations do not react to our actions: neither the
checker nor these tests measure placement. No score or no-regression guarantee
is possible before a practice run.

## Changes that work together

1. Select the shootable target before deciding whether to commit. Hysteresis is
   keyed to that target. Nearby enemies still contribute incoming damage even
   when behind cover, retaining the baseline's conservative threat estimate.
2. Cap each weapon's sustained contribution by its damage available over two
   seconds. Account for range, ammo, reload, cooldown, gun flight time, laser
   charge, and lightning energy after an 8-energy reserve. Do not count mortar
   damage while the combat controller cannot fire mortars. This is a heuristic:
   it does not simulate future aim alignment, front armor, or enemy upgrades.
3. Allow the wounded-target override only with a favourable commitment or enough
   predicted short-horizon damage. Once FIGHT is selected, authorize firing;
   gun aim/LOS/ammo checks still apply. This removes FIGHT-with-no-fire behavior.
4. Give emergency laser cover a bounded 4 ms search before ordinary steering.
   Skip steering/juking when cover owns the action. Bound juke prediction and
   candidate checks by the remaining budget; retain ordinary steering if the
   prediction cannot run. Use half speed while charging our own laser.
5. Reject enemy-held supply drops, check all local threats rather than four,
   and check zone safety through travel, landing wait, capture, and a 2-second
   margin. Safe uncontested drops remain available.

The upgrade order, main pathfinder, loot weights, range preferences, and adaptive
lead sampler remain unchanged. This limits simultaneous strategic changes.

## Research and what transfers

- Robocode wave surfing predicts reachable future positions against incoming
  fire. Mechfight provides projectile positions/velocities directly, so its
  existing swept collision predictor is useful; Robocode's energy-drop shot
  inference and bullet-speed formulas do not apply. This patch bounds that
  predictor and corrects its charging-speed input, rather than adding an entire
  statistical wave-surfer.
  https://book.robocode.dev/movement/advanced-evasion/wave-surfing-introduction
- Andrew Fray's context-steering work explains why independent steering choices
  can conflict. The transferable principle here is explicit action ownership
  and shared safety constraints. This patch prioritizes laser cover and prevents
  a later juke overwriting it. It is not a full context-map implementation.
  https://www.gameaipro.com/GameAIPro2/GameAIPro2_Chapter18_Context_Steering_Behavior-Driven_Steering_at_the_Macro_Scale.pdf
- Robocode waves/virtual guns learn from actual target positions at projectile
  arrival. That is a promising separate experiment for the current global
  hit-attribution sampler, but replacing it in this patch would obscure whether
  the decision fixes helped. Keep the present lead sampler for this submission;
  later compare per-target virtual prediction and fixed lead separately.
  https://book.robocode.dev/targeting/the-targeting-problem/introducing-waves.html

## Validation on the development host

- 73 unit/integration tests passed (58 existing + 15 new). Existing test weapon
  fixtures now contain reload duration and laser cooldown; previously their
  missing fields silently gave zero DPS in tactical evaluation.
- Official checker: 300/300 timely, zero stale/invalid replies, p99 18.7 ms,
  maximum 25.1 ms. Ready in 97 ms.
- Direct recorded benchmark: p99 18.198 ms, maximum 31.632 ms; zero over 50 ms.
- Crowded synthetic benchmark: p99 31.602 ms, maximum 49.553 ms; zero over 50 ms.
  That maximum leaves little margin; CPU scheduling and container hardware can
  change it. Peak process RSS about 30.23 MiB.
- Additional active-branch benchmark: 120/120 ticks actually juking, 120/120
  juking while charging, 120/120 dodging laser into cover. Maxima respectively
  10.952, 6.371, and 3.693 ms; zero over 50 ms.
- Docker is unavailable on this host. Run the actual amd64 container check below.

## Apply and test

Run from the repository root containing bot.py. Start with your uploaded 3.77
version and a clean working tree. If patch checking fails, stop: do not force it
onto a different experiment.

```bash
git status --short
git branch backup-score-3.77
git apply --check ~/Downloads/mechfight-3.77-to-v0.5.patch
git apply ~/Downloads/mechfight-3.77-to-v0.5.patch
python3 -m unittest discover -s tests -q
python3 check/check.py -- python3 -u bot.py
python3 check/benchmark_tactics.py
docker build --platform linux/amd64 -t mechfight:v0.5 .
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" mechfight:v0.5
```

After all checks pass:

```bash
git add bot.py tactics.py tests/test_bot.py tests/test_v05.py check/benchmark_tactics.py UPDATE_v05.md
git commit -m "Fix target commitment, weapon readiness and evasion priorities"
git push
git rev-parse HEAD
```

Submit that commit, retain the 3.77 submission, and record the practice result.
If it regresses, isolate engagement changes from movement/drop changes; do not
stack another broad tweak on top. The 2-second readiness horizon can be too
conservative when reloading behind safe cover, and rejecting enemy-held drops
can miss a profitable contest. These are deliberate tradeoffs to evaluate.
