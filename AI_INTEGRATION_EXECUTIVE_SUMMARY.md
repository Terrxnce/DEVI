# D.E.V.I 2.0 — AI Integration Executive Summary

**Date**: Oct 21, 2025, 4:30 AM UTC+01:00
**Status**: Design Complete, Ready for Implementation
**Timeline**: 2-3 weeks implementation + 1-2 weeks shadow mode

---

## Quick Answers to Your 12 Questions

### Integration & Config
**1. Call Site**: After SL/TP planning (Stage 9.5), before executor
- AI runs with full decision context
- Can filter decisions before execution
- Optional (can disable via config)

**2. Config Location**:
- `system.json`: Infrastructure (provider, endpoint, timeout, versioning)
- `structure.json`: Decision logic (weights, thresholds, prompt template)

**3. Fallback Behavior**: `composite_only` (recommended)
- On timeout/error: Use composite score as AI confidence
- Keeps signal flow alive
- Conservative approach

### Engineering & Ops
**4. Latency Budget**: 2-3ms per decision (batched)
- Batch by symbol (1-3 decisions per symbol)
- Timeout: 2000ms (covers network latency)
- Latency SLA: p95 < 500ms

**5. Logging**:
- `logs/ai_calls.jsonl`: Per AI call (success, timeout, error)
- `logs/ai_daily_summary.jsonl`: Daily metrics per session
- Rotation: 100MB per file, keep 10 backups

**6. Versioning**:
- Store: model_name, model_version, prompt_hash, prompt_version, deployed_timestamp
- Include in every AI call log
- Track prompt changes in config_changes.jsonl

### Safety & Testing
**7. Shadow Mode**: 1-2 weeks before production
- AI runs but doesn't filter decisions
- All decisions still gated by composite score
- 9 success criteria (latency, availability, accuracy, correlation, false rates)

**8. Unit Tests**: Mock AI responses for determinism
- Test success, timeout, error cases
- Test shadow mode behavior
- Test final score gating
- All tests use mocked LLaMA responses

**9. Network Constraints**: Local model (Ollama) recommended
- No external API dependencies
- No network latency
- Full control over model
- Deterministic outputs

### Data & Learning
**10. Outcome Fields**: P&L, MAE/MFE, slippage
- Store per trade: entry/exit, P&L, MAE/MFE, slippage, AI confidence, structure type
- Store daily: win rate, avg RR, profit factor, expectancy
- File: logs/trades.jsonl, logs/daily_summary.jsonl

**11. Threshold Review**: Weekly (data), monthly (AI), quarterly (strategy)
- Daily: Win rate, avg RR, errors (ops alert)
- Weekly: AI metrics, false rates (data review)
- Monthly: Model performance (AI team)
- Quarterly: Overall strategy (strategy lead)

**12. Meta-Model Assist**: YES (Phase 2, after 1 month clean)
- Learn which AI decisions are accurate
- Adjust AI confidence based on patterns
- Implement after AI validation
- Timeline: Week 9-12

---

## Architecture Overview

### Pipeline Integration
```
Stage 9: Decision Generation
  ├─ Create candidate decision
  ├─ [NEW] Stage 9.5: AI Reasoning
  │  ├─ Call LLaMA with context
  │  ├─ Parse confidence score
  │  ├─ Apply fallback on timeout
  │  └─ Merge AI confidence with composite
  └─ Filter by min_final_score
     ↓
Stage 10: Execution
```

### Configuration
```json
{
  "system.json": {
    "ai": {
      "enabled": true,
      "provider": "ollama",
      "model": "llama2:7b",
      "endpoint": "http://localhost:11434",
      "timeout_ms": 2000,
      "fallback_mode": "composite_only",
      "versioning": {...}
    }
  },
  "structure.json": {
    "scoring": {
      "weights": {
        "composite": 0.60,
        "ai": 0.40
      },
      "scales": {
        "M15": {
          "fx": {
            "ASIA": {"min_final_score": 0.70}
          }
        }
      }
    }
  }
}
```

### Fallback Logic
```
AI Call
  ├─ Success → Use AI confidence
  ├─ Timeout → Use composite score (fallback_mode=composite_only)
  └─ Error → Use composite score (fallback_mode=composite_only)
```

---

## Implementation Roadmap

### Phase 1: AI Reasoning Layer (2-3 weeks)
**Week 1**:
- Implement AIReasoner class
- Integrate with pipeline (Stage 9.5)
- Add logging (ai_calls.jsonl)
- Add versioning tracking

**Week 2**:
- Implement batching (per-symbol)
- Add timeout/error handling
- Add fallback logic
- Implement shadow mode

**Week 3**:
- Add unit tests (mock responses)
- Add integration tests
- Performance tuning
- Documentation

### Phase 2: Shadow Mode Validation (1-2 weeks)
**Week 1**:
- Deploy with shadow_mode=true
- Monitor AI metrics (latency, availability, errors)
- Collect AI decisions with outcomes
- Manual review of 50 decisions

**Week 2** (if criteria met):
- Exit shadow mode (shadow_mode=false)
- Start production mode
- Monitor daily metrics
- Weekly threshold reviews

