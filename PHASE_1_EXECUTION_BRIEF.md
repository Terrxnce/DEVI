# Phase 1 Execution Brief — Active Instructions for Adam

**Date**: Oct 22, 2025, 12:12 PM UTC+01:00
**Status**: ✅ ACTIVE EXECUTION PROTOCOL
**From**: Terry (Systems Architect)
**To**: Adam (Lead Developer)
**Timeline**: Oct 22-25, 2025 (5 trading days)

---

## Official Phase 1 Deliverables Checklist

This document is your **working brief** for Phase 1. Everything we need logged, stored, and validated is inside. Follow this exactly.

---

## 1️⃣ Immediate Actions (Today, Oct 22)

### Priority 1: MT5 Source Confirmation
- [ ] Confirm broker/server/account
- [ ] Verify connection is active
- [ ] Document timezone handling (broker time → UTC)
- **File**: `artifacts/mt5_source_confirmation.json`
- **Status**: Required TODAY

### Priority 2: Data Quality Proof
- [ ] Fetch 1000 M15 bars for EURUSD
- [ ] Validate: 0 gaps, 0 duplicates, 100% OHLC validity
- [ ] Run `test_data_quality.py`
- [ ] Capture first/last timestamps (UTC)
- **File**: `artifacts/data_quality_EURUSD.json`
- **Status**: Required TODAY

### Priority 3: Config Fingerprint
- [ ] Generate SHA256 hashes for:
  - `configs/structure.json`
  - `configs/system.json`
  - `configs/broker_symbols.json`
- [ ] Verify all configs load without errors
- [ ] Verify all components initialized
- **File**: `artifacts/config_fingerprint.txt`
- **Status**: Required TODAY

### Priority 4: Start Dry-Run
- [ ] Once data quality confirmed, begin 5-day live dry-run
- [ ] Keep `execution.mode = "dry-run"` (no live orders)
- [ ] Monitor: pass-rate, RR compliance, validation errors
- **Status**: Begin TODAY after confirmations

---

## 2️⃣ Shared Folder Structure

Create this structure in your workspace:

```
c:\Users\Index\DEVI\
├── artifacts/                          (Confirmations, proofs, diffs)
│   ├── mt5_source_confirmation.json
│   ├── data_quality_EURUSD.json
│   ├── config_fingerprint.txt
│   ├── daily_logs_bundle_DAY_1.tar.gz
│   ├── daily_summary_DAY_1.json
│   ├── daily_logs_bundle_DAY_2.tar.gz
│   ├── daily_summary_DAY_2.json
│   ├── daily_logs_bundle_DAY_3.tar.gz
│   ├── daily_summary_DAY_3.json
│   ├── daily_logs_bundle_DAY_4.tar.gz
│   ├── daily_summary_DAY_4.json
│   ├── daily_logs_bundle_DAY_5.tar.gz
│   ├── daily_summary_DAY_5.json
│   └── determinism_diff.txt
│
├── logs/                               (Live dry-run logs)
│   ├── gate_eval.jsonl
│   ├── decision.jsonl
│   ├── hourly_summary.jsonl
│   └── dry_run_summary.jsonl
│
├── reports/                            (Analysis & reviews)
│   ├── PHASE_1_DAILY_REPORT_DAY_1.md
│   ├── PHASE_1_DAILY_REPORT_DAY_2.md
│   ├── PHASE_1_DAILY_REPORT_DAY_3.md
│   ├── PHASE_1_DAILY_REPORT_DAY_4.md
│   ├── PHASE_1_DAILY_REPORT_DAY_5.md
│   └── PHASE_1_ANALYSIS_REPORT.md     (Final review by Terry)
│
└── configs/                            (Snapshots for reproducibility)
    ├── structure.json.snapshot
    ├── system.json.snapshot
    └── broker_symbols.json.snapshot
```

