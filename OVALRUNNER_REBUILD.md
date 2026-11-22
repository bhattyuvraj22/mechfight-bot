# OvalRunner-derived controller replacement

## Provenance and scope

Patch base: bhattyuvraj22/mechfight-bot at c556552ce1bdc31e15f7a53aa3f24c507d1107c4.
Source: https://github.com/SandeepMadhavarapu/BattleRoyale/tree/b532564a5fa97370d1f18da29b2c28198b80b426
This is the revision associated with the author's reported 6.25 practice score, not a score achieved by this repository. Its underlying Giddy source is credited to e19e3c8d45d980df35c2fa5318353aaeb7c515bd.
Both upstream MIT licenses are retained and copied into the runtime image. This is an attributed source reuse experiment, not an independently authored controller. Competition reuse eligibility is separate from its software license.

The Go controller completely replaces the Python entrypoint in Docker. Existing Python files remain for reference and rollback; editing them no longer changes the submitted bot. Old Python tests do not validate the active Go controller.

Runtime policy files and embedded parameters are byte-for-byte upstream. Changes are the ready display name, packaging to include licenses, disabled build VCS stamping, documentation, and integration tests. No strategy thresholds were tuned.

## Actual active strategy

- Initially use the defensive base policy; after 20 seconds, infer squad practice unless deaths not caused by this bot persist for five observations. This heuristic is not guaranteed to identify all free-for-all matches correctly.
- Practice policy emphasizes laser acquisition, resource farming, strong target commitment, low-HP targets and close finishing. Laser preferred spacing is 120 m in this mode; it does not demand an isolated enemy before fighting.
- Restore the defensive base policy once next-zone radius is at most 140 m. Ghost mode still engages nearby threats, recent attackers, some vulnerable targets and endgame opponents. It is not a no-fire mode.
- Base retreat/recovery thresholds are 38% / 80% HP, subject to finishing and other tactical conditions. Cover, cooldown peeking, navigation, remembered objects and projectile handling come from upstream.
- Embedded parameters: salt=0, Ears=false, EndGhost=140, no squad overrides. The upstream README's 70 m description is stale for this revision; params.json is authoritative.
- Numerous optional mechanisms in brain.go are disabled by default. Their presence does not establish that the scored policy used them.

## Validation performed

Go 1.26.1 linux/amd64 toolchain download verified against its official SHA-256. CGO disabled; static amd64 binary builds successfully.
`go test ./...`: recorded observations with zero recovered panics, practice-to-EndGhost transition and persistence, and other-deaths practice detection all pass.
Official checker: 300/300 on time, zero invalid lines/ticks; p50 0.4 ms, p99 2.4 ms, max 3.6 ms on the host. This is a noninteractive recording, not a match simulator.
Docker is unavailable in the preparation environment: the image build, UID 65534 and complete container constraints must still be checked below. No competitive match was run. Go map iteration and execution timing mean copying source does not guarantee identical actions or scores.

## Run before pushing (Mac / Docker Desktop)

```sh
docker build --platform linux/amd64 -t mechfight-ovalrunner .
python3 check/check.py --map-dir /arena -- docker run --rm -i \
  --platform linux/amd64 --network none --cpus 1 --memory 512m \
  --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 \
  -v "$PWD/arena:/arena:ro" mechfight-ovalrunner
```

Optional source-level tests with Go 1.26.1 installed: `go test ./...`.
Build dependencies are pinned in Dockerfile. Runtime has no package dependencies or network requirements. Only Go source, embedded parameters and license files enter the image; the map is mounted by the referee.

## Apply / rollback

Before applying, use `git status --short` and keep unrelated changes separate. Create a new branch and record the current revision with a local tag. Run `git apply --check` before applying the patch. Build/check successfully before committing and pushing.

To undo after committing the replacement, use `git revert <replacement-commit>`. This restores the previous Docker entrypoint. Keep the best officially scored submission selected until a replacement actually beats it; a source author's score is not a prediction.

## Upstream file SHA-256

- `mech/brain.go`: `583745746425168fc3d21e48aeb86af358db256d0c95a6d6ac0c1f6667956cfc`
- `mech/world.go`: `a2cf879007fc3bc49cfc0bb90e6e99e8cff5a9413f85499c6b165bfee6d27ec4`
- `mech/types.go`: `6cd04c9cef22385436693a1d9806d9afc6f0cc58d0c4661496326e00abd38473`
- `mech/export.go`: `3f0384222b15eddf9f516b74e89beefe44e65a10fef294735424f042d982967b`
- `cmd/bot/params.json`: `33904e757fa9f4ef2e4cb8cde8e4b737a79f2bdc307988cae6e1f2046b146d9d`
- `go.mod`: `51496525f2844bdd830c5d1e202b54bd97d9dfad96381782fea13fa51e6fc3fb`
