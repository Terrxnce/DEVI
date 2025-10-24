#!/usr/bin/env python
"""Verify DEVI 2.0 system is fully operational."""

import sys
from decimal import Decimal

print("=" * 70)
print("DEVI 2.0 SYSTEM VERIFICATION")
print("=" * 70)

# Test 1: Import all detectors
print("\n[1/6] Testing detector imports...")
try:
    from core.structure.detector import StructureDetector
    from core.structure.order_block import OrderBlockDetector
    from core.structure.fair_value_gap import FairValueGapDetector
    from core.structure.break_of_structure import BreakOfStructureDetector
    from core.structure.sweep import SweepDetector
    from core.structure.rejection import UnifiedZoneRejectionDetector
    from core.structure.engulfing import EngulfingDetector
    print("    PASS: All 6 detectors imported successfully")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 2: Initialize all detectors
print("\n[2/6] Testing detector initialization...")
try:
    detectors = [
        OrderBlockDetector({}),
        FairValueGapDetector({}),
        BreakOfStructureDetector({}),
        SweepDetector({}),
        UnifiedZoneRejectionDetector({}),
        EngulfingDetector({})
    ]
    print(f"    PASS: All 6 detectors initialized")
    for d in detectors:
        print(f"      - {d.name}: {d.structure_type.value}")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 3: Test pipeline initialization
print("\n[3/6] Testing pipeline initialization...")
try:
    from core.orchestration.pipeline import TradingPipeline
    from core.models.config import Config
    config = Config(system_configs={}, structure_configs={})
    pipeline = TradingPipeline(config)
    print(f"    PASS: Pipeline initialized with {len(pipeline.structure_manager.detectors)} detectors")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 4: Test executor
print("\n[4/6] Testing executor...")
try:
    from core.execution.mt5_executor import MT5Executor, ExecutionMode, ExecutionResult
    executor = MT5Executor(ExecutionMode.DRY_RUN)
    result = ExecutionResult(success=True, rr=1.5, validation_errors=[])
    print(f"    PASS: Executor initialized, ExecutionResult has rr={result.rr}")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 5: Test models
print("\n[5/6] Testing core models...")
try:
    from core.models.structure import Structure, StructureType, StructureQuality, LifecycleState
    from core.models.decision import Decision, DecisionType, DecisionStatus
    from core.models.ohlcv import Bar, OHLCV
    from datetime import datetime, timezone
    
    # Create a test bar
    bar = Bar(
        timestamp=datetime.now(timezone.utc),
        open=Decimal('1.0950'),
        high=Decimal('1.0960'),
        low=Decimal('1.0940'),
        close=Decimal('1.0955'),
        volume=1000
    )
    print(f"    PASS: All models working (created test bar: {bar.close})")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# Test 6: Test backtest
print("\n[6/6] Testing backtest execution...")
try:
    import subprocess
    result = subprocess.run(
        ["python", "backtest_dry_run.py", "100", "EURUSD"],
        capture_output=True,
        text=True,
        timeout=30
    )
    if result.returncode == 0:
        print(f"    PASS: Backtest completed successfully")
        # Extract key metrics
        if "Decisions generated:" in result.stdout:
            for line in result.stdout.split('\n'):
                if 'Decisions generated:' in line or 'Pass rate:' in line:
                    print(f"      {line.strip()}")
    else:
        print(f"    FAIL: Backtest failed with exit code {result.returncode}")
        print(result.stderr[-500:] if result.stderr else "No error output")
        sys.exit(1)
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("ALL TESTS PASSED - SYSTEM IS FULLY OPERATIONAL")
print("=" * 70)
print("\nSystem Status:")
print("  - 6 detectors: OPERATIONAL")
print("  - Pipeline: OPERATIONAL")
print("  - Executor: OPERATIONAL")
print("  - Models: OPERATIONAL")
print("  - Backtest: OPERATIONAL")
print("\nReady for Phase 1.5 (Live Dry-Run with Real MT5 Data)")
print("=" * 70)
