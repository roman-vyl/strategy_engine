"""Environment-driven service settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    http_host: str = "127.0.0.1"
    http_port: int = 8090
    mds_base_url: str = "http://127.0.0.1:8080"
    mds_connect_timeout_seconds: float = 2.0
    mds_read_timeout_seconds: float = 30.0
    max_batch_variants: int = 500

    @classmethod
    def from_env(cls) -> Settings:
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
        )
