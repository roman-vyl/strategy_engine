# Scripts

The first script will copy and hash the exact BBB source paths listed in `docs/05_initial_copy_manifest.md`.

`verify_release_archive.py` rejects stale built distributions and `egg-info`
from the source tree. When given a ZIP, it also verifies CRC and rejects VCS,
virtual-environment, cache, bytecode, nested archive, and generated package
members:

```bash
python scripts/verify_release_archive.py .
python scripts/verify_release_archive.py strategy_engine_release.zip
```
