"""
DEVI 2.0 Live/Paper MT5 Loop

Streams live (or pseudo-live) bars into the TradingPipeline using MT5Executor.

This script is intentionally conservative and does NOT change any PR3/PR4 logic.
It only wires a streaming loop around the existing TradingPipeline, MT5Executor,
config loader, and JSON logging similar to backtest_dry_run.py.

Usage (from repo root):
    python run_live_mt5.py --symbols EURUSD XAUUSD AUDUSD AUDJPY USDJPY NVDA TSLA \
                           --mode paper --poll-seconds 10

If the MetaTrader5 Python package is not available, or MT5 initialization fails,
this script will fall back to a synthetic pseudo-live feed using the same CSV /
or synthetic data helpers as backtest_dry_run.py, so it remains usable for
testing.
"""

import sys
import os
import argparse
import json
import logging
from collections import deque
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Deque, Tuple, Optional, List

# Force UTF-8 encoding on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Core imports
from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.orchestration.pipeline import TradingPipeline
from core.execution.mt5_executor import MT5Executor, ExecutionMode
from configs import config_loader

# Reuse helpers from backtest script for CSV/synthetic fallback
from backtest_dry_run import load_csv_data, create_sample_data, create_config


class JSONFormatter(logging.Formatter):
    """JSON log formatter compatible with backtest_dry_run.py."""

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "getMessage",
                ]:
                    if not key.startswith("_"):
                        log_obj[key] = value
        return json.dumps(log_obj)


