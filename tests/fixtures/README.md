# Refactor regression fixtures

Generated from the original `hadleys_hope.py` supplied in `world-archive.zip`.
Source SHA-256: `287f32bbddc9c563a0648114993f599669fba9427c19826265eea4d1772069d4`.

- `simulation.json.gz`: deep JSON copies at ticks 0, 1, 10, 60, 120; then a
  tick from 1439 and a tick from month-end minus one, using seed 12345.
- `legacy-hadleys_hope.pkl.gz`, `legacy-__main__.pkl.gz`: original World at
  tick 123 with one issue, serialized with both historical class-module paths.

These are trusted synthetic test fixtures, not production saves. They verify
compatibility with the supplied source. Regenerate deliberately when physics
changes; do not regenerate merely to make a failing refactor test pass.
