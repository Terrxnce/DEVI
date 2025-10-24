# DEVI 2.0 Implementation Roadmap — Code References & Next Steps

## Current State (90% Complete)

### ✅ Completed Components

| Component | File | Status | Lines |
|-----------|------|--------|-------|
| **Core Models** | `core/models/structure.py` | ✅ Complete | 260 |
| | `core/models/decision.py` | ✅ Complete | 172 |
| | `core/models/ohlcv.py` | ✅ Complete | ~150 |
| | `core/models/session.py` | ✅ Complete | ~100 |
| **ATR Utility** | `core/indicators/atr.py` | ✅ Complete | ~80 |
| **FVG Detector** | `core/structure/fair_value_gap.py` | ✅ Complete | ~400 |
| **OB Detector** | `core/structure/order_block.py` | ✅ Complete | ~450 |
| **BOS Detector** | `core/structure/break_of_structure.py` | ✅ Complete | ~350 |
| **Sweep Detector** | `core/structure/sweep.py` | ✅ Complete | ~400 |
| **UZR Detector** | `core/structure/rejection.py` | ✅ Complete | ~600 |
| **Engulfing Detector** | `core/structure/engulfing.py` | ✅ Complete | 600 |
| **Structure Manager** | `core/structure/manager.py` | ✅ Complete | 81 |
| **Pipeline Orchestrator** | `core/orchestration/pipeline.py` | ✅ Complete | 400 |
| **Config System** | `configs/structure.json` | ✅ Complete | 120 |
| **Unit Tests** | `tests/unit/` | ✅ Complete | 2000+ |
| **Documentation** | Various `.md` files | ✅ Complete | 1000+ |

### 🚧 In Progress / Pending

| Component | File | Status | Priority | Est. Lines |
|-----------|------|--------|----------|-----------|
| **Composite Score** | `core/orchestration/scoring.py` | 🚧 Proposed | HIGH | 200 |
| **Schema Validation** | `configs/structure.schema.json` | ⏳ Pending | MEDIUM | 300 |
| **AI Integration Hook** | `core/ai/reasoning_hook.py` | ⏳ Proposed | HIGH | 300 |
| **MT5 Execution** | `core/execution/mt5_executor.py` | ⏳ Proposed | HIGH | 400 |
| **SL/TP Enhancement** | `core/risk/sltp_calculator.py` | ⏳ Proposed | MEDIUM | 250 |
| **GUI Dashboard** | `gui/dashboard.py` | ⏳ Proposed | LOW | 500+ |

---

## Phase 1: Composite Confidence Score (Recommended Next)

### Objective
Replace per-structure quality with per-bar composite decision confidence that combines:
- Structure quality (40%)
- UZR rejection strength (25%)
- EMA alignment (20%)
- Zone proximity (15%)

### Implementation Plan

**File**: `core/orchestration/scoring.py` (NEW)

```python
class CompositeScorer:
    """
    Calculates per-bar composite confidence score.
    
    Formula:
    confidence = 0.40 × structure_quality +
                 0.25 × uzr_strength +
                 0.20 × ema_alignment +
                 0.15 × zone_proximity
    """
    
    def __init__(self, weights: Dict[str, float]):
        self.weights = weights
    
    def calculate_confidence(self, structures: List[Structure], 
                           uzr_context: Dict, ema_scores: Dict,
                           zone_proximity: Dict) -> Decimal:
        """Calculate composite confidence for bar."""
        # Implementation
        pass
```

**Integration Point**: `core/orchestration/pipeline.py` → `_process_decision_generation()`

**Changes Required**:
1. Add CompositeScorer to pipeline __init__
2. Call after UZR processing, before decision generation
3. Use composite score as decision confidence_score
4. Add to config: `scoring_weights` section

**Config Addition** (structure.json):
```json
{
  "scoring": {
    "scoring_weights": {
      "structure_quality": 0.40,
      "uzr_strength": 0.25,
      "ema_alignment": 0.20,
      "zone_proximity": 0.15
    },
    "min_composite_threshold": 0.50
  }
}
```

**Tests Required**:
- Composite score in valid range (0-1)
- Weights sum to 1.0
- Deterministic across runs
- Proper weighting of components

---

## Phase 2: Schema Validation (Quick Win)

### Objective
Add JSON Schema validation to `configs/structure.schema.json` for config validation on load.

### Implementation Plan

