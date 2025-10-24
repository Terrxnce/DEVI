# D.E.V.I 2.0 — Team Structure & Workflow

**Date**: Oct 22, 2025, 11:58 AM UTC+01:00
**Status**: Role Clarity Confirmed
**Purpose**: Establish clear responsibilities and execution workflow

---

## Team Composition

### Terry (Systems Architect & Lead)
**Role**: Architecture, logic, decision-making

**Responsibilities**:
- Design system architecture and roadmap
- Define logic and validation specifications
- Make strategic decisions on direction
- Provide implementation requirements
- Validate results and approve iterations
- Decide on next phase progression

**Deliverables**:
- Architecture documents
- Implementation specifications
- Validation criteria and success metrics
- Approval for phase progression

**Availability**: Strategic reviews (weekly), decision-making (as needed)

---

### Adam (Lead Developer & Implementation)
**Role**: Implementation, testing, execution

**Responsibilities**:
- Execute agreed specifications in code
- Run comprehensive tests and validation
- Report results, metrics, and logs
- Identify blockers and technical issues
- Implement fixes based on feedback
- Ensure code quality and determinism

**Deliverables**:
- Working code (production-ready)
- Test results and validation reports
- Daily logs (during execution phases)
- Phase summaries (end of phase)
- Blocker identification and escalation

**Availability**: Daily execution, weekly summaries

---

## Workflow: Sequential Execution (Not Parallel)

### Phase Execution Cycle

```
1. Terry: Provide Architecture + Specs
   ↓
2. Adam: Implement + Test
   ↓
3. Adam: Report Results + Logs
   ↓
4. Terry: Validate + Decide Next Steps
   ↓
5. Iterate (if needed) or Move to Next Phase
```

### Key Principle
**Implementation follows from agreed roadmap** (not concurrent planning)

---

## Communication Protocol

### Daily (During Execution Phases)

**Adam's Responsibility**:
- Share daily logs (pass-rate, errors, metrics)
- Flag any blockers or issues immediately
- Provide brief status update (5-10 min)

**Terry's Responsibility**:
- Monitor logs and metrics
- Flag any concerns or anomalies
- Provide guidance if needed

**Format**: Daily log summary (email or Slack)
```
Date: Oct 22, 2025
Phase: 1 (Live Dry-Run)
Status: Day 1 of 5

Metrics:
- Bars processed: 240 (ASIA session)
- Decisions generated: 12
- Pass-rate: 8.3%
- RR compliance: 100% (all ≥1.5)
- Validation errors: 0

Issues: None
Blockers: None
Next: Continue monitoring
```

### Weekly (End of Phase)

**Adam's Responsibility**:
- Prepare comprehensive phase summary
- Include all metrics, results, and logs
- Identify any issues or learnings
- Confirm readiness for next phase

**Terry's Responsibility**:
- Review phase summary
- Validate success criteria met
- Approve or request adjustments
- Provide next phase specifications

**Format**: Phase summary document (2-3 pages)
```
Phase 1 Summary (Oct 22-25, 2025)
- 5-day dry-run results
- Data quality validation
- Determinism replay results
- Success criteria: ✅ All met
- Ready for Phase 2: ✅ Yes
```

### As Needed (Blockers or Clarifications)

**Adam's Responsibility**:
- Escalate blockers immediately
- Request clarification on specs
- Propose solutions if possible

**Terry's Responsibility**:
- Provide rapid clarification
- Adjust specs if needed
- Unblock implementation

**Format**: Slack/email with context and proposed solution

---

## Phase 1 Execution (This Week)

### Terry's Role (Already Completed)
- ✅ Provided implementation analysis & roadmap
- ✅ Confirmed Phase 1-4 architecture
- ✅ Locked Phase 2 specs (OB+FVG exits, RR ≥1.5 rejection)
- ✅ Approved Phase 1 go-ahead

### Adam's Role (This Week)

**Priority 1: Confirm MT5 Data Source**
- [ ] Which broker/server? (e.g., ICMarkets-Demo, XM-Live)
- [ ] Demo or live account?
- [ ] Verify connection is active and stable

