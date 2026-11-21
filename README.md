# Oval Sentinel — first draft

A Python bot for `mechfight/1`. Target: a practice mean of **6+ placement points**.
This is a runnable, locally checked first candidate, **not a measured 6-point bot**.

## Quick start on your Mac

Extract the archive, open Terminal in this folder, and run:

```bash
python3 -m unittest discover -s tests -v
python3 check/check.py -- python3 -u bot.py
```

Python 3.11+ is recommended for local development. There are no pip dependencies.
The submission image uses Python 3.13.2.

With Docker Desktop running, build and check the Linux/AMD64 image:

```bash
docker build --platform linux/amd64 -t oval-sentinel:v0.1 .
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" oval-sentinel:v0.1
```

On Apple Silicon, AMD64 runs under emulation, so its timing is not the same as a native AMD64 scorer. The exact sandbox check still matters: it catches permission, map-path, and packaging mistakes. Docker was unavailable in the environment that produced this draft, so the image build and sandbox check have **not yet been verified**.

## What this version does

- Incremental A* on a 4 m ground grid, with cached body clearance and edge checks.
- Prism footprints, courtyard holes, bridge clearance, terrain sampling, roof-edge support, and cube-scaled body dimensions.
- Short movement rollouts that account for acceleration, obstacles, zone exposure, and incoming projectiles.
- Gun projectile interception and firing gated by actual torso alignment and a clear shot path.
- Laser charge/release scheduling, plus lightning with an energy reserve for escape.
- Retreat while facing threats, quiet recovery, selective crate/cube collection, nearby weapon pickup, and ranked upgrades.
- Early rotation into the next zone, stable goals, and stuck detection.
- Bounded search/steering work, stdout reserved for protocol messages, and no runtime file writes.

The strategy enters `COLLECT`, `FIGHT`, `ESCAPE`, `HEAL`, or `ROTATE` according to health, threat count, and zone urgency. It aims to fight isolated opponents and recover behind cover. It does not contain a special practice-seed route or identify house bots.

## Deliberate first-draft limits

- No mortar pickup or mortar firing, planned jet climbs, supply-drop capture strategy, or sound-bearing threat inference yet.
- Trees are not modelled for vision. They correctly do not block our bullet ray checks, but the bot does not yet exploit foliage concealment.
- Terrain and movement predictions are approximate. Ground A* is conservative; local roof movement is not a full 3D path planner.
- The server can auto-fire a held laser; releasing an existing charge during retreat may produce one final shot and delay regeneration.
- Upgrade priorities, engagement distances, and health thresholds are initial hypotheses, not tuned results.
- The supplied recording is not a simulator. Neither tests nor synthetic timing scenes establish a practice score.

## Files

| File | Purpose |
| --- | --- |
| `bot.py` | State selection, loot, upgrades, movement evaluation, main entry point |
| `geometry.py` | Terrain, prisms, body clearance, shot paths, local support |
| `navigation.py` | Incremental A* and cached grid queries |
| `combat.py` | Gun interception, aiming, weapon triggers |
| `mechfight.py` | Supplied protocol wrapper |
| `Dockerfile` | Submission image; already at repository root |
| `tests/test_bot.py` | Focused geometry, combat, and policy tests |
| `check/check.py` | Organizer's unchanged protocol checker |
| `check/benchmark.py` | Direct-call timing and synthetic stress scenarios |
| `arena/` | Organizer's map for local tests; scorer mounts its own `/arena` |
| `VALIDATION.md` | Checks completed while preparing this draft |

## Submit after the container check passes

Create a public GitHub repository and put **this folder's contents** at its root. Do not put the whole folder inside another folder: the Dockerfile must be at the root.

If starting a new repository locally:

```bash
git init
git add .
git commit -m "Add Oval Sentinel first draft"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
git rev-parse HEAD
```

Replace the repository URL with your real public repository. Submit that repository and the exact commit on the competition page. This draft has not been pushed or submitted for you.

Keep a record of each commit and practice score. For the next candidate, change one major strategy at a time: disengagement thresholds, mobility/regen upgrades, or secondary-weapon choice. Prioritize measured failures over adding features. Practice matches and the final free-for-all have different opponents, so avoid tuning only to the fixed practice seeds.

## Optional timing report

```bash
python3 check/benchmark.py
```

The synthetic cases intentionally crowd observations with 15 actors and 48 projectiles. They exercise computation and action validity, not house-bot tactics or authoritative physics.

The Docker base uses an explicit Python patch tag. For a fully immutable final build, replace that tag with the verified image digest after the first successful build.
