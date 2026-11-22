# Spacing and recovery experiment

Apply AFTER mechfight-current3-position.patch. Input is exactly the previously
produced position-candidate, not the unpatched mechfight-draft(3).zip.

Changes:
- Keep baseline own-weapon preferences. After the wounded-enemy closing rule,
  impose minimum preferred distance 64 m vs lightning and 80 m vs mortar when
  we do not hold lightning. NPC preferred distance becomes 58 m.
- A group-triggered retreat extends a recovery hold to two seconds after the
  latest qualifying group observation. During this hold, disable the duel-position
  search, pursue existing escape/heal cover, and skip healing-drop detours.
  Zone urgency and the existing short safe-finishing exception override it.
  Ordinary baseline healing thresholds still apply after it expires.

Evidence and limits:
Coverdrive's downloaded stripped Go binary retains a .gopclntab. Recovering its
function table allowed disassembly of Brain.prefRange, NewBrain, odds and
squadParams. The preferred-range branch structure and constants 58/64/80 match
https://github.com/waiprotein/mech-royale-bot/blob/HEAD/mech/brain.go .
The lightning-energy threshold in that function is 12, but we intentionally keep
our existing own-lightning energy/distance rule. Public source recovery logic
in waiprotein and Kestrel motivates the hold; TWO SECONDS IS OUR TUNING, NOT A
RECOVERED COVERDRIVE VALUE. No full controller reconstruction or score replication
is claimed. No competitor code is copied.
https://github.com/brycehcmcgrath/mechfight-bot
https://github.com/nguyenphuquang1234567/kestrel

Known tradeoffs: spacing can lose wounded-target opportunities. The short hold
can reduce pressure. Enemy range upgrades are not inferred; minimum distance is
not a safety guarantee. No new enemy-memory model or weapon-cooldown peeking is
included. These two additions should be isolated if the combined result regresses.
The paired parent score is needed; 3.77 remains the best reported baseline.

Validation: 70 tests pass; official checker 300/300 timely, p99 18.3/max 24.8 ms.
Synthetic crowd benchmark max 29.198 ms, no late calls, RSS 30.48 MiB. Replay
and synthetic observations do not simulate the consequences of our actions.
Docker was not available here. Run the constrained amd64 check before submission.

Apply with git apply --check first; stop on mismatch. Changes are bot.py,
tests/test_spacing_recovery.py and this document. Bot display name is unchanged;
identify this experiment by commit SHA.
