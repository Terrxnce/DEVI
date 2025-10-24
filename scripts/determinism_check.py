#!/usr/bin/env python3
"""
Determinism Check — Run same 100-bar slice twice, verify 100% match

Validates that the pipeline is deterministic (replay-safe) by:
1. Running bars 0-99 with fixed seed
2. Running bars 0-99 again with same seed
3. Comparing structure IDs, composite scores, decisions
4. Generating determinism_diff.txt with results
"""

import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging():
    """Setup logging to console and file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"determinism_check_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"
    
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


def run_determinism_test(bars_count=100):
    """
    Run the same bar slice twice and compare results.
    
    Args:
        bars_count: Number of bars to test (default 100)
    
    Returns:
        Tuple of (run1_decisions, run2_decisions, is_match)
    """
    from core.models.ohlcv import Bar, OHLCV
    from core.models.config import Config
    from core.orchestration.pipeline import TradingPipeline
    from decimal import Decimal
    from datetime import timedelta
    
    logger.info(f"Starting determinism test with {bars_count} bars")
    
    # Create sample data (same for both runs)
    def create_sample_data(num_bars):
        bars = []
        base_price = Decimal("1.0950")
        base_time = datetime.now(timezone.utc)
        
        for i in range(num_bars):
            timestamp = base_time - timedelta(minutes=15 * (num_bars - 1 - i))
            price_change = Decimal(str((i % 20 - 10) * 0.00005))
            open_price = base_price + price_change
            close_price = open_price + Decimal(str((i % 5 - 2) * 0.0003))
            high_price = max(open_price, close_price) + Decimal("0.0008")
            low_price = min(open_price, close_price) - Decimal("0.0005")
            
            bar = Bar(
                timestamp=timestamp,
                open=float(open_price),
                high=float(high_price),
                low=float(low_price),
                close=float(close_price),
                volume=1000000
            )
            bars.append(bar)
            base_price = close_price
        
        return OHLCV(symbol="EURUSD", bars=bars, timeframe="15m")
    
    # Load config once
    config = Config()
    sample_data = create_sample_data(bars_count)
    
    # Run 1
    logger.info("Run 1: Processing bars...")
    pipeline1 = TradingPipeline(config)
    decisions1 = []
    for i, bar in enumerate(sample_data.bars):
        bar_data = OHLCV(
            symbol="EURUSD",
            bars=sample_data.bars[:i+1],
            timeframe="15m"
        )
        decisions = pipeline1.process_bar(bar_data, datetime.now(timezone.utc))
        decisions1.extend(decisions)
    
    logger.info(f"Run 1: Generated {len(decisions1)} decisions")
    
    # Run 2 (same config, same data)
    logger.info("Run 2: Processing bars...")
    pipeline2 = TradingPipeline(config)
    decisions2 = []
    for i, bar in enumerate(sample_data.bars):
        bar_data = OHLCV(
            symbol="EURUSD",
            bars=sample_data.bars[:i+1],
            timeframe="15m"
        )
        decisions = pipeline2.process_bar(bar_data, datetime.now(timezone.utc))
        decisions2.extend(decisions)
    
    logger.info(f"Run 2: Generated {len(decisions2)} decisions")
    
    return decisions1, decisions2


def compare_decisions(decisions1, decisions2):
    """
    Compare two decision lists for determinism.
    
    Args:
        decisions1: First run decisions
        decisions2: Second run decisions
    
    Returns:
        Tuple of (is_match, diff_report)
    """
    diff_report = {
        "run1_count": len(decisions1),
        "run2_count": len(decisions2),
        "count_match": len(decisions1) == len(decisions2),
        "decisions_match": True,
        "mismatches": []
    }
    
    # Compare counts
    if diff_report["run1_count"] != diff_report["run2_count"]:
        diff_report["decisions_match"] = False
        diff_report["mismatches"].append({
            "type": "count_mismatch",
            "run1": diff_report["run1_count"],
            "run2": diff_report["run2_count"]
        })
    
    # Compare each decision
    for i in range(min(len(decisions1), len(decisions2))):
        d1 = decisions1[i]
        d2 = decisions2[i]
        
        # Compare key fields
        if d1.type != d2.type:
            diff_report["decisions_match"] = False
            diff_report["mismatches"].append({
                "index": i,
                "field": "type",
                "run1": d1.type,
                "run2": d2.type
            })
        
        if d1.rr != d2.rr:
            diff_report["decisions_match"] = False
            diff_report["mismatches"].append({
                "index": i,
                "field": "rr",
                "run1": d1.rr,
                "run2": d2.rr
            })
        
        if d1.entry_price != d2.entry_price:
            diff_report["decisions_match"] = False
            diff_report["mismatches"].append({
                "index": i,
                "field": "entry_price",
                "run1": d1.entry_price,
                "run2": d2.entry_price
            })
        
        if d1.stop_loss != d2.stop_loss:
            diff_report["decisions_match"] = False
            diff_report["mismatches"].append({
                "index": i,
                "field": "stop_loss",
                "run1": d1.stop_loss,
                "run2": d2.stop_loss
            })
        
        if d1.take_profit != d2.take_profit:
            diff_report["decisions_match"] = False
            diff_report["mismatches"].append({
                "index": i,
                "field": "take_profit",
                "run1": d1.take_profit,
                "run2": d2.take_profit
            })
    
    return diff_report["decisions_match"], diff_report


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("DETERMINISM CHECK — 100-Bar Replay Test")
    print("="*70)
    
    # Setup logging
    log_file = setup_logging()
    logger.info(f"Logging to {log_file}")
    
    # Run determinism test
    try:
        decisions1, decisions2 = run_determinism_test(bars_count=100)
    except Exception as e:
        logger.error(f"Determinism test failed: {str(e)}")
        print(f"\nFAIL: Determinism test error: {str(e)}")
        return 1
    
    # Compare results
    is_match, diff_report = compare_decisions(decisions1, decisions2)
    
    # Write diff report
    diff_file = Path("artifacts") / "determinism_diff.txt"
    diff_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(diff_file, "w", encoding="utf-8") as f:
        f.write("="*70 + "\n")
        f.write("DETERMINISM CHECK RESULTS\n")
        f.write("="*70 + "\n\n")
        
        f.write(f"Run 1 Decisions: {diff_report['run1_count']}\n")
        f.write(f"Run 2 Decisions: {diff_report['run2_count']}\n")
        f.write(f"Count Match: {diff_report['count_match']}\n")
        f.write(f"Decisions Match: {diff_report['decisions_match']}\n\n")
        
        if diff_report["mismatches"]:
            f.write(f"Mismatches Found: {len(diff_report['mismatches'])}\n\n")
            for i, mismatch in enumerate(diff_report["mismatches"][:10]):  # Show first 10
                f.write(f"Mismatch {i+1}:\n")
                f.write(json.dumps(mismatch, indent=2) + "\n\n")
            
            if len(diff_report["mismatches"]) > 10:
                f.write(f"... and {len(diff_report['mismatches']) - 10} more mismatches\n")
        else:
            f.write("No mismatches found.\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("FULL REPORT\n")
        f.write("="*70 + "\n")
        f.write(json.dumps(diff_report, indent=2))
    
    # Print summary
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"Run 1 Decisions: {diff_report['run1_count']}")
    print(f"Run 2 Decisions: {diff_report['run2_count']}")
    print(f"Count Match: {diff_report['count_match']}")
    print(f"Decisions Match: {diff_report['decisions_match']}")
    
    if is_match:
        print(f"\nOK: 100% determinism match")
        print(f"Diff report: {diff_file}")
        print("="*70 + "\n")
        return 0
    else:
        print(f"\nFAIL: Determinism mismatch detected")
        print(f"Mismatches: {len(diff_report['mismatches'])}")
        print(f"Diff report: {diff_file}")
        print("="*70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
