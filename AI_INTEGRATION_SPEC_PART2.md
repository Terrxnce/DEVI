# D.E.V.I 2.0 — AI Integration Specification (Part 2/2)

**Date**: Oct 21, 2025, 4:30 AM UTC+01:00
**Status**: Design Phase (Pre-Implementation)

---

## Safety & Testing

### 7️⃣ Shadow Mode: 1-2 Weeks, Success Criteria

**Shadow Mode Definition**:
- AI runs in parallel with composite scoring
- AI confidence is logged but NOT used for filtering
- All decisions still gated by composite score only
- Allows validation without affecting live trading

**Shadow Mode Configuration**:
```json
{
  "ai": {
    "enabled": true,
    "shadow_mode": true,
    "shadow_mode_duration_days": 14,
    "shadow_mode_start_date": "2025-10-21"
  }
}
```

**Shadow Mode Logic**:
```python
def _process_decision_generation(self, sltp_plans, data, session, timestamp, uzr_context):
    decisions = []
    
    for sltp_plan in sltp_plans:
        candidate_decision = Decision(...)
        
        # Stage 9.5: AI Reasoning (in shadow mode)
        if self.ai_enabled:
            ai_result = self._process_ai_reasoning(...)
            
            # Log AI result for analysis
            self._log_ai_call(
                event="ai_call_shadow",
                ai_confidence=ai_result['ai_confidence'],
                composite_score=candidate_decision.composite_score,
                final_score_would_be=...,
                decision_would_be_accepted=...
            )
            
            # In shadow mode: don't filter, just log
            if self.ai_config.get('shadow_mode', False):
                candidate_decision.metadata['ai_confidence'] = ai_result['ai_confidence']
                candidate_decision.metadata['ai_reasoning'] = ai_result['reasoning']
                candidate_decision.metadata['shadow_mode'] = True
            else:
                # Production mode: use final score
                final_score = (
                    self.config.weights['composite'] * candidate_decision.composite_score +
                    self.config.weights['ai'] * ai_result['ai_confidence']
                )
                if final_score < self.config.min_final_score_by_session[session.name]:
                    continue
                candidate_decision.metadata['final_score'] = final_score
        
        decisions.append(candidate_decision)
    
    return decisions
```

**Success Criteria (After 1-2 Weeks)**:

| Metric | Target | Action if Miss |
|--------|--------|-----------------|
| AI latency (p95) | <500ms | Optimize prompt or reduce batch size |
| AI availability | ≥99% | Check model stability |
| AI timeout rate | <1% | Increase timeout |
| AI error rate | <1% | Debug model errors |
| AI confidence distribution | 0.4-0.8 (most) | Adjust prompt |
| AI-composite correlation | 0.5-0.8 | Validate AI learning |
| Decisions AI would reject | 5-15% | Reasonable filtering |
| False positive rate | <10% | Adjust prompt/weights |
| False negative rate | <10% | Adjust prompt/weights |

**Exit Shadow Mode Criteria** (ALL must be met):
- ✅ AI latency (p95) < 500ms
- ✅ AI availability ≥99%
- ✅ AI timeout rate <1%
- ✅ AI error rate <1%
- ✅ AI-composite correlation 0.5-0.8
- ✅ False positive rate <10%
- ✅ False negative rate <10%
- ✅ Manual review of 50 AI decisions (spot check)

**If Criteria NOT Met**:
- Extend shadow mode by 1 week
- Adjust prompt or weights
- Increase timeout or reduce batch size
- Restart shadow mode

---

### 8️⃣ Unit Tests: Determinism & Mocking

**Test File**: `tests/unit/test_ai_reasoning.py`

