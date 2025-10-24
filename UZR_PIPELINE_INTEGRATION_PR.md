# PR: UZR Pipeline Integration + Feature Flag + Documentation

## Summary

This PR completes the Unified Zone Rejection (UZR) integration into the core trading pipeline with feature flagging, comprehensive documentation, and acceptance tests. UZR now runs as Stage 6 in the pipeline (after structure detection & scoring) and augments decision context with rejection signals.

## Changes

### 1. Feature Flag (`configs/system.json`)

Added `features.unified_zone_rejection` flag (default: `false`) to control UZR behavior:

```json
{
  "features": {
    "unified_zone_rejection": false
  }
}
```

- **Flag off**: Pipeline behavior unchanged; UZR context fields present but false
- **Flag on**: UZR detector runs; rejection signals populate decision metadata

### 2. Documentation (`core/structure/rejection.py`)

Added comprehensive module documentation at the top of the file:

#### State Diagram
```
UNFILLED
    |
    | (zone touched + reaction detected)
    v
PARTIAL (TOUCHED)
    |
    | (follow-through confirmed)
    v
FILLED (REJECTED)
    |
    +---> EXPIRED (age > max_age_bars OR follow_through_confirmed)
    |
    +---> INVALIDATED (structure invalidated externally)
```

#### Scoring Equation
Quality Score (0-1) = weighted sum of normalized components:
- **reaction_body_score** (w=0.35): Reaction candle body strength
- **follow_through_score** (w=0.35): Follow-through confirmation
- **penetration_score** (w=0.20): Zone penetration depth
- **context_score** (w=0.10): Contextual alignment bonuses (placeholder)

Quality Levels:
- PREMIUM: score >= 0.8
- HIGH: score >= 0.6
- MEDIUM: score >= 0.4
- LOW: score < 0.4

#### ID Composition
Deterministic structure IDs composed of:
```
structure_id = hash(symbol + timeframe + rejection_index + zone_id + direction)
```

Ensures:
- Deterministic replay (same inputs → same IDs)
- Uniqueness per zone/direction/timeframe
- Traceability to originating zone

#### Metrics
**Counters** (cumulative per session):
- detected: Total rejections detected
- rejected: Rejections that reached FILLED state
- followed_through: Rejections that reached EXPIRED via follow-through
- invalidated: Rejections that expired or were invalidated

**Gauge** (rolling average):
- average_quality_score: Mean quality_score of active rejections

**Detection Parameters** (all ATR-normalized):
- touch_atr_buffer: 0.25 ATR (default)
- midline_bias: 0.1 ATR (default)
- min_reaction_body_atr: 0.5 ATR (default)
- min_follow_through_atr: 1.0 ATR (default)
- lookahead_bars: 5 (default)
- max_age_bars: 20 (default)
- debounce_bars: 3 (default)

### 3. Pipeline Integration (`core/orchestration/pipeline.py`)

#### Imports & Initialization
- Added `UnifiedZoneRejectionDetector` import
- Initialized UZR detector in `__init__` with feature flag check
- Added logger for structured logging

#### New Pipeline Stage (Stage 6)
Added `_process_uzr()` method that:
- Runs UZR detector on zone structures (OB, FVG)
- Captures rejection events and lifecycle transitions
- Populates UZR context with compatibility shim booleans:
  - `rejection`: True if any valid rejection detected this bar
  - `rejection_confirmed_next`: True if FOLLOWED_THROUGH state reached
  - `uzr_enabled`: Feature flag status
- Logs structured JSON events for UZR processing
- Returns early if flag is off (no processing)

#### Decision Context Enhancement
Updated `_process_decision_generation()` to:
- Accept optional `uzr_context` parameter
- Inject UZR compatibility shim fields into decision metadata:
  ```python
  metadata['rejection'] = uzr_context.get('rejection', False)
  metadata['rejection_confirmed_next'] = uzr_context.get('rejection_confirmed_next', False)
  metadata['uzr_enabled'] = uzr_context.get('uzr_enabled', False)
  ```
- Ensures GUI/signal surfaces can consume rejection signals

#### Error Handling
- Replaced print statements with structured logging
- All errors logged via `logger.warning()` with context dict
- Pipeline continues gracefully on UZR errors

### 4. Acceptance Tests (`tests/unit/test_uzr_pipeline_integration.py`)

Comprehensive test suite covering:

#### Feature Flag Tests
- `test_flag_off_no_uzr_processing`: Verifies UZR disabled when flag off
- `test_flag_on_uzr_enabled`: Verifies UZR enabled when flag on

#### Context Population Tests
- `test_uzr_context_in_metadata_flag_off`: UZR fields present but false
- `test_uzr_context_in_metadata_flag_on`: UZR fields populated when enabled

#### Deterministic Replay Tests
- `test_identical_runs_produce_identical_decisions`: Two runs with same inputs produce identical decisions

#### Structured Logging Tests
- `test_no_prints_only_structured_logs`: Verifies only structured logs (no prints)

#### Snapshot Behavior Tests
- `test_flag_off_snapshot_unchanged`: Flag off produces identical baseline behavior

## Acceptance Checks

✅ **Flag off**: Pipeline behavior unchanged (snapshot test passes)
✅ **Flag on**: UZR logs appear; compatibility booleans populated
✅ **Deterministic replay**: Identical IDs + logs across runs
✅ **No prints**: Only structured JSON logs
✅ **Compatibility shim**: `rejection` and `rejection_confirmed_next` booleans exposed

## Merge Criteria

- [x] UZR detector implementation complete and tested
- [x] Feature flag added to system.json
- [x] Pipeline integration wired (Stage 6)
- [x] Compatibility shim exposed in decision metadata
- [x] Comprehensive documentation added
- [x] Acceptance tests pass
- [x] Structured logging only (no prints)
- [x] Deterministic replay verified

## Next Steps

Once merged:
1. GUI/signal surfaces can consume `rejection` and `rejection_confirmed_next` fields
2. Enable flag in production configs when ready
3. Monitor UZR event logs for signal quality
4. Integrate AI reasoning layer to validate UZR signals
5. Wire MT5 execution layer to act on validated signals

## Testing

Run acceptance tests:
```bash
python -m pytest tests/unit/test_uzr_pipeline_integration.py -v
```

Run full test suite:
```bash
python -m pytest tests/unit/ -v
```

## Files Changed

- `configs/system.json` - Added feature flag
- `core/structure/rejection.py` - Added comprehensive documentation
- `core/orchestration/pipeline.py` - Added UZR integration stage + compatibility shim
- `tests/unit/test_uzr_pipeline_integration.py` - New acceptance test suite

## Artifacts

### Example UZR Processing Log (Flag On)
```json
{
  "event": "uzr_processing",
  "run_id": "session_123",
  "symbol": "EURUSD",
  "rejections_detected": 2,
  "rejection_flag": true,
  "rejection_confirmed_next": false,
  "uzr_enabled": true
}
```

### Example Decision Metadata (Flag On)
```json
{
  "structure_type": "ORDER_BLOCK",
  "quality": "HIGH",
  "pipeline_version": "2.0",
  "rejection": true,
  "rejection_confirmed_next": false,
  "uzr_enabled": true
}
```

### Example Decision Metadata (Flag Off)
```json
{
  "structure_type": "ORDER_BLOCK",
  "quality": "HIGH",
  "pipeline_version": "2.0",
  "rejection": false,
  "rejection_confirmed_next": false,
  "uzr_enabled": false
}
```

---

**Status**: Ready for merge ✅
**Determinism**: Verified ✅
**Tests**: All passing ✅
