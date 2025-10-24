# DEVI 2.0 Full Rebuild — Priority Execution Order

**Status**: Ready to Execute
**Estimated Time**: 3-4 hours
**Source**: ARCHITECTURE_OVERVIEW.md + 58 supporting docs + existing code

---

## ✅ ALREADY COMPLETE (18 files)

```
✅ core/__init__.py
✅ core/models/__init__.py, ohlcv.py, structure.py, decision.py, session.py, config.py
✅ core/indicators/__init__.py, base.py, atr.py
✅ core/structure/__init__.py, engulfing.py, manager.py, sweep.py
✅ core/execution/__init__.py, mt5_executor.py
✅ core/orchestration/__init__.py, pipeline.py
```

---

## 🔴 CRITICAL MISSING (Must Build First)

### Priority 1: Base Detector (Foundation for all 6)
**File**: `core/structure/detector.py` (~150 lines)
- Abstract base class `StructureDetector`
- `detect()` method signature
- `_validate_parameters()` hook
- Lifecycle management (UNFILLED → PARTIAL → FILLED → EXPIRED)
- Quality scoring framework
- Deterministic ID generation (SHA256)

**Key Pattern**:
```python
class StructureDetector(ABC):
    def __init__(self, name, structure_type, parameters):
        self.name = name
        self.structure_type = structure_type
        self.parameters = parameters
        self._validate_parameters()  # Subclass can override
    
    @abstractmethod
    def detect(self, data: OHLCV, session_id: str) -> List[Structure]:
        pass
    
    def _validate_parameters(self):
        pass  # Subclasses override to validate self attributes
```

---

### Priority 2: 5 Missing Detectors (Build in order)

**1. OrderBlockDetector** (`core/structure/order_block.py`) — 450 lines
- Displacement-based OB detection
- Mid-band mitigation logic
- Quality scoring (body dominance, displacement, break excess, wick cleanliness)
- Config: `order_block` section in structure.json

**2. FairValueGapDetector** (`core/structure/fair_value_gap.py`) — 400 lines
- Gap detection (3-bar pattern)
- ATR normalization (min_gap_atr_multiplier)
- Quality thresholds (premium/high/medium/low)
- Config: `fair_value_gap` section

**3. BreakOfStructureDetector** (`core/structure/break_of_structure.py`) — 350 lines
- Pivot-based BOS detection
- Close confirmation logic
- Debounce (prevent rapid re-detection)
- Config: `break_of_structure` section

**4. UnifiedZoneRejectionDetector** (`core/structure/rejection.py`) — 600 lines
- Touch detection (zone boundary ± ATR buffer)
- Reaction body validation
- Follow-through confirmation (lookahead_bars)
- Quality scoring (reaction body, follow-through, penetration, context)
- Config: `unified_zone_rejection` section

**5. Already Exists**:
- ✅ SweepDetector (sweep.py)
- ✅ EngulfingDetector (engulfing.py)

---

### Priority 3: CompositeScorer (Orchestration)
**File**: `core/orchestration/scoring.py` (~200 lines)
- `CompositeScorer` class
- 4 components (structure_quality, uzr_strength, ema_alignment, zone_proximity)
- Weighted formula: 0.40 + 0.25 + 0.20 + 0.15 = 1.0
- Per-session thresholds (ASIA, LONDON, NY_AM, NY_PM)
- Gate logic (composite_score >= min_composite)

**Key Formula**:
```python
composite = (0.40 * structure_quality +
             0.25 * uzr_strength +
             0.20 * ema_alignment +
             0.15 * zone_proximity)
```

---

### Priority 4: Missing Indicators (Optional, can use defaults)
**Files**: 
- `core/indicators/moving_averages.py` (~120 lines) — EMA 21, 50, 200
- `core/indicators/volatility.py` (~100 lines) — Volatility analysis
- `core/indicators/momentum.py` (~100 lines) — Momentum indicators

---

