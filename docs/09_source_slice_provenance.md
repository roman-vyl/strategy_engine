# Source slice provenance

## Source

```text
archive: project_snapshot_20260711.zip
sha256: 3020cf491a185e495c16b77caddb9e8c06acb7e6577d6b6d9fe5efc9373046e6
extracted audit root: /mnt/data/bbb_snapshot_20260711
```

## Installed immutable slice

```text
legacy_source/bbb/research/strategies/ema_pullback/
legacy_source/bbb/tests/
legacy_source/bbb/copy_manifest.json
```

Counts:

```text
strategy package files: 61
selected tests/helpers: 23
manifest entries: 84
```

The copy was created by:

```bash
python scripts/copy_legacy_source.py \
  /mnt/data/bbb_snapshot_20260711 \
  --target /mnt/data/strategy_engine
```

## Rules

- Do not edit files under `legacy_source`.
- Do not add `legacy_source` to production `PYTHONPATH`.
- Do not copy BBB dependencies merely to make legacy imports work.
- Port behavior into clean modules under `src/strategy_engine`.
- Use the manifest SHA-256 to detect accidental drift.
