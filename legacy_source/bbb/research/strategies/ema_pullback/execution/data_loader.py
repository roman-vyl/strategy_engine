"""DB candle loading for ema_pullback execution."""

from __future__ import annotations

from data_engine.config import Settings
from data_engine.contracts import TimeWindow
from data_engine.engine.time_grid import tf_ms
from data_engine.store import Db

from research.ema_smoke_helpers import candles_to_ohlcv_dataframe
from research.strategies.ema_pullback.config import ExecutionConfig
from research.strategies.ema_pullback.execution.result_models import LoadedCandles


def load_candles_once(cfg: ExecutionConfig) -> LoadedCandles:
    """Load DB candles once and return OHLCV plus range metadata."""

    settings = Settings()
    if cfg.db_path is not None:
        settings = settings.model_copy(update={"db_path": cfg.db_path})

    db_path = settings.db_path
    existed = db_path.exists()
    db = Db(db_path)
    if not existed:
        db.apply_ddl()

    health = db.health()
    if health.get("contract") != "ok":
        raise SystemExit(f"database contract is not ok: {health!r}")

    symbol = cfg.symbol
    tf = cfg.timeframe
    step_ms = tf_ms(tf)

    t_min = db.min_open_time_ms(symbol, tf)
    t_max = db.max_open_time_ms(symbol, tf)
    if t_min is None or t_max is None:
        raise SystemExit(
            f"No candles for {symbol} {tf}. Run backfill + fix first, "
            "then re-run this script."
        )

    window = TimeWindow(t_min, t_max + step_ms)
    candles = db.range_get(symbol, tf, window)
    if len(candles) < 2:
        raise SystemExit("Not enough candles for a backtest.")

    return LoadedCandles(
        ohlcv=candles_to_ohlcv_dataframe(candles),
        candles_count=len(candles),
        from_open_time_ms=int(candles[0].open_time_ms),
        to_open_time_ms=int(candles[-1].open_time_ms),
    )
