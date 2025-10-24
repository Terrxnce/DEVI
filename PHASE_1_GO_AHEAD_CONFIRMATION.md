# Phase 1 Go-Ahead Confirmation — Action Items & Alignment

**Date**: Oct 22, 2025, 11:49 AM UTC+01:00
**From**: Terry
**To**: Dev
**Status**: Ready for Phase 1 Kickoff
**Timeline**: Start live dry-run this week

---

## ✅ Alignment Confirmed

Terry has reviewed the implementation analysis and confirmed alignment on all phases. Here's the official go-ahead with specific action items.

---

## 1️⃣ Phase 1 — Live Dry-Run (Real MT5 Data)

### Status: GO ✅

**Action Items for Dev**:

- [ ] **Confirm MT5 data source**
  - Which broker/server are you using? (e.g., ICMarkets-Demo, XM-Live, etc.)
  - Is it a demo or live account?
  - Verify connection is active and stable

- [ ] **Verify data stability**
  - Fetch 1000 M15 bars for EURUSD
  - Check: 0 gaps, 0 duplicates, valid OHLC relationships
  - Run `test_data_quality.py` to validate
  - **Expected**: 1000 consecutive 15-minute candles

- [ ] **Confirm timestamp handling**
  - All timestamps must be UTC
  - Convert broker time → UTC on ingestion
  - Log timezone conversion at startup

- [ ] **Start 5-day live dry-run**
  - Once data stability confirmed, begin dry-run
  - Keep `execution.mode = "dry-run"` (no live orders)
  - Monitor daily: pass-rate, RR compliance, validation errors
  - **Expected outcome**: 0 validation errors, pass-rate 5-15%, RR ≥1.5 for 100%

### Deliverables (End of Week 1):
- ✅ MT5 data source confirmed (broker/server/account)
- ✅ Data quality validation passed (1000 bars, 0 gaps/duplicates)
- ✅ 5 days of dry-run logs collected
- ✅ Daily summaries showing: pass-rate, RR compliance, validation errors
- ✅ Determinism replay test results (100 bars, 100% match)

---

## 2️⃣ Phase 2 — Structure-First SL/TP (Next Week)

### Status: DESIGN LOCKED ✅

**Approach** (Confirmed):
- Start with **OB + FVG only** (Week 2)
- Keep **ATR fallback enabled** as safety net
- Feature flag `use_structure_exits = false` initially (Phase 1)
- Expand to Engulf/UZR/Sweep in Week 3 (after OB+FVG stable)