```python
import pytest
from unittest.mock import patch
from core.orchestration.pipeline import TradingPipeline
from core.models.decision import Decision, DecisionType

class TestAIReasoning:
    """Test AI reasoning layer with mocked responses."""
    
    @pytest.fixture
    def pipeline(self):
        config = Config.load("configs/system.json")
        return TradingPipeline(config)
    
    @pytest.fixture
    def mock_llama_response(self):
        return {
            "confidence": 0.75,
            "reasoning": "Strong OB with rejection confirmation",
            "key_factors": ["rejection_confirmed", "ema_aligned"]
        }
    
    def test_ai_reasoning_success(self, pipeline, mock_llama_response):
        """Test successful AI reasoning."""
        with patch.object(pipeline, '_call_llama', return_value=mock_llama_response):
            candidate_decision = Decision(
                decision_type=DecisionType.BUY,
                symbol="EURUSD",
                entry_price=1.0948,
                stop_loss=1.0945,
                take_profit=1.0958,
                composite_score=0.71
            )
            
            ai_result = pipeline._process_ai_reasoning(
                candidate_decision=candidate_decision,
                structures=[],
                indicators={},
                session=None,
                data=None
            )
            
            assert ai_result['ai_confidence'] == 0.75
            assert ai_result['fallback_used'] == False
            assert ai_result['latency_ms'] > 0
    
    def test_ai_reasoning_timeout(self, pipeline):
        """Test AI timeout fallback."""
        with patch.object(pipeline, '_call_llama', side_effect=TimeoutError()):
            candidate_decision = Decision(
                decision_type=DecisionType.BUY,
                symbol="EURUSD",
                composite_score=0.71
            )
            
            ai_result = pipeline._process_ai_reasoning(
                candidate_decision=candidate_decision,
                structures=[],
                indicators={},
                session=None,
                data=None
            )
            
            assert ai_result['fallback_used'] == True
            assert ai_result['error'] == 'timeout'
            if pipeline.config.ai['fallback_mode'] == 'composite_only':
                assert ai_result['ai_confidence'] == 0.71
    
    def test_ai_reasoning_error(self, pipeline):
        """Test AI error fallback."""
        with patch.object(pipeline, '_call_llama', side_effect=ValueError("Model error")):
            candidate_decision = Decision(...)
            ai_result = pipeline._process_ai_reasoning(...)
            
            assert ai_result['fallback_used'] == True
            assert 'error' in ai_result
    
    def test_ai_determinism(self, pipeline, mock_llama_response):
        """Test deterministic AI outputs (same input → same output)."""
        with patch.object(pipeline, '_call_llama', return_value=mock_llama_response):
            candidate_decision = Decision(...)
            
            ai_result_1 = pipeline._process_ai_reasoning(...)
            ai_result_2 = pipeline._process_ai_reasoning(...)
            
            assert ai_result_1['ai_confidence'] == ai_result_2['ai_confidence']
            assert ai_result_1['reasoning'] == ai_result_2['reasoning']
    
    def test_ai_shadow_mode(self, pipeline):
        """Test shadow mode (AI runs but doesn't filter)."""
        pipeline.ai_config['shadow_mode'] = True
        
        with patch.object(pipeline, '_call_llama', return_value={"confidence": 0.3, ...}):
            decisions = pipeline._process_decision_generation(
                sltp_plans=[...],
                data=data,
                session=session,
                timestamp=timestamp,
                uzr_context={}
            )
            
            # Decision should be in list (not filtered by AI)
            assert len(decisions) > 0
            assert decisions[0].metadata['shadow_mode'] == True
    
    def test_ai_final_score_gating(self, pipeline):
        """Test final score gating (composite + AI)."""
        pipeline.ai_config['shadow_mode'] = False
        pipeline.config.weights = {'composite': 0.6, 'ai': 0.4}
        pipeline.config.min_final_score_by_session = {'LONDON': 0.70}
        
        with patch.object(pipeline, '_call_llama', return_value={"confidence": 0.5, ...}):
            candidate_decision = Decision(
                composite_score=0.80,
                # final_score = 0.6 * 0.80 + 0.4 * 0.5 = 0.68 (below 0.70)
            )
            
            decisions = pipeline._process_decision_generation(...)
            
            # Decision should be filtered
            assert len(decisions) == 0
```

**Test Execution**:
```bash
# Run all AI tests
pytest tests/unit/test_ai_reasoning.py -v

# Run with coverage
pytest tests/unit/test_ai_reasoning.py --cov=core.orchestration

# Run determinism tests only
pytest tests/unit/test_ai_reasoning.py -k determinism -v
```

---

### 9️⃣ Network Constraints: Local vs API Model

**Recommendation**: Local model (Ollama) for Phase 1

