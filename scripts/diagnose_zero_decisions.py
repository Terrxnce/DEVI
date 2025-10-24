#!/usr/bin/env python3
"""
Diagnose why pipeline is generating 0 decisions.

Checks:
1. Are structures being detected?
2. Is composite gate passing?
3. Are SL/TP calculations working?
4. Are decisions being generated?
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal

def diagnose():
    """Run diagnostic checks."""
    print("\n" + "="*70)
    print("PIPELINE DIAGNOSTIC — Zero Decisions Issue")
    print("="*70 + "\n")
    
    # Import pipeline components
    try:
        from core.models.ohlcv import Bar, OHLCV
        from core.models.config import Config
        from core.orchestration.pipeline import TradingPipeline
        print("✅ Imports successful")
    except Exception as e:
        print(f"❌ Import error: {e}")
        return 1
    
    # Create sample data
    print("\n[1/5] Creating sample data...")
    try:
        bars = []
        base_price = Decimal("1.0950")
        base_time = datetime.now(timezone.utc)
        
        for i in range(100):
            timestamp = base_time - timedelta(minutes=15 * (100 - 1 - i))
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
        
        sample_data = OHLCV(symbol="EURUSD", bars=bars, timeframe="15m")
        print(f"✅ Generated {len(bars)} bars")
    except Exception as e:
        print(f"❌ Data generation error: {e}")
        return 1
    
    # Load config
    print("\n[2/5] Loading configuration...")
    try:
        config = Config()
        print("✅ Config loaded")
        
        # Check composite scorer config
        scoring_config = config.system_configs.get("scoring", {})
        if scoring_config:
            print(f"   Scoring config found: {list(scoring_config.keys())}")
            scales = scoring_config.get("scales", {})
            if scales:
                print(f"   Scales: {list(scales.keys())}")
        else:
            print("   ⚠️  No scoring config found")
    except Exception as e:
        print(f"❌ Config error: {e}")
        return 1
    
    # Initialize pipeline
    print("\n[3/5] Initializing pipeline...")
    try:
        pipeline = TradingPipeline(config)
        print("✅ Pipeline initialized")
    except Exception as e:
        print(f"❌ Pipeline init error: {e}")
        return 1
    
    # Process bars and collect diagnostics
    print("\n[4/5] Processing bars...")
    decisions = []
    structures_detected = 0
    gates_passed = 0
    gates_failed = 0
    
    try:
        for i, bar in enumerate(sample_data.bars):
            bar_data = OHLCV(
                symbol="EURUSD",
                bars=sample_data.bars[:i+1],
                timeframe="15m"
            )
            
            # Process bar
            bar_decisions = pipeline.process_bar(bar_data, datetime.now(timezone.utc))
            decisions.extend(bar_decisions)
            
            # Print progress every 20 bars
            if (i + 1) % 20 == 0:
                print(f"   Bar {i+1}/100: {len(decisions)} decisions so far")
        
        print(f"✅ Processed {len(sample_data.bars)} bars")
    except Exception as e:
        print(f"❌ Processing error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Summary
    print("\n[5/5] Diagnostic Summary")
    print("="*70)
    print(f"Total decisions generated: {len(decisions)}")
    
    if len(decisions) == 0:
        print("\n❌ ISSUE: Zero decisions generated")
        print("\nPossible causes:")
        print("  1. Composite gate threshold too high (check min_composite in config)")
        print("  2. No structures detected (check detectors)")
        print("  3. SL/TP planning failing (check RR calculation)")
        print("  4. Guards filtering all bars (check session/ATR guards)")
        print("\nRecommendations:")
        print("  1. Lower min_composite threshold by 0.05-0.10")
        print("  2. Check structure.json for detector parameters")
        print("  3. Enable debug logging in pipeline.py")
        print("  4. Run with smaller dataset (10 bars) for manual inspection")
    else:
        print(f"\n✅ SUCCESS: {len(decisions)} decisions generated")
        print(f"   Pass-rate: {len(decisions) / len(sample_data.bars) * 100:.1f}%")
        
        if len(decisions) > 0:
            print(f"\n   First decision:")
            d = decisions[0]
            print(f"     Type: {getattr(d, 'type', 'N/A')}")
            print(f"     Entry: {getattr(d, 'entry_price', 'N/A')}")
            print(f"     SL: {getattr(d, 'stop_loss', 'N/A')}")
            print(f"     TP: {getattr(d, 'take_profit', 'N/A')}")
            print(f"     RR: {getattr(d, 'rr', 'N/A')}")
    
    print("\n" + "="*70 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(diagnose())