**Key Rules** (Confirmed):
- ✅ Structure exits are primary (target ≥95% of exits)
- ✅ ATR fallback only if structure geometry unavailable
- ✅ Post-clamp RR validation: **reject if RR < 1.5** (don't degrade silently)
- ✅ Log exit_reason: "structure" | "structure+atr_buffer" | "atr_fallback"

**Action Items for Dev**:

- [ ] **Implement per-structure exit calculators**
  - OB: SL just beyond zone edge ± sl_atr_buffer; TP to opposite edge
  - FVG: SL beyond nearer gap edge ± buffer; TP to far edge
  - Engulf/UZR/Sweep: Use pattern/zone edge + buffer (add Week 3)

- [ ] **Implement broker clamp + RR re-check**
  - After calculating structure SL/TP, clamp to broker limits
  - Re-check RR after clamp
  - If RR < 1.5, **reject trade** (log reason)

- [ ] **Add exit_reason logging**
  - Log which exit method was used: structure, structure+atr_buffer, atr_fallback
  - Track distribution: expect ≥95% "structure" on clean days

- [ ] **Unit tests for each structure type**
  - OB exits: valid SL/TP, RR gate enforced, broker clamp correct
  - FVG exits: valid SL/TP, RR gate enforced, broker clamp correct
  - Engulf/UZR/Sweep: same (add Week 3)

- [ ] **Feature flag implementation**
  - Add to `configs/structure.json`:
    ```json
    {
      "sltp_planning": {
        "use_structure_exits": false,
        "structure_exit_types": ["order_block", "fair_value_gap"],
        "atr_fallback_enabled": true,
        "sl_atr_buffer": 0.5,
        "tp_extension_atr": 1.0
      }
    }
    ```
  - Phase 1: `use_structure_exits = false` (ATR-only)
  - Phase 2 Week 1: `use_structure_exits = true`, types = [OB, FVG]
  - Phase 2 Week 2: expand types = [OB, FVG, Engulfing, UZR, Sweep]

### Deliverables (End of Week 2-3):
- ✅ OB + FVG exit calculators implemented
- ✅ Broker clamp + RR re-check working
- ✅ Unit tests passing (all structure types)
- ✅ 3 days dry-run with feature flag ON
- ✅ exit_reason distribution: ≥95% "structure"

---

## 3️⃣ Phase 3 & 4 — Deferred (Design Only)

### Status: DESIGN LOCKED, NO CODE YET ✅

**Phase 3 — Profit Protection & Recovery** (Weeks 4-5):
- Leave in design phase for now
- No code changes until Phase 2 passes
- Once Phase 2 is stable (≥95% structure exits, 0 validation errors):
  - Implement state machines for profit protection
  - Implement recovery mode logic
  - Unit tests + dry-run validation

**Phase 4 — Paper → Live Ramp** (Weeks 6-7+):
- Standard progression: paper (1 week) → live (0.25× → 0.5× → 1.0×)
- No changes to this approach
- Stays as planned

---

## 4️⃣ Quick Clarifications — Answered

### Q1: Which MT5 data source are you using for dry-run?

**Answer**: 
- **Confirm with dev**: Which broker/server/account?
- **Expected**: Live MT5 feed (not mock)
- **Data format**: 1000 M15 bars, UTC timestamps, 0 gaps/duplicates
- **Validation**: Run `test_data_quality.py` before starting dry-run

### Q2: How are we storing logs (local /logs or external)?

**Answer**:
- **Local storage**: `c:\Users\Index\DEVI\logs\`
- **Format**: JSONL (one JSON object per line)
- **Rotation**: 100MB per file, keep 10 backups
- **Log types**:
  - `gate_eval.jsonl` (per-bar, ~240 per day)
  - `decision.jsonl` (per trade, ~10-50 per day)
  - `dry_run_summary.jsonl` (EOD, 1 per day)
  - `hourly_summary.jsonl` (per hour, 24 per day)

### Q3: Can you share the determinism replay results once ready (100 bars diff output)?

**Answer**:
- **When**: After Phase 1 data is stable (end of week 1)
- **Format**: 100 bars → 100% match on replay
- **Diff output example**:
  ```
  Determinism Test Results
  ========================
  Run 1: 100 bars → 8 decisions
  Run 2: 100 bars → 8 decisions
  
  Decision Comparison:
    Decision 0: ✅ MATCH (structure_id=OB_EURUSD_M15_42_abc123, composite=0.71, entry=1.0948)
    Decision 1: ✅ MATCH (structure_id=FVG_EURUSD_M15_55_def456, composite=0.68, entry=1.0955)
    ...
    Decision 7: ✅ MATCH (structure_id=UZR_EURUSD_M15_98_jkl012, composite=0.70, entry=1.0971)
  
  Overall: ✅ DETERMINISM VERIFIED (100% match)
  ```

---

## 🚀 Phase 1 Go-Ahead — Official

### Status: ✅ GREEN LIGHT

**Effective**: Oct 22, 2025, 11:49 AM UTC+01:00

**Dev Action Items (This Week)**:

1. [ ] Confirm MT5 data source (broker/server/account)
2. [ ] Verify data stability (1000 bars, 0 gaps/duplicates)
3. [ ] Run `test_data_quality.py` to validate
4. [ ] Start 5-day live dry-run
5. [ ] Monitor daily: pass-rate, RR compliance, validation errors
6. [ ] Collect determinism replay results (100 bars diff output)
7. [ ] Prepare Phase 1 summary (end of week)

**Success Criteria (End of Week 1)**:
- ✅ 0 validation errors across 5 days
- ✅ Pass-rate 5-15% (noise filter healthy)
- ✅ RR compliance 100% ≥1.5
- ✅ Determinism verified (replay tests pass)
- ✅ All logs collected and analyzed
- ✅ Ready to proceed to Phase 2

**If Any Issues**:
- Validation errors detected → investigate immediately
- Data quality issues → verify MT5 connection
- Determinism fails → debug non-deterministic code
- Pass-rate outside 5-15% → review composite scoring thresholds

---

## Timeline

| Week | Phase | Status | Owner |
|------|-------|--------|-------|
| 1 (Now) | Phase 1 | 🟢 GO | Dev |
| 2-3 | Phase 2 | 🟡 Design locked, code next | Dev |
| 4-5 | Phase 3 | 🟡 Design only, no code | Dev |
| 6-7+ | Phase 4 | 🟡 Ready, execute after Phase 3 | Dev |

---

## Next Sync

**When**: End of Week 1 (Oct 25, 2025)
**What**: Phase 1 results + Phase 2 readiness check
**Deliverables**:
- 5-day dry-run summary
- Determinism replay results
- Data quality validation report
- Ready to proceed to Phase 2?

---

**Message from Terry**: "Great breakdown. Everything looks tight and risk-aware. Let's get Phase 1 started this week. Confirm data source and we're good to go."

**Status**: ✅ **Phase 1 Officially Green-Lit** 🚀