def setup_logging() -> Path:
    """Setup JSON logging to file, mirroring backtest_dry_run.py."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"live_mt5_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root_logger.addHandler(console_handler)

    return log_file


def create_live_config() -> Config:
    """Load full Config structure using the existing config loader."""
    return create_config()


def init_executor(config: Config, mode: str) -> MT5Executor:
    """Initialize MT5Executor in the requested mode using system execution config."""
    exec_cfg = dict((config.system_configs or {}).get("execution", {}) or {})
    # Ensure min_rr is present for the executor; default to 1.5 as elsewhere
    exec_cfg.setdefault("min_rr", 1.5)
    exec_cfg.setdefault("enabled", True)

    if mode.lower() == "live":
        exec_mode = ExecutionMode.LIVE
    elif mode.lower() == "paper":
        exec_mode = ExecutionMode.PAPER
    else:
        exec_mode = ExecutionMode.DRY_RUN

    # Load execution guards config
    guards_config = {}
    try:
        guards_path = Path("configs/execution_guards.json")
        if guards_path.exists():
            with open(guards_path, "r", encoding="utf-8") as f:
                guards_config = json.load(f) or {}
    except Exception as e:
        logging.getLogger(__name__).warning("execution_guards_config_load_failed", extra={"error": str(e)})

    return MT5Executor(mode=exec_mode, config=exec_cfg, guards_config=guards_config)


def try_init_mt5() -> Optional[object]:
    """Best-effort initialize MetaTrader5; return module or None on failure.

    This keeps the script usable even when MetaTrader5 is not installed or
    MT5 is not running. In that case we fall back to a pseudo-live CSV feed.
    """
    logger = logging.getLogger(__name__)
    try:
        import MetaTrader5 as mt5  # type: ignore

        if not mt5.initialize():
            logger.warning("mt5_init_failed", extra={"error": mt5.last_error()})
            return None
        logger.info("mt5_initialized")
        return mt5
    except Exception as e:
        logger.warning("mt5_import_or_init_failed", extra={"error": str(e)})
        return None


def fetch_historical_bars_mt5(mt5_mod, symbol: str, timeframe, num_bars: int = 100) -> List[Bar]:
    """Fetch historical bars for a symbol from MT5 to pre-populate the buffer.
    
    Returns up to num_bars of completed (closed) bars, excluding the current forming bar.
    """
    from datetime import timedelta as _td
    
    now = datetime.now(timezone.utc)
    # Request extra bars since the last one may be incomplete
    rates = mt5_mod.copy_rates_from(symbol, timeframe, now, num_bars + 1)
    if rates is None or len(rates) == 0:
        return []
    
    bars = []
    for rate in rates[:-1]:  # Exclude the last (current/forming) bar
        bar_time = datetime.fromtimestamp(rate["time"], tz=timezone.utc)
        # Only include bars that are fully closed (at least 15 min old for M15)
        if now - bar_time >= _td(minutes=15):
            try:
                tick_vol = rate["tick_volume"]
            except (KeyError, IndexError, ValueError, TypeError):
                tick_vol = 0
            bars.append(Bar(
                open=Decimal(str(rate["open"])),
                high=Decimal(str(rate["high"])),
                low=Decimal(str(rate["low"])),
                close=Decimal(str(rate["close"])),
                volume=Decimal(str(tick_vol)),
                timestamp=bar_time,
            ))
    return bars


def fetch_latest_bar_mt5(mt5_mod, symbol: str, timeframe, last_time: Optional[datetime]) -> Optional[Bar]:
    """Fetch the latest completed bar for a symbol from MT5.

    If last_time is provided, only return a bar if it is strictly newer.
    """
    from datetime import timedelta as _td

    # Request a few recent bars to be robust to off-by-one issues
    now = datetime.now(timezone.utc)
    rates = mt5_mod.copy_rates_from(symbol, timeframe, now, 3)
    if rates is None or len(rates) == 0:
        return None

    # MT5 typically returns the *current forming bar* as the last element.
    # Use the second-to-last element as the last fully closed bar when possible.
    if len(rates) >= 2:
        last_rate = rates[-2]
    else:
        last_rate = rates[-1]

    # MT5 returns a numpy.void with named fields like 'time', 'open', 'high', etc.
    # Access via indexing, not .get.
    bar_time = datetime.fromtimestamp(last_rate["time"], tz=timezone.utc)

    # Guard against partial current bar: require that bar is closed by checking
    # that its time is at least one timeframe earlier than 'now'. For M15 that
    # means >= 15 minutes ago.
    if now - bar_time < _td(minutes=15):
        return None

    if last_time is not None and bar_time <= last_time:
        return None

    # tick_volume is the standard MT5 volume field on rates; fall back to 0 if missing.
    try:
        tick_vol = last_rate["tick_volume"]
    except (KeyError, IndexError, ValueError, TypeError):
        tick_vol = 0

    return Bar(
        open=Decimal(str(last_rate["open"])),
        high=Decimal(str(last_rate["high"])),
        low=Decimal(str(last_rate["low"])),
        close=Decimal(str(last_rate["close"])),
        volume=Decimal(str(tick_vol)),
        timestamp=bar_time,
    )


def build_initial_series(symbol: str, num_bars: int, data_source: str) -> OHLCV:
    """Build an initial OHLCV series for pseudo-live fallback mode."""
    if data_source == "csv":
        return load_csv_data(csv_path="infra/data/eurusd_m15_clean.csv", symbol=symbol, num_bars=num_bars)
    return create_sample_data(num_bars=num_bars, symbol=symbol)


def run_live_loop(
    symbols: List[str],
    mode: str = "paper",
    poll_seconds: int = 10,
    max_bars_per_symbol: int = 2000,
) -> Dict[str, object]:
    """Main live/paper trading loop.

    - For LIVE/PAPER modes, attempts to stream bars from MT5.
    - If MT5 is unavailable, falls back to a pseudo-live replay from CSV/synthetic
      using the backtest helpers, while still exercising the full pipeline.
    """
    logger = logging.getLogger(__name__)

    print("\n" + "=" * 70)
    print("D.E.V.I 2.0 LIVE/PAPER MT5 LOOP")
    print("=" * 70)

    print("\n[1/4] Setting up logging...")
    log_file = setup_logging()
    print(f"      Logs: {log_file}")

    print("\n[2/4] Loading configuration...")
    config = create_live_config()
    print(f"      Config hash: {str(config.config_hash.hash_value)[:16]}...")
    data_source = config.system_configs.get("data_source", "UNKNOWN")
    print(f"      Data source: {data_source}")

    print("\n[3/4] Initializing executor and pipeline...")
    executor = init_executor(config, mode=mode)
    pipeline = TradingPipeline(config, executor=executor)
    print(f"      Pipeline ready (executor enabled: {pipeline.executor.enabled})")
    print(f"      Executor mode: {pipeline.executor.mode.value}")
    print(f"      Broker symbols registered: {sorted(pipeline.broker_symbols.keys())}")

    # Log a clear session start marker so live vs paper runs are easy to audit.
    system_risk = (config.system_configs or {}).get("risk", {}) or {}
    logging.getLogger(__name__).info(
        "live_session_start",
        extra={
            "executor_mode": pipeline.executor.mode.value,
            "symbols": symbols,
            "per_trade_pct": system_risk.get("per_trade_pct"),
            "per_symbol_open_risk_cap_pct": system_risk.get("per_symbol_open_risk_cap_pct"),
        },
    )

    use_mt5 = mode.lower() in {"paper", "live"}
    mt5_mod = try_init_mt5() if use_mt5 else None
    if use_mt5 and mt5_mod is None:
        print("      WARNING: MT5 unavailable, falling back to pseudo-live replay.")
        use_mt5 = False

    # Set up per-symbol bar buffers and last seen timestamps
    symbol_buffers: Dict[str, Deque[Bar]] = {}
    last_times: Dict[str, Optional[datetime]] = {sym: None for sym in symbols}

    if not use_mt5:
        # Build initial historical series for each symbol and start from the end
        for sym in symbols:
            series = build_initial_series(sym, num_bars=max_bars_per_symbol, data_source=data_source)
            # Use bars as a rolling deque to simulate new bars over time
            symbol_buffers[sym] = deque(series.bars, maxlen=max_bars_per_symbol)
            last_times[sym] = series.bars[-1].timestamp if series.bars else None
        print("      Pseudo-live mode: replaying CSV/synthetic data.")
    else:
        # Pre-load historical bars from MT5 so we can generate signals immediately
        print("      Loading historical bars from MT5...")
        for sym in symbols:
            hist_bars = fetch_historical_bars_mt5(mt5_mod, sym, mt5_mod.TIMEFRAME_M15, num_bars=100)
            if hist_bars:
                symbol_buffers[sym] = deque(hist_bars, maxlen=max_bars_per_symbol)
                last_times[sym] = hist_bars[-1].timestamp
                print(f"        {sym}: loaded {len(hist_bars)} historical bars")
            else:
                symbol_buffers[sym] = deque(maxlen=max_bars_per_symbol)
                print(f"        {sym}: no historical bars available")
        print("      MT5 streaming mode: polling for new completed bars.")

    print("\n[4/4] Entering main loop (Ctrl+C to stop)...")

    processed_counts: Dict[str, int] = {sym: 0 for sym in symbols}
    first_iteration = True  # Process pre-loaded bars on first iteration

    try:
        while True:
            loop_start = datetime.now(timezone.utc)

            try:
                for sym in symbols:
                    buf = symbol_buffers.get(sym)
                    last_time = last_times.get(sym)

                    if use_mt5:
                        if first_iteration and buf and len(buf) > 0:
                            # First iteration: process pre-loaded historical bars
                            pass  # buf already populated, skip fetch
                        else:
                            # MT5: fetch at most one new completed bar per poll
                            bar = fetch_latest_bar_mt5(mt5_mod, sym, mt5_mod.TIMEFRAME_M15, last_time)
                            if bar is None:
                                continue
                            if buf is None:
                                buf = deque(maxlen=max_bars_per_symbol)
                                symbol_buffers[sym] = buf
                            buf.append(bar)
                            last_times[sym] = bar.timestamp
                    else:
                        # Pseudo-live: rotate existing series by one bar per loop iteration
                        if buf is None or not buf:
                            continue
                        # Treat the rightmost bar as the latest and simply reuse the full series;
                        # for a more advanced replay, we could index through the series instead.
                        bar = buf[-1]

                    if not buf:
                        continue

                    ohlcv = OHLCV(symbol=sym, bars=tuple(buf), timeframe="15m")
                    timestamp = ohlcv.latest_bar.timestamp

                    decisions = pipeline.process_bar(ohlcv, timestamp)
                    processed_counts[sym] += 1

                # Simple progress heartbeat
                if any(processed_counts.values()):
                    print(
                        f"      Loop @ {loop_start.isoformat()} | "
                        + ", ".join(f"{s}: {c} bars" for s, c in processed_counts.items())
                    )

                # Reset first_iteration flag after processing
                first_iteration = False

                # Sleep until next poll
                from time import sleep

                sleep(max(poll_seconds, 1))

            except Exception as e:
                logger.exception("live_loop_error", extra={"error": str(e)})
                break

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt received, finalizing session...")
    finally:
        try:
            pipeline.finalize_session("LIVE_LOOP")
        except Exception:
            pass
        if use_mt5 and mt5_mod is not None:
            try:
                mt5_mod.shutdown()
            except Exception:
                pass

        stats = pipeline.get_pipeline_stats()
        print("\n" + "=" * 70)
        print("LIVE LOOP SUMMARY")
        print("=" * 70)
        print(f"  - Processed bars: {stats['processed_bars']}")
        print(f"  - Decisions generated: {stats['decisions_generated']}")
        print(f"  - Execution results: {stats['execution_results']}")
        print(f"  - Executor mode: {stats['executor_mode']}")
        print("\n" + "=" * 70)
        print(f"Log file: {log_file}")
        print("=" * 70 + "\n")

        return {
            "log_file": str(log_file),
            "processed_bars": stats["processed_bars"],
            "decisions_generated": stats["decisions_generated"],
            "execution_results": stats["execution_results"],
            "executor_mode": stats["executor_mode"],
        }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DEVI 2.0 live/paper MT5 loop")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["EURUSD", "XAUUSD", "AUDUSD", "AUDJPY", "USDJPY", "NVDA", "TSLA"],
        help="Symbols to stream (default: EURUSD XAUUSD AUDUSD AUDJPY USDJPY NVDA TSLA)",
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "paper", "live"],
        default="paper",
        help="Executor / MT5 mode (default: paper)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=10,
        help="Polling interval in seconds between MT5 bar checks (default: 10)",
    )
    parser.add_argument(
        "--max-bars-per-symbol",
        type=int,
        default=2000,
        help="Max bars to retain per symbol in memory (default: 2000)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    results = run_live_loop(
        symbols=args.symbols,
        mode=args.mode,
        poll_seconds=args.poll_seconds,
        max_bars_per_symbol=args.max_bars_per_symbol,
    )
    print("\nLive Loop Summary JSON:")
    print(json.dumps(results, indent=2))
