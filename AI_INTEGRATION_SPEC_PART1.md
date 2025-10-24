# D.E.V.I 2.0 — AI Integration Specification (Part 1/2)

**Date**: Oct 21, 2025, 4:30 AM UTC+01:00
**Status**: Design Phase (Pre-Implementation)

---

## Integration & Config

### 1️⃣ Call Site: Pipeline Stage Order

**Exact Call Site** (in `pipeline.py`, `_process_decision_generation()`):
```python
# Stage 9.5: AI Reasoning (NEW)
if self.ai_enabled:
    ai_result = self._process_ai_reasoning(
        candidate_decision=candidate_decision,
        structures=scored_structures,
        indicators=indicators,
        session=session,
        data=data
    )
    
    # Merge scores
    final_score = (
        self.config.weights['composite'] * candidate_decision.composite_score +
        self.config.weights['ai'] * ai_result['ai_confidence']
    )
    
    # Gate on final score
    if final_score < self.config.min_final_score_by_session[session.name]:
        continue  # Skip this decision
    
    candidate_decision.metadata['ai_confidence'] = ai_result['ai_confidence']
    candidate_decision.metadata['final_score'] = final_score
```

**Key Points**:
- ✅ AI runs AFTER SL/TP planning (full decision context)
- ✅ AI runs BEFORE executor (can filter decisions)
- ✅ AI is optional (disable via config)
- ✅ Fallback to composite-only if timeout/error

---

### 2️⃣ Configuration: system.json vs structure.json

**In `configs/system.json`** (infrastructure):
```json
{
  "ai": {
    "enabled": true,
    "provider": "ollama",
    "model": "llama2:7b",
    "endpoint": "http://localhost:11434",
    "timeout_ms": 2000,
    "max_retries": 2,
    "fallback_mode": "composite_only",
    "versioning": {
      "model_name": "llama2",
      "model_version": "7b",
      "prompt_hash": "sha256_abc123...",
      "prompt_version": "v1.0"
    }
  },
  "logging": {
    "ai_call_log": "logs/ai_calls.jsonl",
    "ai_daily_summary": "logs/ai_daily_summary.jsonl",
    "rotation_size_mb": 100,
    "retention_days": 30
  }
}
```

**In `configs/structure.json`** (decision logic):
```json
{
  "scoring": {
    "weights": {
      "composite": 0.60,
      "ai": 0.40
    },
    "scales": {
      "M15": {
        "fx": {
          "ASIA": {
            "min_composite": 0.68,
            "min_final_score": 0.70,
            "min_rr": 1.5
          }
        }
      }
    }
  },
  "ai_reasoning": {
    "enabled": true,
    "prompt_template": "v1.0",
    "context_fields": [
      "structure_type",
      "quality_score",
      "composite_score",
      "uzr_flags",
      "ema_alignment"
    ]
  }
}
```

**Rationale**:
- `system.json`: Infrastructure (provider, endpoint, timeout, versioning)
- `structure.json`: Decision logic (weights, thresholds, prompt template)

---

### 3️⃣ Fallback Behavior on Timeout/Error

**Recommended**: `composite_only` (conservative)

**Fallback Options**:
- `composite_only`: Use composite score as AI confidence (keeps signal flow)
- `hold`: Reject decision (stops all signals on AI failure)

**Implementation**:
```python
def _process_ai_reasoning(self, candidate_decision, ...):
    try:
        # Call LLaMA
        response = self._call_llama(...)
        ai_confidence = float(response['confidence'])
        
        return {
            "ai_confidence": ai_confidence,
            "reasoning": response['reasoning'],
            "fallback_used": False,
            "latency_ms": latency,
            "error": None
        }
    
    except TimeoutError:
        if self.config.ai['fallback_mode'] == "composite_only":
            return {
                "ai_confidence": candidate_decision.composite_score,
                "reasoning": "AI timeout - using composite score",
                "fallback_used": True,
                "latency_ms": self.config.ai['timeout_ms'],
                "error": "timeout"
            }
        elif self.config.ai['fallback_mode'] == "hold":
            return {
                "ai_confidence": 0.0,
                "reasoning": "AI timeout - holding",
                "fallback_used": True,
                "error": "timeout"
            }
    
    except Exception as e:
        # Similar logic for errors
        ...
```

---

## Engineering & Ops

### 4️⃣ Latency Budget & Batching

**Per-Bar Latency Budget**:
```
Total per bar: ~10-15ms (with AI)
├─ Indicators: 1-2ms
├─ Structure detection: 2-3ms
├─ Scoring: 0.5-1ms
├─ Guards: 0.5ms
├─ SL/TP planning: 1-2ms
├─ Decision generation: 0.5ms
└─ AI reasoning: 2-3ms (target)
```

**AI Latency Budget**: 2-3ms per decision
- Timeout: 2000ms (allows network latency)
- Per-decision: 200-300ms (if batched)