**File**: `configs/structure.schema.json` (NEW)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DEVI 2.0 Structure Configuration",
  "type": "object",
  "properties": {
    "structure_configs": {
      "type": "object",
      "properties": {
        "engulfing": {
          "type": "object",
          "properties": {
            "enabled": { "type": "boolean" },
            "atr_window": { "type": "integer", "minimum": 5 },
            "min_body_atr": { "type": "number", "minimum": 0.1 },
            "min_body_to_range": { "type": "number", "minimum": 0, "maximum": 1 },
            "weights": {
              "type": "object",
              "properties": {
                "body": { "type": "number", "minimum": 0, "maximum": 1 },
                "body_to_range": { "type": "number", "minimum": 0, "maximum": 1 },
                "follow_through": { "type": "number", "minimum": 0, "maximum": 1 },
                "context": { "type": "number", "minimum": 0, "maximum": 1 }
              },
              "required": ["body", "body_to_range", "follow_through", "context"]
            }
          },
          "required": ["enabled", "atr_window", "min_body_atr", "min_body_to_range"]
        }
      }
    },
    "quality_thresholds": {
      "type": "object",
      "properties": {
        "premium": { "type": "number", "minimum": 0, "maximum": 1 },
        "high": { "type": "number", "minimum": 0, "maximum": 1 },
        "medium": { "type": "number", "minimum": 0, "maximum": 1 },
        "low": { "type": "number", "minimum": 0, "maximum": 1 }
      }
    }
  }
}
```

**Integration**: `configs/config_loader.py`

```python
import jsonschema

def load_and_validate(config_path: str) -> Dict:
    with open(config_path) as f:
        config = json.load(f)
    
    with open('configs/structure.schema.json') as f:
        schema = json.load(f)
    
    jsonschema.validate(config, schema)
    return config
```

**Tests Required**:
- Valid config passes validation
- Invalid config raises error
- All detector configs validated

---

## Phase 3: AI Integration Hook

### Objective
Prepare pipeline output for LLaMA reasoning layer with structured payload.

### Implementation Plan

**File**: `core/ai/reasoning_hook.py` (NEW)

```python
class AIReasoningHook:
    """
    Prepares structured payload for AI reasoning layer.
    
    Input: Pipeline output (structures, indicators, UZR context)
    Output: JSON payload for LLaMA reasoning
    """
    
    def prepare_reasoning_input(self, data: OHLCV, structures: List[Structure],
                               uzr_context: Dict, indicators: Dict) -> Dict:
        """Prepare AI input payload."""
        return {
            "run_id": session.session_id,
            "symbol": data.symbol,
            "timeframe": "15m",
            "current_bar": {...},
            "indicators": {...},
            "structures": [...],
            "uzr_context": {...}
        }
    
    def parse_reasoning_output(self, ai_response: Dict) -> Dict:
        """Parse AI reasoning response."""
        return {
            "decision": ai_response.get("decision"),
            "confidence": ai_response.get("confidence"),
            "reasoning": ai_response.get("reasoning"),
            "risk_level": ai_response.get("risk_level")
        }
```

**Integration Point**: `core/orchestration/pipeline.py` → after decision generation

```python
# In process_bar()
decisions = self._process_decision_generation(...)

# AI Hook (new)
if self.ai_enabled:
    ai_input = self.ai_hook.prepare_reasoning_input(data, structures, uzr_context, indicators)
    ai_response = self.llama_client.reason(ai_input)
    ai_validation = self.ai_hook.parse_reasoning_output(ai_response)
    
    # Filter decisions based on AI validation
    decisions = [d for d in decisions if ai_validation.get("decision") == d.decision_type]
```

**Config Addition**:
```json
{
  "ai": {
    "enabled": false,
    "llama_endpoint": "http://localhost:8000",
    "model": "llama-2-7b",
    "temperature": 0.3,
    "max_tokens": 500
  }
}
```

**Tests Required**:
- Payload structure correct
- All required fields present
- Deterministic payload generation
- Response parsing works

---

## Phase 4: MT5 Execution Wiring

### Objective
Connect Decision objects to MT5 order placement via API.

### Implementation Plan

**File**: `core/execution/mt5_executor.py` (NEW)

```python
class MT5Executor:
    """
    Executes trading decisions on MT5 platform.
    
    Subscribes to Decision output from pipeline.
    Converts to MT5 order format and executes.
    """
    
    def __init__(self, mt5_config: Dict):
        self.mt5 = mt5.MT5(mt5_config)
        self.pending_decisions: List[Decision] = []
    
    def execute_decision(self, decision: Decision) -> bool:
        """Execute a single decision on MT5."""
        if decision.status != DecisionStatus.PENDING:
            return False
        
        order = self._convert_to_mt5_order(decision)
        result = self.mt5.send_order(order)
        
        logger.info("mt5_order_executed", extra={
            "decision_id": decision.structure_id,
            "order_ticket": result.order,
            "status": result.retcode
        })
        
        return result.retcode == mt5.TRADE_RETCODE_DONE
    
    def _convert_to_mt5_order(self, decision: Decision) -> Dict:
        """Convert Decision to MT5 order format."""
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": decision.symbol,
            "volume": float(decision.position_size),
            "type": mt5.ORDER_TYPE_BUY if decision.is_long else mt5.ORDER_TYPE_SELL,
            "price": float(decision.entry_price),
            "sl": float(decision.stop_loss),
            "tp": float(decision.take_profit),
            "comment": f"DEVI2.0_{decision.structure_id[:20]}"
        }
