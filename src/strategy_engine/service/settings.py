"""Environment-driven service settings."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from strategy_engine.strategies.contracts import LIVE_ENTRY_MODES, LiveEntryMode

_CONFIG_KEYS = frozenset({"live_entry_mode"})


def _read_config_file(path: str | None) -> Mapping[str, Any]:
    """Engine config file (`touch-signal-close-entry-v1`), read once at
    start like MDS reads `markets.toml`. Unset path or missing file = no
    overrides; an unparsable file or an unknown key fails start."""

    if not path:
        return {}
    config_path = Path(path)
    if not config_path.is_file():
        return {}
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"engine config {path} is not valid TOML: {exc}") from exc
    unknown = sorted(set(payload) - _CONFIG_KEYS)
    if unknown:
        raise ValueError(f"engine config {path} has unknown keys: {unknown}")
    return payload


def _live_entry_mode(config: Mapping[str, Any]) -> LiveEntryMode:
    value = config.get("live_entry_mode", "ema_anchor")
    if value not in LIVE_ENTRY_MODES:
        raise ValueError(f"live_entry_mode must be one of {list(LIVE_ENTRY_MODES)}, got {value!r}")
    return cast(LiveEntryMode, value)


@dataclass(frozen=True, slots=True)
class Settings:
    http_host: str = "127.0.0.1"
    http_port: int = 8090
    mds_base_url: str = "http://127.0.0.1:8080"
    mds_connect_timeout_seconds: float = 2.0
    mds_read_timeout_seconds: float = 30.0
    max_batch_variants: int = 500
    episode_history_revalidate_seconds: float = 300.0
    episode_history_cache_entries: int = 16
    live_entry_mode: LiveEntryMode = "ema_anchor"

    @classmethod
    def from_env(cls) -> Settings:
        config = _read_config_file(os.getenv("STRATEGY_ENGINE_CONFIG_PATH"))
        return cls(
            http_host=os.getenv("STRATEGY_ENGINE_HTTP_HOST", "127.0.0.1"),
            http_port=int(os.getenv("STRATEGY_ENGINE_HTTP_PORT", "8090")),
            mds_base_url=os.getenv("STRATEGY_ENGINE_MDS_BASE_URL", "http://127.0.0.1:8080"),
            mds_connect_timeout_seconds=float(
                os.getenv("STRATEGY_ENGINE_MDS_CONNECT_TIMEOUT_SECONDS", "2")
            ),
            mds_read_timeout_seconds=float(
                os.getenv("STRATEGY_ENGINE_MDS_READ_TIMEOUT_SECONDS", "30")
            ),
            max_batch_variants=int(os.getenv("STRATEGY_ENGINE_MAX_BATCH_VARIANTS", "500")),
            episode_history_revalidate_seconds=float(
                os.getenv("STRATEGY_ENGINE_EPISODE_HISTORY_REVALIDATE_SECONDS", "300")
            ),
            episode_history_cache_entries=int(
                os.getenv("STRATEGY_ENGINE_EPISODE_HISTORY_CACHE_ENTRIES", "16")
            ),
            live_entry_mode=_live_entry_mode(config),
        )
