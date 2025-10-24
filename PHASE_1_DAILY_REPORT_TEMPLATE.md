# Phase 1 Daily Report Template

**Use this template every evening (EOD) to report Phase 1 progress.**

---

## ✅ Phase 1 Day X Summary

**Date**: Oct 22/23/24/25, 2025
**Day**: X of 5
**Status**: [On Track / Blocked / Issue Detected]

---

## 📊 Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Pass-rate | 5-15% | __% | ✅/⚠️ |
| RR≥1.5 compliance | 100% | __% | ✅/⚠️ |
| Validation errors | 0 | __ | ✅/⚠️ |
| Bars processed | ~960 | __ | ✅/⚠️ |
| Decisions generated | 10-50 | __ | ✅/⚠️ |

---

## 📍 Session Breakdown

| Session | Bars | Decisions | Pass-rate | Avg Composite | Status |
|---------|------|-----------|-----------|---------------|--------|
| ASIA | 240 | __ | __% | __ | ✅/⚠️ |
| LONDON | 240 | __ | __% | __ | ✅/⚠️ |
| NY_AM | 240 | __ | __% | __ | ✅/⚠️ |
| NY_PM | 240 | __ | __% | __ | ✅/⚠️ |

---

## 📦 Artifacts Uploaded

- [ ] `daily_logs_bundle_DAY_X.tar.gz` (contains: gate_eval.jsonl, decision.jsonl, hourly_summary.jsonl, dry_run_summary.jsonl)
- [ ] `daily_summary_DAY_X.json` (metrics summary)
- [ ] Location: `artifacts/` folder

---

## 🔍 Data Quality Check

| Check | Status | Notes |
|-------|--------|-------|
| No gaps in bars | ✅/⚠️ | __ |
| No duplicate timestamps | ✅/⚠️ | __ |
| OHLC validity | ✅/⚠️ | __ |
| Timestamps in UTC | ✅/⚠️ | __ |

---

## ⚠️ Issues / Blockers

**None** or describe:

- Issue 1: [description]
  - Impact: [high/medium/low]
  - Action: [what you're doing about it]

- Issue 2: [description]
  - Impact: [high/medium/low]
  - Action: [what you're doing about it]

---

## ✅ Validation Checklist (Daily)

- [ ] All logs collected (gate_eval, decision, hourly_summary, dry_run_summary)
- [ ] Logs are valid JSONL (one JSON object per line)
- [ ] No validation errors in executor
- [ ] RR compliance 100% (all decisions ≥1.5)
- [ ] Pass-rate within 5-15% range
- [ ] No crashes or exceptions
- [ ] Determinism maintained (if tested)

---

## 🎯 Next Action

**Tomorrow**:
- [ ] Continue monitoring
- [ ] Investigate [specific issue] if any
- [ ] Collect logs and prepare next daily report

**End of Week**:
- [ ] Prepare Phase 1 summary
- [ ] Generate determinism diff (100-bar replay)
- [ ] Ready for sync with Terry

---

## 📝 Notes

[Any additional observations, patterns, or learnings from today]

---

**Submitted by**: Adam
**Reviewed by**: Terry (pending)
**Status**: Awaiting review