**Upload Protocol**:
- Tag each artifact with `DAY_N` (e.g., `daily_logs_bundle_DAY_1.tar.gz`)
- Push to `artifacts/` folder daily
- Keep logs in `logs/` folder (append only, don't overwrite)
- This keeps version control simple and validation easy

---

## 3️⃣ Daily Report Prompt

**Every evening (EOD), send one message with this format:**

```
✅ Phase 1 Day X Summary
═══════════════════════════════════════

Date: Oct 22/23/24/25, 2025
Day: X of 5

Metrics:
  Pass-rate: __%
  RR≥1.5 compliance: __%
  Validation errors: __
  Bars processed: __
  Decisions generated: __

Session Breakdown:
  ASIA: __ decisions, __ pass-rate
  LONDON: __ decisions, __ pass-rate
  NY_AM: __ decisions, __ pass-rate
  NY_PM: __ decisions, __ pass-rate

Artifacts Uploaded:
  ✅ daily_logs_bundle_DAY_X.tar.gz
  ✅ daily_summary_DAY_X.json

Issues/Blockers:
  [None] or [describe]

Next Action:
  Continue monitoring / Investigate [issue] / Ready for Phase 2
```

This keeps me in the loop without extra meetings. I'll audit each report and flag any concerns immediately.

---

## 4️⃣ My Role This Week (Terry)

**I will**:
- ✅ Observe daily reports
- ✅ Verify artifacts are complete
- ✅ Audit data quality and determinism
- ✅ Flag any anomalies or blockers
- ✅ Generate Phase 1 Analysis Report (end of week)

**I will NOT**:
- ❌ Tweak configs or thresholds
- ❌ Change detection logic
- ❌ Adjust scoring scales
- ❌ Modify feature flags

**Why**: Let the dry-run data tell us what to adjust. At the end of 5 days, we'll review logs together and decide if Phase 2 can start.

---

## 5️⃣ Your Role This Week (Adam)

**You will**:
- ✅ Execute Phase 1 exactly as specified
- ✅ Collect all logs daily
- ✅ Upload artifacts to `artifacts/` folder
- ✅ Send daily report every evening
- ✅ Flag blockers immediately (don't wait for EOD)
- ✅ Prepare Phase 1 summary (end of week)

**You will NOT**:
- ❌ Change configs without approval
- ❌ Skip any validation checks
- ❌ Modify logging schema
- ❌ Adjust thresholds mid-phase

**Why**: We need clean, reproducible data to validate the system. Any changes mid-phase corrupt the baseline.

---

## 6️⃣ Success Criteria (End of Week 1)

**All of these must be met to proceed to Phase 2:**

- ✅ MT5 source confirmed (broker/server/account)
- ✅ Data quality validated (1000 bars, 0 gaps/duplicates)
- ✅ 5 days of logs collected (all 4 file types daily)
- ✅ Determinism verified (100% match on 100-bar replay)
- ✅ Config fingerprint captured (SHA hashes)
- ✅ 0 validation errors across 5 days
- ✅ Pass-rate 5-15% (noise filter healthy)
- ✅ RR compliance 100% (all ≥1.5)
- ✅ All daily reports submitted
- ✅ Phase 1 summary prepared

**If ANY criterion is not met**: We extend Phase 1 by 1 week and investigate.

---

## 7️⃣ End-of-Week Sync (Oct 25, 2025)

**When**: Oct 25, 5:00 PM UTC+01:00
**Duration**: 30-45 minutes
**Attendees**: Terry, Adam

**Agenda**:
1. Review 5-day dry-run results (10 min)
2. Audit artifacts and logs (10 min)
3. Validate success criteria (10 min)
4. Review determinism diff (5 min)
5. Approve Phase 2 or extend Phase 1 (5 min)

**Deliverables from Adam**:
- 5-day dry-run summary
- Data quality validation report
- Determinism replay results (100 bars diff output)
- All daily reports (5 days)
- All logs (gate_eval, decision, hourly_summary, dry_run_summary)

**Deliverables from Terry**:
- Phase 1 Analysis Report (official review)
- Approval to proceed to Phase 2 (or extension plan)
- Phase 2 detailed specs (if approved)

---

## 8️⃣ What Happens Next (After Phase 1)

**If Phase 1 passes** (all criteria met):
- ✅ Phase 2 starts immediately (Week 2)
- ✅ Implement OB + FVG structure exits
- ✅ Same daily report protocol
- ✅ Same artifact upload protocol

**If Phase 1 fails** (any criterion not met):
- ⚠️ Extend Phase 1 by 1 week
- ⚠️ Investigate root cause
- ⚠️ Adjust and retry
- ⚠️ Sync again at end of extended week

---

## 9️⃣ Quick Reference

**Today (Oct 22)**:
- [ ] MT5 source confirmation
- [ ] Data quality proof
- [ ] Config fingerprint
- [ ] Start dry-run

**Days 2-5 (Oct 23-25)**:
- [ ] Append daily logs
- [ ] Send daily report (EOD)
- [ ] Upload artifacts to folder
- [ ] Monitor for issues

**End of Week (Oct 25)**:
- [ ] Determinism check
- [ ] Phase 1 summary
- [ ] Sync with Terry
- [ ] Approve Phase 2?

---

## 🎯 Bottom Line

This is your working brief for Phase 1. Follow it exactly. Upload artifacts daily. Send daily reports. Let the data speak. At the end of 5 days, we'll review everything together and decide if Phase 2 can start.

**Status**: ✅ **READY TO EXECUTE** 🚀

**Adam**: Confirm you've received this brief and start with MT5 source + data quality proof today.

**Terry**: I'll audit daily reports and generate Phase 1 Analysis Report at end of week.
