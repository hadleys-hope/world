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

## Deliberate edits

- `simulation.json.gz`, path `month.report.sector_income` only: was
  `[1750.0] * 6` (fees collected at month close), now
  `[1843.9, 1844.6, 1842.9, 1841.9, 1842.9, 1842.9]`, all the money each
  sector received in the month (daily utility bills + fees). The old line did
  not reconcile with `sector_budget` (10000 + 1750 != 11844). Spliced: every
  other leaf was asserted unchanged, written with `json.dumps` and gzip
  `mtime=0`. The file was not regenerated, because a regeneration on macOS
  would bake a 1-ULP libm difference into `rovers[21]` (see
  `tests/test_regression.py`).
- New API keys (`finance.households`, `houses.fin`, `houses.cash`,
  `report.households`, `house.finance`) are removed by the normalisers in
  `tests/test_regression.py`, which also assert their golden-run values.