**Priority 2: Verify Data Stability**
- [ ] Fetch 1000 M15 bars for EURUSD
- [ ] Check: 0 gaps, 0 duplicates, valid OHLC
- [ ] Run `test_data_quality.py`
- [ ] Expected: 1000 consecutive 15-minute candles

**Priority 3: Start 5-Day Live Dry-Run**
- [ ] Keep `execution.mode = "dry-run"` (no live orders)
- [ ] Monitor daily: pass-rate, RR compliance, validation errors
- [ ] Collect all logs (gate_eval, decision, dry_run_summary, hourly_summary)
- [ ] Expected: 0 validation errors, pass-rate 5-15%, RR ≥1.5 for 100%

**Priority 4: Share Daily Logs**
- [ ] Each day: Brief status update (metrics, issues, blockers)
- [ ] Format: Simple daily summary (5-10 min read)

**Priority 5: Prepare Phase 1 Summary (End of Week)**
- [ ] 5-day dry-run results
- [ ] Data quality validation report
- [ ] Determinism replay results (100 bars diff output)
- [ ] Ready for Phase 2?

### Terry's Role (End of Week)
- [ ] Review Phase 1 results
- [ ] Validate success criteria met
- [ ] Approve Phase 2 implementation
- [ ] Provide Phase 2 detailed specs (if needed)

---

## Success Criteria (Phase 1)

| Metric | Target | Owner | Validation |
|--------|--------|-------|-----------|
| Validation errors | 0 across 5 days | Adam | Report daily |
| Pass-rate | 5-15% | Adam | Report daily |
| RR compliance | 100% ≥1.5 | Adam | Report daily |
| Determinism | 100% match | Adam | Report end-of-week |
| Logs collected | All 4 types | Adam | Report end-of-week |
| Ready for Phase 2 | Yes/No | Both | Sync end-of-week |

---

## Phase 1-4 Status (Locked)

| Phase | Owner | Status | Timeline | Next |
|-------|-------|--------|----------|------|
| 1 | Adam | 🟢 GO | This week | Daily logs → end-of-week summary |
| 2 | Adam | 🟡 Specs locked | Next week | Implement OB+FVG exits |
| 3 | Adam | 🟡 Design only | Weeks 4-5 | Implement after Phase 2 passes |
| 4 | Adam | 🟡 Ready | Weeks 6-7+ | Execute after Phase 3 passes |

---

## Key Principles

### 1. Sequential Execution
- Implementation follows specs (not parallel planning)
- Each phase completes before next begins
- No scope creep or concurrent design

### 2. Clear Handoffs
- Terry → specs and validation criteria
- Adam → working code and test results
- Terry → approval and next phase specs

### 3. Daily Transparency
- Adam shares daily logs during execution
- Terry monitors and flags issues
- Blockers escalated immediately

### 4. Locked Roadmap
- Phase 1-4 architecture is locked
- No major changes without explicit approval
- Iterations within phase only

### 5. Iterative Refinement
- Iterate based on results, not assumptions
- Each phase validated before next
- Learnings inform future phases

---

## Next Sync

**When**: End of Week 1 (Oct 25, 2025)
**What**: Phase 1 results + Phase 2 readiness
**Attendees**: Terry, Adam
**Duration**: 30-45 minutes

**Agenda**:
1. Review Phase 1 results (10 min)
2. Validate success criteria (10 min)
3. Review determinism replay results (5 min)
4. Confirm ready for Phase 2 (5 min)
5. Discuss any issues or learnings (10 min)

**Deliverables from Adam**:
- 5-day dry-run summary
- Data quality validation report
- Determinism replay results (100 bars diff output)
- Daily logs (all 5 days)

**Deliverables from Terry**:
- Phase 2 detailed specs (if needed)
- Approval to proceed to Phase 2
- Any adjustments or clarifications

---

## Summary

**Terry**: Architect, specs, validation, decisions
**Adam**: Implementation, testing, reporting, execution
**Together**: Iterate until stable, then move to next phase
**No Parallel Planning**: Implementation follows specs (not concurrent design)

---

**Status**: ✅ **Team Structure & Workflow Confirmed** 🚀

**Adam**: Start Phase 1 this week. Confirm MT5 data source and verify data stability first. Share daily logs.

**Terry**: Monitor daily logs. Sync with Adam at end of week for Phase 1 results and Phase 2 readiness.