### Phase 3: Meta-Model Assist (Weeks 9-12)
**Week 9-10**:
- Collect 1000+ AI decisions with outcomes
- Train meta-model (linear or neural)
- Validate on holdout set

**Week 11-12**:
- Deploy meta-model to shadow mode
- Validate success criteria
- Switch to production

---

## Success Criteria

### Shadow Mode Exit (All must be met)
- ✅ AI latency (p95) < 500ms
- ✅ AI availability ≥99%
- ✅ AI timeout rate <1%
- ✅ AI error rate <1%
- ✅ AI-composite correlation 0.5-0.8
- ✅ False positive rate <10%
- ✅ False negative rate <10%
- ✅ Manual review of 50 decisions (spot check)

### Production Mode Targets (Weekly)
- ✅ Win rate: 55-65%
- ✅ Avg RR: ≥1.5
- ✅ AI latency (p95): <500ms
- ✅ AI availability: ≥99%
- ✅ Fallback usage: <2%
- ✅ AI-composite correlation: 0.5-0.8
- ✅ False positive rate: <10%
- ✅ False negative rate: <10%

---

## Key Design Decisions

### Why Ollama (Local Model)?
- ✅ No external dependencies
- ✅ Deterministic outputs
- ✅ Full control over model
- ✅ No API costs
- ✅ No privacy concerns
- ❌ Requires GPU (or CPU slower)

### Why Composite + AI (Weighted)?
- ✅ Composite is proven (Phase 1 validated)
- ✅ AI adds reasoning capability
- ✅ Weighted combination is conservative
- ✅ Easy to tune weights per session
- ✅ Can disable AI without breaking system

### Why Shadow Mode First?
- ✅ Validate AI before affecting trading
- ✅ Collect outcomes for meta-model
- ✅ Identify failure modes early
- ✅ Build confidence in system
- ✅ Easy to rollback if issues

### Why Meta-Model Later?
- ✅ Need 1000+ training samples first
- ✅ AI must be stable before meta-learning
- ✅ Reduces risk of overfitting
- ✅ Allows time for AI validation
- ✅ Improves over time (learning loop)

---

## Risk Mitigation

### Risk: AI Latency Too High
**Mitigation**:
- Batch decisions per symbol
- Reduce batch size if needed
- Use faster model (3B instead of 7B)
- Increase timeout to 3000ms

### Risk: AI Confidence Distribution Extreme
**Mitigation**:
- Adjust prompt to encourage middle scores
- Add temperature parameter to model
- Review prompt examples
- Validate with manual spot checks

### Risk: AI Timeout/Error Rate High
**Mitigation**:
- Check model stability
- Increase timeout
- Add retry logic
- Monitor Ollama logs

### Risk: False Positive Rate High
**Mitigation**:
- Raise min_final_score threshold
- Adjust prompt to be more conservative
- Increase AI weight (currently 0.40)
- Review rejected decisions manually

### Risk: False Negative Rate High
**Mitigation**:
- Lower min_final_score threshold
- Adjust prompt to be more aggressive
- Decrease AI weight (currently 0.40)
- Review missed opportunities manually

---

## Files to Create

| File | Purpose | Lines |
|------|---------|-------|
| `core/orchestration/ai_reasoner.py` | AI reasoning layer | 300+ |
| `core/orchestration/ai_logging.py` | AI call & summary logging | 150+ |
| `prompts/llama2_v1.0.txt` | LLaMA prompt template | 30+ |
| `tests/unit/test_ai_reasoning.py` | Unit tests (mocked) | 200+ |
| `AI_INTEGRATION_SPEC_PART1.md` | Spec Part 1 | ✅ Done |
| `AI_INTEGRATION_SPEC_PART2.md` | Spec Part 2 | ✅ Done |

---

## Next Steps

### Immediate (This Week)
1. Review & approve spec with team
2. Identify any blockers or concerns
3. Confirm Ollama setup (if local model)
4. Plan sprint for implementation

### Week 1-3 (Implementation)
1. Implement AIReasoner class
2. Integrate with pipeline
3. Add logging & versioning
4. Implement shadow mode
5. Write unit tests
6. Performance tuning

### Week 4-5 (Shadow Mode)
1. Deploy with shadow_mode=true
2. Monitor metrics
3. Collect outcomes
4. Manual reviews
5. Validate success criteria

### Week 6+ (Production)
1. Exit shadow mode
2. Start production mode
3. Weekly threshold reviews
4. Plan meta-model assist
5. Continuous monitoring

---

## Approval Checklist

- [ ] Spec reviewed by engineering team
- [ ] Spec reviewed by data team
- [ ] Spec reviewed by strategy team
- [ ] Ollama setup confirmed (if local model)
- [ ] API setup confirmed (if API model)
- [ ] Timeline approved
- [ ] Budget approved (GPU/infrastructure)
- [ ] Success criteria agreed
- [ ] Rollback plan agreed
- [ ] Ready to implement

---

**Status**: ✅ **AI Integration Specification Complete & Ready for Implementation** 🚀

**Questions?** Review Part 1 & Part 2 for detailed specifications.