**Batching Strategy** (Recommended: Per-Symbol):
```python
# Batch decisions per symbol before AI call
decisions_by_symbol = {}
for decision in candidate_decisions:
    if decision.symbol not in decisions_by_symbol:
        decisions_by_symbol[decision.symbol] = []
    decisions_by_symbol[decision.symbol].append(decision)

# Call AI once per symbol with all decisions
for symbol, decisions in decisions_by_symbol.items():
    ai_results = self._call_llama_batch(
        decisions=decisions,
        context={"symbol": symbol, "session": session}
    )
```

**Recommendation**:
- ✅ Batch by symbol (1-3 decisions per symbol per bar)
- ✅ Max batch size: 10 decisions
- ✅ Timeout: 2000ms
- ✅ Latency SLA: 95th percentile < 500ms

---

### 5️⃣ Logging: AI Call Logs & Daily Summaries

**`logs/ai_calls.jsonl`** (Per AI call):
```json
{
  "timestamp": "2025-10-21T04:30:00Z",
  "event": "ai_call_success",
  "symbol": "EURUSD",
  "session": "LONDON",
  "decision_type": "BUY",
  "latency_ms": 245,
  "ai_confidence": 0.75,
  "composite_score": 0.71,
  "final_score": 0.73,
  "reasoning": "Strong OB with rejection confirmation",
  "key_factors": ["rejection_confirmed", "ema_aligned"],
  "fallback_used": false,
  "model": "llama2:7b",
  "prompt_version": "v1.0"
}
```

**`logs/ai_daily_summary.jsonl`** (Per session, end of day):
```json
{
  "timestamp": "2025-10-21T23:59:59Z",
  "event": "ai_daily_summary",
  "date": "2025-10-21",
  "session": "LONDON",
  "metrics": {
    "ai_calls_total": 45,
    "ai_calls_success": 43,
    "ai_calls_timeout": 1,
    "ai_calls_error": 1,
    "fallback_used_count": 2,
    "avg_latency_ms": 248,
    "p95_latency_ms": 450,
    "p99_latency_ms": 650
  },
  "decisions_generated": 45,
  "decisions_executed": 42,
  "decisions_rejected_by_ai": 3,
  "avg_ai_confidence": 0.72,
  "win_rate": 0.64,
  "avg_rr": 1.73,
  "model": "llama2:7b"
}
```

**Log Rotation**:
```python
import logging.handlers

ai_call_handler = logging.handlers.RotatingFileHandler(
    filename="logs/ai_calls.jsonl",
    maxBytes=100 * 1024 * 1024,  # 100 MB
    backupCount=10
)

ai_summary_handler = logging.handlers.RotatingFileHandler(
    filename="logs/ai_daily_summary.jsonl",
    maxBytes=50 * 1024 * 1024,  # 50 MB
    backupCount=30  # Keep 1 month
)
```

---

### 6️⃣ Versioning: Model, Version, Prompt Hash

**In `system.json`**:
```json
{
  "ai": {
    "versioning": {
      "model_name": "llama2",
      "model_version": "7b",
      "model_checkpoint": "2024-10-01",
      "prompt_hash": "sha256_abc123def456...",
      "prompt_version": "v1.0",
      "prompt_file": "prompts/llama2_v1.0.txt",
      "config_hash": "sha256_xyz789...",
      "deployed_timestamp": "2025-10-21T04:30:00Z"
    }
  }
}
```

**Prompt File** (`prompts/llama2_v1.0.txt`):
```
You are a professional forex trader analyzing trading signals.

Context:
- Structure Type: {structure_type}
- Quality Score: {quality_score}
- Composite Score: {composite_score}
- EMA Alignment: {ema_alignment}
- ATR Value: {atr_value}
- Session: {session_name}
- Recent Win Rate: {recent_win_rate}

Decision:
- Type: {decision_type}
- Entry: {entry_price}
- SL: {stop_loss}
- TP: {take_profit}
- RR: {risk_reward_ratio}

Analyze this signal and provide:
1. Confidence score (0-1)
2. Key factors supporting/opposing
3. Brief reasoning

Output JSON:
{
  "confidence": <float 0-1>,
  "reasoning": "<string>",
  "key_factors": ["<factor1>", "<factor2>"]
}
```

**Version Tracking**:
```python
# In pipeline.py, __init__()
self.ai_version = self.ai_config.get('versioning', {})

# Log on startup
logger.info("ai_initialized", extra={
    "model_name": self.ai_version['model_name'],
    "prompt_version": self.ai_version['prompt_version'],
    "prompt_hash": self.ai_version['prompt_hash']
})

# Include in every AI call log
self._log_ai_call(
    event="ai_call_success",
    ...,
    model=self.ai_version['model_name'],
    prompt_version=self.ai_version['prompt_version']
)
```

---

**Status**: Part 1 Complete — Continue to Part 2 for Safety & Testing, Data & Learning Loop