**Option A: Local Model (Ollama)** ✅ Recommended
```
Pros:
- No external API dependencies
- No network latency (local)
- No API rate limits
- No API costs
- Full control over model
- Deterministic outputs

Cons:
- Requires GPU (or CPU with slower inference)
- Model size (~4GB VRAM for 7B)
- Infrastructure cost

Setup:
1. Install Ollama: https://ollama.ai
2. Pull model: ollama pull llama2:7b
3. Run: ollama serve
4. Endpoint: http://localhost:11434
```

**Option B: API Model (OpenAI, Anthropic)** ⚠️ Not Recommended (Phase 1)
```
Pros:
- No infrastructure needed
- Latest models available

Cons:
- External API dependency
- Network latency (100-500ms)
- API rate limits
- API costs ($0.01-0.10 per call)
- Non-deterministic
- Privacy concerns

Setup:
1. Get API key
2. Configure endpoint
3. Add API key to environment
```

**Configuration**:

**For Local Model**:
```json
{
  "ai": {
    "provider": "ollama",
    "model": "llama2:7b",
    "endpoint": "http://localhost:11434/api/generate",
    "timeout_ms": 2000,
    "max_retries": 2
  }
}
```

**For API Model**:
```json
{
  "ai": {
    "provider": "openai",
    "model": "gpt-4",
    "endpoint": "https://api.openai.com/v1/chat/completions",
    "api_key_env": "OPENAI_API_KEY",
    "timeout_ms": 5000,
    "max_retries": 3
  }
}
```

---

## Data & Learning Loop

### 🔟 Outcome Fields: P&L, MAE/MFE, Slippage

**Outcome Fields to Store**:

**Per Trade**:
```json
{
  "trade_id": "unique_id",
  "decision_id": "decision_id",
  "symbol": "EURUSD",
  "entry_price": 1.0948,
  "entry_timestamp": "2025-10-21T04:30:00Z",
  "exit_price": 1.0965,
  "exit_timestamp": "2025-10-21T05:15:00Z",
  "position_size": 1.0,
  "stop_loss": 1.0945,
  "take_profit": 1.0958,
  "direction": "BUY",
  "rr": 1.75,
  "outcome": "TP_HIT",
  "pnl": 170,
  "pnl_pips": 17,
  "mae": 5,
  "mfe": 25,
  "slippage_entry": 0.5,
  "slippage_exit": 0.3,
  "duration_minutes": 45,
  "ai_confidence": 0.75,
  "composite_score": 0.71,
  "final_score": 0.73,
  "structure_type": "ORDER_BLOCK",
  "session": "LONDON"
}
```

**Storage Location**: `logs/trades.jsonl`

**Daily Summary**:
```json
{
  "date": "2025-10-21",
  "session": "LONDON",
  "trades_total": 12,
  "trades_won": 8,
  "trades_lost": 4,
  "win_rate": 0.667,
  "pnl_total": 1450,
  "avg_rr_achieved": 1.82,
  "avg_mae": 4.2,
  "avg_mfe": 18.5,
  "avg_slippage": 0.4,
  "avg_duration_minutes": 42,
  "avg_ai_confidence": 0.73,
  "avg_composite_score": 0.70,
  "avg_final_score": 0.72,
  "profit_factor": 2.1,
  "expectancy": 120.8
}
```

**Storage Location**: `logs/daily_summary.jsonl`

---

### 1️⃣1️⃣ Threshold Review: Frequency & Sign-Off

**Review Cadence**:

| Frequency | Metric | Owner | Action |
|-----------|--------|-------|--------|
| Daily | Win rate, avg RR, errors | Ops | Alert if drift >5% |
| Weekly | AI confidence distribution, latency, false rates | Data | Review & adjust |
| Monthly | Model performance, prompt effectiveness | AI Lead | Evaluate new prompt |
| Quarterly | Overall strategy performance, meta-model | Strategy | Major tuning |

**Weekly Review Checklist**:
```
[ ] Win rate: target 55-65%
[ ] Avg RR: target ≥1.5
[ ] AI latency (p95): target <500ms
[ ] AI availability: target ≥99%
[ ] AI-composite correlation: target 0.5-0.8
[ ] False positive rate: target <10%
[ ] False negative rate: target <10%
[ ] AI confidence distribution: check for extremes
[ ] Fallback usage: should be <2%
[ ] Any anomalies: investigate
```