```

**Integration Point**: `core/orchestration/pipeline.py` → after decision generation

```python
# In process_bar()
decisions = self._process_decision_generation(...)

# MT5 Execution (new)
if self.mt5_enabled:
    for decision in decisions:
        success = self.mt5_executor.execute_decision(decision)
        if success:
            logger.info("decision_executed", extra={"decision_id": decision.structure_id})
```

**Config Addition**:
```json
{
  "execution": {
    "enabled": false,
    "mt5": {
      "account": 123456,
      "password": "***",
      "server": "ICMarketsSC-Demo",
      "timeout": 5000
    }
  }
}
```

**Tests Required**:
- Order conversion correct
- Connection to MT5 works
- Order execution logged
- Error handling (insufficient funds, etc.)

---

## Phase 5: SL/TP Enhancement

### Objective
Improve stop-loss and take-profit calculation with ATR buffers and structure geometry.

### Implementation Plan

**File**: `core/risk/sltp_calculator.py` (NEW)

```python
class SLTPCalculator:
    """
    Calculates stop-loss and take-profit levels.
    
    Uses structure geometry (OB mid/edge, FVG edges) + ATR buffers.
    Supports trailing stops.
    """
    
    def calculate_sltp(self, structure: Structure, entry_price: Decimal,
                      atr: Decimal, config: Dict) -> Tuple[Decimal, Decimal]:
        """Calculate SL and TP for structure."""
        
        if structure.structure_type == StructureType.ORDER_BLOCK:
            sl, tp = self._sltp_for_ob(structure, entry_price, atr, config)
        elif structure.structure_type == StructureType.FAIR_VALUE_GAP:
            sl, tp = self._sltp_for_fvg(structure, entry_price, atr, config)
        else:
            sl, tp = self._sltp_default(structure, entry_price, atr, config)
        
        return sl, tp
    
    def _sltp_for_ob(self, ob: Structure, entry: Decimal, atr: Decimal,
                    config: Dict) -> Tuple[Decimal, Decimal]:
        """SL/TP for Order Block."""
        sl_buffer = Decimal(str(config.get('sl_atr_buffer', 0.5))) * atr
        tp_buffer = Decimal(str(config.get('tp_atr_buffer', 1.0))) * atr
        
        if ob.direction == 'bullish':
            sl = ob.low_price - sl_buffer
            tp = ob.high_price + tp_buffer
        else:
            sl = ob.high_price + sl_buffer
            tp = ob.low_price - tp_buffer
        
        return sl, tp
    
    def _sltp_for_fvg(self, fvg: Structure, entry: Decimal, atr: Decimal,
                     config: Dict) -> Tuple[Decimal, Decimal]:
        """SL/TP for Fair Value Gap."""
        # Use FVG edges as TP, structure low/high as SL
        pass
```

**Integration Point**: `core/orchestration/pipeline.py` → `_process_sltp_planning()`

```python
def _process_sltp_planning(self, structures, data, session):
    plans = []
    for structure in structures:
        atr = self.atr_calculator.get_latest_value(data)
        sl, tp = self.sltp_calculator.calculate_sltp(structure, data.latest_bar.close, atr, self.config)
        
        # Validate R:R
        risk = abs(data.latest_bar.close - sl)
        reward = abs(tp - data.latest_bar.close)
        rr_ratio = reward / risk if risk > 0 else Decimal('0')
        
        if rr_ratio >= Decimal(self.config.get('min_rr_ratio', 1.5)):
            plans.append({...})
    
    return plans
