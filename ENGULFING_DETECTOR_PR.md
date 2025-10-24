# PR: Engulfing Detector Implementation

## Summary

This PR implements the **Engulfing Detector** — a context-gated, ATR-normalized detector for high-quality real-body engulfing patterns. The detector follows all D.E.V.I 2.0 conventions: canonical Structure objects, lifecycle management, deterministic IDs, structured JSON logging, and comprehensive unit tests.

## Changes

### 1. Core Implementation (`core/structure/engulfing.py`)

**EngulfingDetector** class extending `StructureDetector` with:

#### Detection Logic
- **Bullish Engulfing**: Previous bar bearish, current bar bullish, bodies engulf (strict, wick-agnostic)
- **Bearish Engulfing**: Previous bar bullish, current bar bearish, bodies engulf
- **ATR-Scaled Strength Filters**:
  - `body_atr = abs(close - open) / ATR >= min_body_atr` (default: 0.6)
  - `body_to_range = body / range >= min_body_to_range` (default: 0.55)
  - Optional `min_close_shift_atr` for displacement check

#### Context Gating (Optional)
- **EMA Trend Alignment** (`ema_confirm=True`):
  - Bullish: EMA_21 > EMA_50, price >= EMA_21
  - Bearish: EMA_21 < EMA_50, price <= EMA_21
  - Configurable slope minimum

- **Zone Proximity** (`zone_context=True`):
  - Detects OB/FVG within `max_zone_distance_atr * ATR` (default: 0.5)
  - Awards zone bonus (0.05) if found
  - Optional hard requirement (`zone_touch_required=False`)
  - Band padding by `zone_padding_atr * ATR` (default: 0.1)

- **BOS Direction Alignment** (`bos_align=True`):
  - Engulfing direction must align with latest BOS direction
  - Optional gate or bonus

#### Lifecycle Management
- **UNFILLED** (on detection)
- **FOLLOWED_THROUGH** (within `lookahead_bars`, price moves `follow_through_atr * ATR` in engulf direction)
- **EXPIRED** (no follow-through within window)
- Structured JSON logs for all transitions

#### Quality Scoring (0-1)
Weighted components:
```
Q = w_body * S_body +
    w_ratio * S_body_to_range +
    w_ft * S_follow_through +
    w_ctx * S_context

Where:
- S_body = clamp(body_atr / 2.0, 0, 1)
- S_body_to_range = clamp((ratio - 0.5) / 0.25, 0, 1)
- S_follow_through = clamp(follow_atr / 2.0, 0, 1)
- S_context = clamp(ema_bonus + bos_bonus + zone_bonus, 0, 1)
```

Default weights (sum = 1.0):
- body: 0.35
- body_to_range: 0.25
- follow_through: 0.25
- context: 0.15

Quality levels:
- PREMIUM: score >= 0.8
- HIGH: score >= 0.65
- MEDIUM: score >= 0.45
- LOW: score < 0.45

#### Debounce & Dedupe
- **Debounce**: Per (symbol, timeframe, direction), require `debounce_bars` (default: 3) between signals
- **Dedupe**: Group by direction, keep highest quality_score

#### Zone Geometry
```
low = min(open, close)
high = max(open, close)
mid = (low + high) / 2
```
Optional band expansion by `zone_padding_atr * ATR` on both sides.

#### Structured Logging
**Detection Event**:
```json
{
  "event": "engulfing_detected",
  "run_id": "session_123",
  "symbol": "EURUSD",
  "timeframe": "15m",
  "detector": "EngulfingDetector",
  "event_id": "structure_id",
  "direction": "bullish",
  "origin_index": 873,
  "atr_at_creation": 0.00042,
  "body_atr": 1.35,
  "body_to_range": 0.72,
  "ema_ok": true,
  "zone_linked": true,
  "quality_score": 0.78,
  "quality": "HIGH",
  "lifecycle": "unfilled"
}
```

**Lifecycle Transition Event**:
```json
{
  "event": "engulfing_lifecycle_transition",
  "run_id": "session_123",
  "symbol": "EURUSD",
  "timeframe": "15m",
  "detector": "EngulfingDetector",
  "event_id": "structure_id",
  "direction": "bullish",
  "origin_index": 873,
  "from": "unfilled",
  "to": "filled",
  "reason": "follow_through",
  "quality_score": 0.78
}
```

### 2. Configuration (`configs/structure.json`)

Added `engulfing` section with all parameters:

```json
{
  "engulfing": {
    "enabled": true,
    "atr_window": 14,
    "min_body_atr": 0.6,
    "min_body_to_range": 0.55,
    "min_close_shift_atr": 0.0,
    "ema_confirm": true,
    "ema_slope_min": 0.0,
    "ema_pairs": [21, 50, 200],
    "zone_context": true,
    "zone_touch_required": false,
    "max_zone_distance_atr": 0.5,
    "pad_band_with_atr": true,
    "zone_padding_atr": 0.1,
    "bos_align": true,
    "lookahead_bars": 5,
    "follow_through_atr": 0.8,
    "debounce_bars": 3,
    "weights": {
      "body": 0.35,
      "body_to_range": 0.25,
      "follow_through": 0.25,
      "context": 0.15
    },
    "quality_thresholds": {
      "premium": 0.8,
      "high": 0.65,
      "medium": 0.45,
      "low": 0.25
    }
  }
}
```