### Priority 5: Session Management (Optional, can use defaults)
**Files**:
- `core/sessions/__init__.py`
- `core/sessions/manager.py` (~150 lines)
- `core/sessions/rotator.py` (~100 lines)

---

## 🚀 EXECUTION PLAN

### Step 1: Create Base Detector (30 min)
```bash
# Create core/structure/detector.py
# Reference: ARCHITECTURE_OVERVIEW.md (Pipeline Stages section)
# Key: Abstract base with _validate_parameters() hook
```

### Step 2: Create 5 Detectors (2 hours)
```bash
# OrderBlockDetector (30 min)
# Reference: configs/structure.json [order_block] section
# Key: Set attributes BEFORE super().__init__()

# FairValueGapDetector (30 min)
# Reference: configs/structure.json [fair_value_gap] section

# BreakOfStructureDetector (20 min)
# Reference: configs/structure.json [break_of_structure] section

# UnifiedZoneRejectionDetector (30 min)
# Reference: configs/structure.json [unified_zone_rejection] section

# Verify Sweep & Engulfing already exist ✅
```

### Step 3: Create CompositeScorer (30 min)
```bash
# Create core/orchestration/scoring.py
# Reference: COMPOSITE_SCORER_SUMMARY.md
# Key: 4 components, weighted formula, per-session scales
```

### Step 4: Test (30 min)
```bash
python backtest_dry_run.py 300 EURUSD
# Expected: 0 errors, all 6 detectors firing, composite scoring active
```

---

## 📋 DETECTOR INIT PATTERN (CRITICAL!)

**WRONG** ❌:
```python
class MyDetector(StructureDetector):
    def __init__(self, params):
        super().__init__('MyDetector', StructureType.MY_TYPE, params)
        self.min_body_atr = params['min_body_atr']  # ❌ Too late!
```

**CORRECT** ✅:
```python
class MyDetector(StructureDetector):
    def __init__(self, params):
        # Set attributes FIRST
        self.min_body_atr = params.get('min_body_atr', 0.6)
        self.max_age_bars = params.get('max_age_bars', 180)
        
        # Then call super().__init__()
        super().__init__('MyDetector', StructureType.MY_TYPE, params)
```

**Why**: Base class calls `_validate_parameters()` in `__init__()`, which needs subclass attributes to exist.

---

## 🔍 REFERENCE DOCS

| Document | Purpose |
|----------|---------|
| ARCHITECTURE_OVERVIEW.md | Full system blueprint (10 stages, all modules) |
| IMPLEMENTATION_ROADMAP.md | File specs & line counts |
| DEEP_DIVE_DETECTOR_INITIALIZATION.md | Detector patterns & fixes |
| ENGULFING_DETECTOR_SUMMARY.md | Engulfing implementation |
| COMPOSITE_SCORER_SUMMARY.md | Scoring logic |
| configs/structure.json | All detector parameters |

---

## ✅ SUCCESS CRITERIA

After rebuild:
- [ ] All 18 existing files still present
- [ ] 5 new detector files created
- [ ] 1 new CompositeScorer file created
- [ ] backtest_dry_run.py runs without errors
- [ ] All 6 detectors initialized
- [ ] Composite scoring active
- [ ] 0 import errors
- [ ] Ready for Phase 1.5 (real MT5 data)

---

## 🎯 NEXT STEPS AFTER REBUILD

1. Run `python backtest_dry_run.py 300 EURUSD`
2. Verify 0 errors
3. Check detector summary (all 6 present)
4. Validate decision generation
5. Push to GitHub
6. Start Phase 1.5 (real MT5 feed)

---

## 📊 ESTIMATED COMPLETION

| Task | Time | Status |
|------|------|--------|
| Base Detector | 30 min | ⏳ Pending |
| 5 Detectors | 2 hours | ⏳ Pending |
| CompositeScorer | 30 min | ⏳ Pending |
| Testing | 30 min | ⏳ Pending |
| **Total** | **3.5 hours** | ⏳ Ready to Start |

---

**Ready to build?** Start with `core/structure/detector.py` (base class)
