#!/usr/bin/env python3
"""
Pull MT5 History — Fetch and validate 1000-bar OHLCV data

Fetches historical data from MT5, validates quality, and caches for replay.
Used for Phase 1.5 MT5 integration testing and determinism verification.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging():
    """Setup logging to console and file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"pull_mt5_history_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    root_logger.addHandler(console_handler)
    
    return log_file


def validate_ohlcv(bars):
    """
    Validate OHLCV data quality.
    
    Args:
        bars: List of OHLCV dicts
    
    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    
    if not bars:
        errors.append("No bars provided")
        return False, errors
    
    # Check chronological order
    for i in range(1, len(bars)):
        if bars[i]["timestamp"] <= bars[i-1]["timestamp"]:
            errors.append(f"Bar {i}: timestamp not in chronological order")
    
    # Check OHLC relationships
    for i, bar in enumerate(bars):
        if bar["high"] < max(bar["open"], bar["close"]):
            errors.append(f"Bar {i}: high < max(open, close)")
        if bar["low"] > min(bar["open"], bar["close"]):
            errors.append(f"Bar {i}: low > min(open, close)")
        if bar["volume"] <= 0:
            errors.append(f"Bar {i}: volume <= 0")
    
    # Check for duplicates
    timestamps = [bar["timestamp"] for bar in bars]
    if len(timestamps) != len(set(timestamps)):
        errors.append("Duplicate timestamps detected")
    
    # Check for gaps (15-min intervals)
    from datetime import timedelta
    for i in range(1, len(bars)):
        ts1 = datetime.fromisoformat(bars[i-1]["timestamp"].replace("Z", "+00:00"))
        ts2 = datetime.fromisoformat(bars[i]["timestamp"].replace("Z", "+00:00"))
        expected_diff = timedelta(minutes=15)
        actual_diff = ts2 - ts1
        if actual_diff != expected_diff:
            errors.append(f"Bar {i}: gap detected (expected 15min, got {actual_diff})")
    
    return len(errors) == 0, errors


def pull_history(symbol, timeframe, count):
    """
    Pull historical data from MT5.
    
    Args:
        symbol: Symbol name (e.g., "EURUSD")
        timeframe: Timeframe (e.g., "M15")
        count: Number of bars to fetch
    
    Returns:
        List of OHLCV dicts or None
    """
    try:
        import MetaTrader5 as mt5
        
        # Initialize MT5
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return None
        
        # Map timeframe
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        
        if timeframe not in tf_map:
            logger.error(f"Unsupported timeframe: {timeframe}")
            return None
        
        # Subscribe to symbol
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Failed to subscribe to {symbol}")
            return None
        
        # Fetch bars
        logger.info(f"Fetching {count} {timeframe} bars for {symbol}...")
        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
        
        if rates is None or len(rates) == 0:
            logger.error(f"No data returned from MT5")
            return None
        
        # Convert to OHLCV dicts with UTC timestamps
        bars = []
        for rate in rates:
            # rate is a tuple: (time, open, high, low, close, tick_volume, spread, real_volume)
            broker_time = datetime.fromtimestamp(rate[0], tz=timezone.utc)
            
            bar = {
                "timestamp": broker_time.isoformat().replace("+00:00", "Z"),
                "open": float(rate[1]),
                "high": float(rate[2]),
                "low": float(rate[3]),
                "close": float(rate[4]),
                "volume": int(rate[6]),  # real_volume
            }
            bars.append(bar)
        
        logger.info(f"Fetched {len(bars)} bars")
        mt5.shutdown()
        return bars
    
    except ImportError:
        logger.error("MetaTrader5 module not installed")
        logger.info("Install with: pip install MetaTrader5")
        return None
    except Exception as e:
        logger.error(f"MT5 error: {str(e)}")
        return None


def save_history(symbol, timeframe, bars):
    """
    Save history to JSON file.
    
    Args:
        symbol: Symbol name
        timeframe: Timeframe
        bars: List of OHLCV dicts
    
    Returns:
        Path to saved file
    """
    data_dir = Path("data/history")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = data_dir / f"{symbol}_{timeframe}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    
    data = {
        "symbol": symbol,
        "timeframe": timeframe,
        "pulled_at": datetime.now(timezone.utc).isoformat() + "Z",
        "bar_count": len(bars),
        "first_bar": bars[0] if bars else None,
        "last_bar": bars[-1] if bars else None,
        "bars": bars,
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"History saved to {file_path}")
    return file_path


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("MT5 HISTORY PULL")
    print("="*70)
    
    # Setup logging
    log_file = setup_logging()
    logger.info(f"Logging to {log_file}")
    
    # Parse arguments
    symbol = "EURUSD"
    timeframe = "M15"
    count = 1000
    
    if len(sys.argv) > 1:
        symbol = sys.argv[1].upper()
    if len(sys.argv) > 2:
        timeframe = sys.argv[2].upper()
    if len(sys.argv) > 3:
        try:
            count = int(sys.argv[3])
        except ValueError:
            pass
    
    logger.info(f"Pulling {count} {timeframe} bars for {symbol}...")
    
    # Pull history
    bars = pull_history(symbol, timeframe, count)
    
    if not bars:
        logger.error("Failed to pull history")
        print("\nFAIL: Could not fetch data from MT5")
        return 1
    
    # Validate
    print(f"\nValidating {len(bars)} bars...")
    is_valid, errors = validate_ohlcv(bars)
    
    if errors:
        logger.warning(f"Validation errors found: {len(errors)}")
        for error in errors[:10]:  # Show first 10 errors
            logger.warning(f"  - {error}")
        if len(errors) > 10:
            logger.warning(f"  ... and {len(errors) - 10} more")
    
    if not is_valid:
        print(f"\nFAIL: Data validation failed ({len(errors)} errors)")
        return 1
    
    print(f"OK: All {len(bars)} bars validated")
    
    # Save history
    file_path = save_history(symbol, timeframe, bars)
    
    # Print summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Bars: {len(bars)}")
    print(f"First: {bars[0]['timestamp']} ({bars[0]['open']})")
    print(f"Last: {bars[-1]['timestamp']} ({bars[-1]['close']})")
    print(f"File: {file_path}")
    print(f"Status: OK")
    print("="*70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
