"""Service CLI entrypoint."""

from __future__ import annotations

import uvicorn

from strategy_engine.service.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "strategy_engine.adapters.http.app:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
    )


if __name__ == "__main__":
    main()