**Sign-Off Process**:
```
1. Data team reviews metrics (daily)
2. AI team reviews AI-specific metrics (weekly)
3. Strategy team reviews overall performance (weekly)
4. If all green: continue as-is
5. If any red: propose adjustment
6. Strategy lead approves adjustment
7. Deploy new config (if needed)
8. Log change with reason & expected impact
```

**Change Log** (`logs/config_changes.jsonl`):
```json
{
  "timestamp": "2025-10-28T10:00:00Z",
  "change_type": "threshold_adjustment",
  "field": "scoring.scales.M15.fx.LONDON.min_final_score",
  "old_value": 0.68,
  "new_value": 0.70,
  "reason": "AI false positive rate 12% (target <10%)",
  "expected_impact": "Reduce decisions by ~5%, improve quality",
  "approved_by": "strategy_lead",
  "reviewed_by": ["data_team", "ai_team"]
}
```

---

### 1️⃣2️⃣ Meta-Model Assist: Yes/No?

**Recommendation**: **YES** (but Phase 2, after AI validation)

**What is Meta-Model Assist?**
- A second-level AI model that learns from AI reasoning outcomes
- Learns which AI decisions tend to be right/wrong
- Adjusts AI confidence based on patterns
- Essentially: "AI that learns from AI"

**Phase 1 (Current)**: AI reasoning layer only
- LLaMA provides confidence scores
- Composite + AI gating
- Shadow mode validation

**Phase 2 (After 1 month clean)**: Add meta-model
- Collect 1000+ AI decisions with outcomes
- Train meta-model to predict AI accuracy
- Use meta-model to adjust AI confidence
- Example: If AI says 0.75 but meta-model says "AI is 80% accurate on OB", adjust to 0.75 * 0.80 = 0.60

**Meta-Model Architecture**:
```
Input:
- AI confidence (0-1)
- Structure type (OB, FVG, etc.)
- Session (ASIA, LONDON, etc.)
- Composite score (0-1)
- Recent win rate (%)

Output:
- Adjusted confidence (0-1)
- Adjustment factor (0-1)
```

**Benefits**:
- ✅ Learns from AI mistakes over time
- ✅ Improves decision quality
- ✅ Adapts to market regime changes
- ✅ Reduces false positives/negatives

**Risks**:
- ❌ Adds complexity
- ❌ Requires 1000+ training samples
- ❌ May overfit to recent data
- ❌ Harder to debug

**Decision**:
- **Phase 1**: NO (focus on AI validation)
- **Phase 2**: YES (after 1 month clean, if AI is stable)
- **Implementation**: Simple linear model (sklearn) or neural network (PyTorch)

**Implementation Timeline**:
1. Week 1-4: AI validation (shadow mode)
2. Week 5-8: Collect outcomes (1000+ samples)
3. Week 9-10: Train meta-model
4. Week 11-12: Validate meta-model (shadow mode)
5. Week 13+: Deploy meta-model

---

## Summary & Recommendations

### Integration Points
- ✅ Call site: After SL/TP, before executor (Stage 9.5)
- ✅ Config: system.json (infrastructure), structure.json (logic)
- ✅ Fallback: composite_only (conservative)

### Engineering
- ✅ Latency budget: 2-3ms per decision (batched)
- ✅ Logging: ai_calls.jsonl + ai_daily_summary.jsonl
- ✅ Versioning: model_name, model_version, prompt_hash, deployed_timestamp

### Safety
- ✅ Shadow mode: 1-2 weeks before production
- ✅ Success criteria: 9 metrics (latency, availability, accuracy, etc.)
- ✅ Unit tests: Mock AI responses for determinism

### Infrastructure
- ✅ Local model (Ollama) recommended for Phase 1
- ✅ No external API dependencies
- ✅ Full control over model and outputs

### Data & Learning
- ✅ Store: trade_id, entry/exit, P&L, MAE/MFE, slippage, AI confidence
- ✅ Review: Daily (ops), Weekly (data), Monthly (AI), Quarterly (strategy)
- ✅ Meta-model: YES (Phase 2, after 1 month clean)

---

**Status**: ✅ **AI Integration Specification Complete** 🚀

**Next Steps**:
1. Review & approve spec with team
2. Implement AI reasoning layer (2-3 weeks)
3. Deploy to shadow mode (1-2 weeks)
4. Validate success criteria
5. Switch to production mode
6. Plan meta-model assist (Phase 2)
