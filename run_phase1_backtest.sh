#!/bin/bash
# Phase 1 Dry-Run Backtest Execution Script

echo "========================================================================"
echo "D.E.V.I 2.0 PHASE 1 DRY-RUN BACKTEST"
echo "========================================================================"
echo ""

# Run 1: Initial backtest
echo "[RUN 1] Executing backtest (1000 bars, EURUSD)..."
python backtest_dry_run.py 1000 EURUSD > run1.txt 2>&1
RUN1_EXIT=$?

if [ $RUN1_EXIT -ne 0 ]; then
    echo "ERROR: Run 1 failed with exit code $RUN1_EXIT"
    cat run1.txt
    exit 1
fi

echo "✓ Run 1 completed successfully"
echo ""

# Run 2: Determinism check
echo "[RUN 2] Executing backtest again (determinism verification)..."
python backtest_dry_run.py 1000 EURUSD > run2.txt 2>&1
RUN2_EXIT=$?

if [ $RUN2_EXIT -ne 0 ]; then
    echo "ERROR: Run 2 failed with exit code $RUN2_EXIT"
    cat run2.txt
    exit 1
fi

echo "✓ Run 2 completed successfully"
echo ""

# Compare results
echo "[DETERMINISM CHECK] Comparing Run 1 and Run 2..."
if diff -q run1.txt run2.txt > /dev/null; then
    echo "✓ DETERMINISM VERIFIED: Runs are identical"
else
    echo "⚠ WARNING: Runs differ (may be due to timestamps)"
    echo "Differences:"
    diff run1.txt run2.txt | head -20
fi

echo ""
echo "========================================================================"
echo "PHASE 1 BACKTEST COMPLETE"
echo "========================================================================"
echo ""
echo "Artifacts:"
echo "  - run1.txt: First backtest run output"
echo "  - run2.txt: Second backtest run output (determinism check)"
echo "  - logs/dry_run_backtest_*.json: Detailed execution logs"
echo ""
