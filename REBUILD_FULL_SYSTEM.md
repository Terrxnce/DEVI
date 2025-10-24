# DEVI 2.0 Full System Rebuild — Master Plan

**Date**: Oct 24, 2025
**Status**: Ready to Execute
**Source**: ARCHITECTURE_OVERVIEW.md + 58 supporting docs
**Estimated Time**: 2-3 hours

---

## Phase 1: Core Models (CRITICAL PATH)

### Files to Create (In Order)
1. `core/models/__init__.py` — Empty init
2. `core/models/ohlcv.py` — Bar, OHLCV classes (~150 lines)
3. `core/models/structure.py` — Structure, StructureType, StructureQuality, LifecycleState (~260 lines)
4. `core/models/decision.py` — Decision, DecisionType, DecisionStatus (~172 lines)
5. `core/models/session.py` — Session, SessionType, SessionRotator (~100 lines)
6. `core/models/config.py` — Config, ConfigHash (~100 lines)

### Key Patterns
- All prices/distances use `Decimal` for precision
- All timestamps use `datetime` with UTC
- Frozen dataclasses for immutability
- Deterministic IDs using SHA256

---

## Phase 2: Indicators

### Files to Create
1. `core/indicators/__init__.py` — Empty init
2. `core/indicators/base.py` — BaseIndicator, RollingIndicator (~80 lines)
3. `core/indicators/atr.py` — ATRCalculator, compute_atr_simple (~100 lines)
4. `core/indicators/moving_averages.py` — MovingAverageCalculator (~120 lines)
5. `core/indicators/volatility.py` — VolatilityCalculator (~100 lines)
6. `core/indicators/momentum.py` — MomentumCalculator (~100 lines)

### Key Pattern
- All indicators return Decimal values
- Support rolling window calculations
- ATR uses Wilder's smoothing (14-period default)

---

## Phase 3: Detectors (COMPLEX)

### Base Detector
1. `core/structure/__init__.py` — Empty init
2. `core/structure/detector.py` — StructureDetector base class (~150 lines)

### 6 Detectors (Follow DEEP_DIVE_DETECTOR_INITIALIZATION.md pattern)
3. `core/structure/order_block.py` — OrderBlockDetector (~450 lines)
4. `core/structure/fair_value_gap.py` — FairValueGapDetector (~400 lines)
5. `core/structure/break_of_structure.py` — BreakOfStructureDetector (~350 lines)
6. `core/structure/sweep.py` — SweepDetector (~400 lines)
7. `core/structure/rejection.py` — UnifiedZoneRejectionDetector (~600 lines)
8. `core/structure/engulfing.py` — EngulfingDetector (~600 lines)

### Manager
9. `core/structure/manager.py` — StructureManager (~100 lines)

### CRITICAL: Detector Init Pattern
```python
class MyDetector(StructureDetector):
    def __init__(self, parameters):
        params = parameters or {}
        params.setdefault('key1', value1)
        
        # SET ATTRIBUTES FIRST (before super().__init__())
        self.key1 = params['key1']
        self.key2 = params['key2']
        
        # THEN call super().__init__()
        super().__init__('MyDetector', StructureType.MY_TYPE, params)
```

---

## Phase 4: Orchestration

### Files to Create
1. `core/orchestration/__init__.py` — Empty init
2. `core/orchestration/pipeline.py` — TradingPipeline (10 stages, ~400 lines)
3. `core/orchestration/scoring.py` — CompositeScorer (~200 lines)

### Pipeline Stages
1. Session Gate
2. Pre-Filters
3. Indicators
4. Structure Detection
5. Scoring
6. UZR (Unified Zone Rejection)
7. Guards
8. SL/TP Planning
9. Decision Generation
10. Execution

---

## Phase 5: Execution & Sessions

### Files to Create
1. `core/execution/__init__.py` — Empty init
2. `core/execution/mt5_executor.py` — MT5Executor (~400 lines)
3. `core/sessions/__init__.py` — Empty init
4. `core/sessions/manager.py` — SessionManager (~150 lines)
5. `core/sessions/rotator.py` — SessionRotator (~100 lines)

---

## Configuration

### Already Exists
- `configs/structure.json` — All detector parameters + scoring weights
- `configs/system.json` — Execution config

### Verify
- All 6 detector configs present
- Scoring weights sum to 1.0
- Per-session thresholds (ASIA, LONDON, NY_AM, NY_PM)

---

## Testing

### Smoke Tests
1. All imports work
2. Config loads without errors
3. All detectors initialize
4. backtest_dry_run.py runs successfully

### Expected Output
- 300 bars processed
- 0+ decisions generated (depends on data)
- 0 errors
- Dry-run mode active

---

## Key Files to Reference

- `ARCHITECTURE_OVERVIEW.md` — Full system blueprint
- `IMPLEMENTATION_ROADMAP.md` — File specs & line counts
- `DEEP_DIVE_DETECTOR_INITIALIZATION.md` — Detector patterns
- `ENGULFING_DETECTOR_SUMMARY.md` — Engulfing implementation
- `COMPOSITE_SCORER_SUMMARY.md` — Scoring logic
- `configs/structure.json` — All parameters

---

## Success Criteria

✅ All files created
✅ No import errors
✅ backtest_dry_run.py runs without crashes
✅ All 6 detectors initialized
✅ Composite scoring active
✅ Execution layer wired
✅ Ready for Phase 1.5 (real MT5 data)

---

## Next Steps After Rebuild

1. Run `python backtest_dry_run.py 300 EURUSD`
2. Verify 0 errors
3. Check detector summary (all 6 present)
4. Validate decision generation
5. Push to GitHub
6. Start Phase 1.5 (real MT5 feed)
