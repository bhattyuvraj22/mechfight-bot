# Position-based isolation experiment

Based exactly on mechfight-draft(3).zip. Independent implementation inspired by
Kestrel's duel-position concept and the cover-adjacent positioning visible in the
public waiprotein Go controller:
https://github.com/nguyenphuquang1234567/kestrel
https://github.com/waiprotein/mech-royale-bot
No competitor code is copied.

Healthy bots not recovering search the current position and 16 nearby positions.
Candidates must be walkable, zone-safe, retain target line of sight, block other
known local mechs, and have reachable full cover six metres away. Search has a
4 ms slice within the existing decision budget and declines crowds over four.
The existing retreat remains the fallback. A valid point becomes the fight goal;
random juke override is suppressed while it is active; emergency laser dodge
remains active. Aim, upgrades and loot rules are unchanged.

This does not add weapon swapping, rooftops, persistent enemy memory or a new
recovery timer. The escape point is a safety check, not a reserved escape path.
It models current positions and line of sight, not opponent future motion or
exposure along the entire approach. Ordinary local steering still controls the
actual move. No practice improvement has been established.

Validation: 65 tests pass; checker 300/300 timely, p99 22.7 ms/max 25.1 ms;
crowd benchmark max 40.892 ms, zero over 50 ms, peak RSS 30.6 MiB. Docker wasn't
run here. The bot display name remains unchanged; track submissions by SHA.

Apply mechfight-current3-position.patch to the uploaded version with git apply
--check first. Run tests, the official checker, and the constrained amd64 Docker
check before pushing. Keep the parent commit for a matched score comparison and
retain the best scored 3.77 entry. Earlier strategy documents are historical.