```

**Config Addition**:
```json
{
  "risk": {
    "sl_atr_buffer": 0.5,
    "tp_atr_buffer": 1.0,
    "min_rr_ratio": 1.5,
    "trailing_stop_enabled": false,
    "trailing_stop_atr": 0.3
  }
}
```

**Tests Required**:
- SL below entry for long, above for short
- TP above entry for long, below for short
- R:R calculation correct
- ATR buffer applied correctly

---

## Phase 6: GUI Dashboard (Lower Priority)

### Objective
Real-time visualization of structures, lifecycle, decisions, and execution.

### Implementation Plan

**File**: `gui/dashboard.py` (NEW)

**Features**:
- Real-time structure detection display
- Lifecycle state transitions
- Decision generation and execution status
- Risk metrics (R:R, position size, account risk)
- Performance metrics (win rate, profit factor)

**Technology Stack** (Proposed):
- **Frontend**: React + TradingView Lightweight Charts
- **Backend**: FastAPI + WebSocket
- **Database**: SQLite (local) or PostgreSQL (cloud)

**Integration**: WebSocket feed from pipeline

---

## Testing Strategy

### Unit Tests (Current: 2000+ lines)

```bash
# Run all tests
python -m pytest tests/unit/ -v

# Run specific detector tests
python -m pytest tests/unit/test_engulfing_detector.py -v

# Run with coverage
python -m pytest tests/unit/ --cov=core --cov-report=html
```

### Integration Tests (Proposed)

```python
# tests/integration/test_pipeline_end_to_end.py
def test_full_pipeline_with_sample_data():
    """Test complete pipeline from OHLCV to Decision."""
    pipeline = TradingPipeline(config)
    data = load_sample_data('EURUSD_15m.csv')
    
    decisions = pipeline.process_bar(data, datetime.now())
    
    assert len(decisions) > 0
    assert all(d.status == DecisionStatus.PENDING for d in decisions)
    assert all(d.risk_reward_ratio >= 1.5 for d in decisions)
```

### Determinism Tests (Current: Verified)

```bash
# Verify identical runs produce identical results
python -m pytest tests/unit/ -k "determinism" -v
```

### Performance Tests (Proposed)

```python
# tests/performance/test_pipeline_speed.py
def test_pipeline_latency():
    """Measure pipeline latency per bar."""
    pipeline = TradingPipeline(config)
    data = load_sample_data('EURUSD_15m.csv')
    
    start = time.time()
    for bar in data.bars:
        pipeline.process_bar(data, datetime.now())
    elapsed = time.time() - start
    
    avg_latency = elapsed / len(data.bars)
    assert avg_latency < 0.005  # < 5ms per bar
```

---

## Deployment Checklist

- [ ] All unit tests passing (2000+)
- [ ] Integration tests passing
- [ ] Determinism verified (identical runs)
- [ ] Performance benchmarked (< 5ms per bar)
- [ ] Schema validation complete
- [ ] Documentation complete
- [ ] Code review completed
- [ ] Config defaults set
- [ ] Feature flags configured
- [ ] Logging verified (JSON only)
- [ ] Error handling tested
- [ ] Edge cases covered

---

## Timeline Estimate

| Phase | Effort | Timeline | Priority |
|-------|--------|----------|----------|
| **Phase 1: Composite Score** | 2-3 days | Week 1 | HIGH |
| **Phase 2: Schema Validation** | 1 day | Week 1 | MEDIUM |
| **Phase 3: AI Integration Hook** | 3-4 days | Week 2 | HIGH |
| **Phase 4: MT5 Execution** | 4-5 days | Week 2-3 | HIGH |
| **Phase 5: SL/TP Enhancement** | 2-3 days | Week 3 | MEDIUM |
| **Phase 6: GUI Dashboard** | 5-7 days | Week 4+ | LOW |
| **Testing & Validation** | 3-4 days | Ongoing | HIGH |
| **Total** | **20-27 days** | **~4 weeks** | |

---

## Success Criteria

✅ **Functionality**:
- All detectors working correctly
- Pipeline producing valid decisions
- AI reasoning integrated
- MT5 execution working

✅ **Quality**:
- All tests passing
- Determinism verified
- Performance < 5ms per bar
- Zero print statements (JSON logs only)

✅ **Observability**:
- Structured JSON logging for all events
- Correlation IDs (run_id, session_id)
- Lifecycle tracking
- Error tracking

✅ **Documentation**:
- Technical audit complete
- API documentation
- Configuration guide
- Deployment guide

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-20  
**Status**: Implementation Roadmap Ready ✅