Also updated `max_structures` to include `engulfings: 5`.

### 3. Pipeline Integration (`core/structure/manager.py`)

- Added `EngulfingDetector` import
- Initialized detector in `_initialize_detectors()` with config-driven flag (`enable_engulfing`, default: True)
- Detector runs alongside other detectors in structure detection pipeline
- Structures ranked and limited by existing quality scorer

### 4. Comprehensive Unit Tests (`tests/unit/test_engulfing_detector.py`)

**Positive Tests**:
- ✅ Detect bullish engulfing with ATR scaling satisfied
- ✅ Quality score in valid range (0-1)
- ✅ Metadata populated (atr_at_creation, body_atr, body_to_range, detector)

**Negative Tests**:
- ✅ Reject bodies below min_body_atr threshold
- ✅ Disabled detector returns empty list
- ✅ Invalid parameters raise errors

**Edge Cases**:
- ✅ Insufficient data raises error
- ✅ Zero ATR bars skipped
- ✅ Debounce prevents double signals on same direction
- ✅ Parameter validation (min_body_atr, body_to_range, lookahead_bars, weights)

**Determinism**:
- ✅ Identical runs produce identical structure IDs
- ✅ Identical runs produce identical quality scores

**Info & Metadata**:
- ✅ get_info() returns valid dictionary
- ✅ Detector name and structure type correct

## Acceptance Criteria

✅ **Core Detection**: Bullish/bearish engulfing detection with ATR-scaled thresholds  
✅ **Context Gating**: EMA trend, BOS alignment, zone proximity (all optional)  
✅ **Lifecycle**: UNFILLED → FOLLOWED_THROUGH → EXPIRED with structured logs  
✅ **Quality Scoring**: Weighted components (body, ratio, follow-through, context)  
✅ **Debounce & Dedupe**: Prevents double signals; keeps higher quality  
✅ **Deterministic IDs**: Replay-safe, identical across runs  
✅ **Structured Logging**: JSON events only (no prints)  
✅ **Configuration**: All parameters in structure.json with validation  
✅ **Pipeline Integration**: Wired into StructureManager, runs with other detectors  
✅ **Comprehensive Tests**: Positive, negative, edge cases, determinism verified  

## Testing

Run engulfing detector tests:
```bash
python -m pytest tests/unit/test_engulfing_detector.py -v
```

Run all structure detector tests:
```bash
python -m pytest tests/unit/ -v -k "structure or engulfing"
```

Run full test suite:
```bash
python -m pytest tests/unit/ -v
```

## Files Changed

- `core/structure/engulfing.py` - New Engulfing Detector implementation
- `configs/structure.json` - Added engulfing config section
- `core/structure/manager.py` - Integrated EngulfingDetector
- `tests/unit/test_engulfing_detector.py` - Comprehensive unit tests

## Example Detection Log

```json
{
  "ts": "2025-10-20T14:30:00Z",
  "run_id": "r_20251020_1430",
  "symbol": "EURUSD",
  "timeframe": "M15",
  "detector": "EngulfingDetector",
  "event_id": "EngulfingDetector|ENGULFING|EURUSD|15m|bullish|873|1.09950|1.10050|20251020_1430",
  "direction": "bullish",
  "origin_index": 873,
  "atr_at_creation": 0.00042,
  "body_atr": 1.35,
  "body_to_range": 0.72,
  "ema_ok": true,
  "zone_linked": true,
  "quality_score": 0.78,
  "quality": "HIGH",
  "lifecycle": "unfilled",
  "params": {
    "min_body_atr": 0.6,
    "min_body_to_range": 0.55,
    "lookahead_bars": 5,
    "follow_through_atr": 0.8
  }
}
```

## Next Steps

Once merged:
1. **Schema Validation** - Update `configs/structure.schema.json` to validate engulfing config
2. **AI Integration Hook** - Prepare engulfing signals for LLaMA reasoning layer
3. **MT5 Execution** - Wire validated engulfing signals to order placement
4. **GUI Dashboard** - Display engulfing patterns with lifecycle tracking

## Conventions Followed

✅ Canonical Structure objects with deterministic IDs  
✅ Lifecycle states (UNFILLED → FOLLOWED_THROUGH → EXPIRED)  
✅ ATR-based thresholds (all normalized)  
✅ Structured JSON logs (no prints)  
✅ Comprehensive unit tests (positive, negative, edge, determinism)  
✅ Config-driven parameters with validation  
✅ Debounce & dedupe logic  
✅ Quality scoring with weighted components  

---

**Status**: Ready for merge ✅  
**Tests**: All passing ✅  
**Determinism**: Verified ✅  
**Logging**: Structured only ✅
