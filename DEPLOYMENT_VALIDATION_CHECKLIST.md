# DEVI 2.0 Deployment Validation Checklist

## Day 0: Pre-Deployment Smoke Tests

### Schema + Boot
- [ ] Config loads without errors (`configs/structure.json` valid JSON)
- [ ] All detectors initialized: FVG, OB, BOS, Sweep, UZR, Engulfing
- [ ] Composite scorer instantiated with weights summing to 1.0
- [ ] UZR flag state confirmed (expected: `enabled: true`)
- [ ] Scoring scales present for M15 FX (ASIA, LONDON, NY_AM, NY_PM)

### Warmup Sanity (First 50 Bars per Symbol)
- [ ] 0 JSON `print()` statements in logs (structured logging only)
- [ ] Each bar shows:
  - [ ] `composite_tech_score` (0..1)
  - [ ] `passed_gate` (bool)
  - [ ] `gate_reasons` (array, empty if passed)
  - [ ] Structure counts after caps:
    - [ ] FVG ≤3 per side
    - [ ] OB ≤3 per side
    - [ ] Engulfing ≤5 total
    - [ ] BOS ≤3 total
    - [ ] Sweep ≤3 total
    - [ ] Rejection ≤5 total

### Determinism Test
- [ ] Replay same data twice on same symbol/timeframe
- [ ] Verify: Identical structure IDs across runs
- [ ] Verify: Identical composite scores across runs
- [ ] Verify: Identical gate pass/fail decisions across runs

---

## Week 1: Live Monitoring Metrics

### Per-Session Targets

| Metric | Target | Action if Miss |
|--------|--------|-----------------|
| Gate pass-rate | 5–15% of bars | Too high → raise `min_composite` +0.02; too low → lower -0.02 |
| Decisions with RR≥1.5 | ≥90% | Check SL/TP planning logic |
| FVG active per side | ≤3 | If clustering: drop to 2 |
| UZR follow-through hit-rate | ≥55% | Validate with 0.8 ATR FT + lookahead 6 |
| False signals (manual eval) | <10% trend-misaligned | Review EMA alignment component |
| Avg composite per session | 0.65–0.70 | Stable = good; drift >0.05 = investigate |

### Daily Logging

- [ ] Per-bar `gate_eval` events logged (INFO level)
  - [ ] session, symbol, tf, composite_tech_score, passed_gate, component_breakdown, gate_reasons
- [ ] Per-decision events logged (INFO level)
  - [ ] type, rr, origin_structure_type, quality_score, uzr_flags
- [ ] Daily summary aggregated at EOD (INFO level)
  - [ ] session_breakdown with bars, gated_in, pass_rate, avg_composite
  - [ ] avg_rr, median_rr
  - [ ] structure_counts (FVG, OB, BOS, Sweep, Rejection, Engulfing)

### Drift Detection

- [ ] Composite score drift alert enabled (threshold: 0.05)
- [ ] Alert triggered if `|today_avg - yesterday_avg| > 0.05` per session
- [ ] Investigate on alert: detector drift, market regime, config reload

---

## Week 1: Manual Review

### First 20 Decisions
- [ ] Review entry structure type (OB, FVG, Engulfing, etc.)
- [ ] Verify trend alignment (EMA 21>50>200 or 21<50<200)
- [ ] Check zone proximity (within 0.5 ATR of OB/FVG edge)
- [ ] Validate RR ≥1.5
- [ ] Confirm UZR flags (rejection, rejection_confirmed_next)

### False Signal Analysis
- [ ] Count signals that are trend-misaligned (target: <10%)
- [ ] Identify patterns in false signals (e.g., all in choppy zones?)
- [ ] Correlate with EMA alignment component (if low, tune slope_min)

---

## Week 1: Safe Tuning Knobs

### If ASIA Too Quiet (Pass-Rate <5%)
**Option 1** (Recommended first):
- Lower `scoring.scales.M15.fx.ASIA.min_composite` from 0.68 → 0.66
- Restart pipeline, monitor for 1 day

**Option 2** (If Option 1 insufficient):
- Session override: `engulfing.min_body_atr` 0.6 → 0.5 (ASIA only)
- Restart pipeline, monitor for 1 day

### If Micro FVGs Slip In (Too Many Small Gaps)
- Raise `fair_value_gap.min_gap_atr_multiplier` from 0.15 → 0.20
- Restart pipeline, monitor for 1 day

### If Rejections Feel Late (UZR Hit-Rate <55%)
- Reduce `unified_zone_rejection.min_follow_through_atr` from 0.8 → 0.7
- Restart pipeline, monitor for 1 day
- **Note**: Medium-risk change; revert if false signals spike

### If Gate Pass-Rate Too High (>15%)
- Raise each session's `min_composite` by +0.02:
  - ASIA: 0.68 → 0.70
  - LONDON: 0.65 → 0.67
  - NY_AM: 0.66 → 0.68
  - NY_PM: 0.67 → 0.69
- Restart pipeline, monitor for 1 day

---

## Quick Backout Plan (< 5 min)

### Revert FVG (1 min)
```json
{
  "fair_value_gap": {
    "max_age_bars": 250,           // was 150
    "min_gap_atr_multiplier": 0.0  // was 0.15
  }
}
```

### Revert UZR (1 min)
```json
{
  "unified_zone_rejection": {
    "min_follow_through_atr": 1.0,  // was 0.8
    "lookahead_bars": 5             // was 6
  }
}
```

### Raise Pass-Rate (1 min)
```json
{
  "scoring": {
    "scales": {
      "M15": {
        "fx": {
          "ASIA":   { "min_composite": 0.70 },  // was 0.68
          "LONDON": { "min_composite": 0.67 },  // was 0.65
          "NY_AM":  { "min_composite": 0.68 },  // was 0.66
          "NY_PM":  { "min_composite": 0.69 }   // was 0.67
        }
      }
    }
  }
}
```

---

## Week 2+: High-ROI Next Steps

### Per-Session Dashboard Card
- [ ] Pass-rate (%) by session
- [ ] Avg composite score by session
- [ ] Decision count by session
- [ ] Avg RR by session
- [ ] Update hourly, review daily

### Anomaly Alerts
- [ ] Composite drift alert (>0.05 day-over-day)
- [ ] Pass-rate anomaly (>2σ from rolling 7-day mean)
- [ ] RR anomaly (median RR drops >0.2)

### Shadow Backtest (3 Months, New Config)
- [ ] Run backtest with tuned config on historical data
- [ ] Compare vs. old config:
  - [ ] Win rate (%)
  - [ ] Profit factor
  - [ ] Avg RR
  - [ ] Max drawdown
  - [ ] Sharpe ratio
- [ ] If improvements validated, scale live exposure

### Per-Timeframe Tuning (Optional)
- [ ] Backtest M5, M30, H1 with adjusted scales
- [ ] Validate per-TF thresholds before live deployment

---

## Sign-Off

- [ ] All Day 0 smoke tests passed
- [ ] Week 1 monitoring infrastructure in place
- [ ] Manual review process defined
- [ ] Tuning knobs documented
- [ ] Backout plan tested (dry-run)
- [ ] **Ready for live deployment** ✅
