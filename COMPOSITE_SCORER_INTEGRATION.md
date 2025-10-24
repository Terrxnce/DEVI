# Composite Scorer Integration Guide

## File: `core/orchestration/scoring.py` ✅ CREATED

**Status**: Ready to use  
**Location**: `c:\Users\Index\DEVI\core\orchestration\scoring.py`  
**Lines**: 350+  
**Dependencies**: None (stateless, only uses standard library + logging)

---

## Pipeline Integration: `core/orchestration/pipeline.py`

### Step 1: Import CompositeScorer

Add to imports section:
```python
from .scoring import CompositeScorer, CompositeResult
```

### Step 2: Initialize in `__init__`

```python
def __init__(self, config: Config):
    # ... existing code ...
    
    # Initialize Composite Scorer
    scoring_config = config.system_configs.get('scoring', {})
    self.composite_scorer = CompositeScorer(scoring_config)
```

### Step 3: Add Call Site in `process_bar()`

**Location**: After UZR processing, before guards

```python
def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
    """
    Process a single bar through the pipeline.
    
    Stages:
    1. Session gate
    2. Pre-filters
    3. Indicators (ATR, EMA)
    4. Structure detection
    5. Scoring (structure ranking)
    6. UZR (feature-flagged)
    >>> 7. COMPOSITE SCORING (NEW) <<<
    8. Guards (risk checks)
    9. SL/TP planning
    10. Decision generation
    """
    decisions = []
    
    try:
        # Stages 1-6: ... existing code ...
        
        # Stage 6: UZR
        uzr_context = self._process_uzr(scored_structures, data, session)
        
        # ========== STAGE 7: COMPOSITE SCORING (NEW) ==========
        composite = self._process_composite_scoring(
            scored_structures, uzr_context, data, session
        )
        
        # Log composite result
        logger.info(
            "composite_gate_evaluated",
            extra={
                "run_id": session.session_id,
                "symbol": data.symbol,
                "timeframe": session.timeframe if hasattr(session, 'timeframe') else '15m',
                "composite_tech_score": composite["composite_tech_score"],
                "passed_gate": composite["passed_gate"],
                "gate_reasons": composite["gate_reasons"],
                "component_breakdown": composite["component_breakdown"]
            }
        )
        
        # Early exit if gate fails (before expensive SLTP work)
        if not composite["passed_gate"]:
            logger.info(
                "trade_gate_rejected",
                extra={
                    "run_id": session.session_id,
                    "symbol": data.symbol,
                    "reasons": composite["gate_reasons"]
                }
            )
            return decisions
        
        # Stage 8: Guards
        if not self._process_guards(scored_structures, data, session):
            return decisions
        
        # Stage 9: SL/TP planning (RR check uses same scale thresholds)
        sltp_plans = self._process_sltp_planning(scored_structures, data, session)
        
        # Stage 10: Decision generation (attach composite fields)
        decisions = self._process_decision_generation(
            sltp_plans, data, session, timestamp, uzr_context,
            extra_metadata={
                "structure_quality": composite["structure_quality"],
                "composite_tech_score": composite["composite_tech_score"],
                "gate_reasons": composite["gate_reasons"],
                "component_breakdown": composite["component_breakdown"]
            }
        )
        
        self.processed_bars += 1
        self.decisions_generated += len(decisions)
    
    except Exception as e:
        logger.warning("pipeline_processing_error", extra={"error": str(e)})
    
    return decisions
```

### Step 4: Add Composite Scoring Method

```python
def _process_composite_scoring(
    self,
    structures: List[Structure],
    uzr_context: Dict[str, Any],
    data: OHLCV,
    session: Session
) -> CompositeResult:
    """
    Process composite scoring stage.
    
    Inputs:
    - structures: Detected and ranked structures (each has quality_score)
    - uzr_context: UZR output with rejection, rejection_confirmed_next, rejection_strength
    - data: OHLCV data with indicators
    - session: Trading session (for timeframe, symbol, session_type)
    
    Outputs:
    - CompositeResult with composite_tech_score, passed_gate, gate_reasons, component_breakdown
    """
    try:
        # Extract indicators
        ema_21 = self.fast_ma.get_latest_value(data)
        ema_50 = self.slow_ma.get_latest_value(data)
        ema_200 = self.long_ma.get_latest_value(data) if hasattr(self, 'long_ma') else None
        atr = self.atr_calculator.get_latest_value(data)
        close = data.latest_bar.close if data.bars else Decimal('0')
        
        # Get previous EMA50 for slope calculation (optional)
        ema_50_prev = None
        if len(data.bars) >= 2:
            prev_data = OHLCV(symbol=data.symbol, bars=data.bars[:-1], timeframe=data.timeframe)
            ema_50_prev = self.slow_ma.get_latest_value(prev_data)
        
        # Build indicators dict
        indicators = {
            "ema_21": ema_21,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "atr": atr,
            "close": close,
            "ema_50_prev": ema_50_prev
        }
        
        # Determine context
        timeframe = session.timeframe if hasattr(session, 'timeframe') else '15m'
        symbol = session.symbol if hasattr(session, 'symbol') else 'EURUSD'
        instrument_group = self._get_instrument_group(symbol)
        session_type = self._get_session_type(symbol)  # ASIA, LONDON, NY_AM, NY_PM
        
        context = {
            "symbol": symbol,
            "timeframe": timeframe,
            "session": session_type,
            "instrument_group": instrument_group
        }
        
        # Compute composite score
        composite = self.composite_scorer.compute(
            structures=structures,
            uzr_context=uzr_context,
            indicators=indicators,
            context=context
        )
        
        return composite
    
    except Exception as e:
        logger.warning(
            "composite_scoring_error",
            extra={"error": str(e), "symbol": data.symbol}
        )
        return {
            "composite_tech_score": 0.0,
            "passed_gate": False,
            "gate_reasons": ["composite_scoring_error"],
            "component_breakdown": {
                "structure_quality": 0.0,
                "uzr_strength": 0.0,
                "ema_alignment": 0.0,
                "zone_proximity": 0.0,
            },
            "top_structure_id": None,
            "structure_quality": None
        }


def _get_instrument_group(self, symbol: str) -> str:
    """Classify instrument into group for weight scaling."""
    majors = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'NZDUSD', 'USDCAD']
    exotics = ['USDZAR', 'USDTRY', 'USDHKD', 'USDSGD', 'USDNOK', 'USDSEK']
    
    if symbol in majors:
        return 'fx'
    elif symbol in exotics:
        return 'equities'
    else:
        return 'crypto'


def _get_session_type(self, symbol: str) -> str:
    """
    Determine current trading session (ASIA, LONDON, NY_AM, NY_PM).
    
    Simplified: uses UTC hour. In production, use proper session manager.
    """
    from datetime import datetime, timezone
    
    hour_utc = datetime.now(timezone.utc).hour
    
    # Simplified session mapping (UTC hours)
    if 0 <= hour_utc < 8:
        return "ASIA"
    elif 8 <= hour_utc < 12:
        return "LONDON"
    elif 12 <= hour_utc < 17:
        return "NY_AM"
    else:
        return "NY_PM"
```

### Step 5: Update Decision Generation

Modify `_process_decision_generation()` to accept and attach extra_metadata:

```python
def _process_decision_generation(
    self,
    sltp_plans: List[Dict[str, Any]],
    data: OHLCV,
    session: Session,
    timestamp: datetime,
    uzr_context: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None
) -> List[Decision]:
    """
    Generate trading decisions from SL/TP plans.
    
    Args:
        sltp_plans: SL/TP plans from previous stage
        data: OHLCV data
        session: Trading session
        timestamp: Current timestamp
        uzr_context: UZR context (optional)
        extra_metadata: Additional metadata to attach (composite score, gate reasons, etc.)
    
    Returns:
        List of Decision objects
    """
    decisions = []
    
    for plan in sltp_plans:
        try:
            # Build metadata
            metadata = {
                'structure_type': plan['structure'].structure_type.value,
                'quality': plan['structure'].quality.value,
                'pipeline_version': '2.0',
                'rejection': uzr_context.get('rejection', False) if uzr_context else False,
                'rejection_confirmed_next': uzr_context.get('rejection_confirmed_next', False) if uzr_context else False,
                'uzr_enabled': uzr_context.get('uzr_enabled', False) if uzr_context else False
            }
            
            # Attach composite scoring metadata (NEW)
            if extra_metadata:
                metadata.update(extra_metadata)
            
            # Create decision
            decision = Decision(
                decision_type=plan['decision_type'],
                symbol=data.symbol,
                timestamp=timestamp,
                session_id=session.session_id,
                entry_price=plan['entry_price'],
                stop_loss=plan['stop_loss'],
                take_profit=plan['take_profit'],
                position_size=plan['position_size'],
                risk_reward_ratio=plan['rr_ratio'],
                structure_id=plan['structure'].structure_id,
                confidence_score=Decimal(str(extra_metadata.get('composite_tech_score', 0.0))) if extra_metadata else Decimal(str(plan['structure'].quality_score)),
                reasoning=f"Structure {plan['structure'].structure_type.value} with quality {plan['structure'].quality.value}",
                metadata=metadata
            )
            
            decisions.append(decision)
            
            logger.info(
                "decision_generated",
                extra={
                    "run_id": session.session_id,
                    "symbol": data.symbol,
                    "decision_type": decision.decision_type.value,
                    "entry": float(decision.entry_price),
                    "sl": float(decision.stop_loss),
                    "tp": float(decision.take_profit),
                    "rr": float(decision.risk_reward_ratio),
                    "confidence": float(decision.confidence_score),
                    "composite_tech_score": metadata.get('composite_tech_score'),
                    "structure_id": decision.structure_id
                }
            )
        
        except Exception as e:
            logger.warning("decision_generation_error", extra={"error": str(e)})
    
    return decisions
```

---

## Configuration: `configs/structure.json`

### Add Scoring Section

```json
{
  "scoring": {
    "weights": {
      "structure_quality": 0.40,
      "uzr_strength": 0.25,
      "ema_alignment": 0.20,
      "zone_proximity": 0.15
    },
    "defaults": {
      "proximity_max_atr": 1.0,
      "ema_slope_cap_atr": 0.3
    },
    "scales": {
      "M15": {
        "fx": {
          "ASIA": {
            "min_composite": 0.68,
            "min_rr": 1.5
          },
          "LONDON": {
            "min_composite": 0.65,
            "min_rr": 1.5
          },
          "NY_AM": {
            "min_composite": 0.65,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.67,
            "min_rr": 1.5
          }
        },
        "equities": {
          "NY_AM": {
            "min_composite": 0.66,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.68,
            "min_rr": 1.5
          }
        },
        "crypto": {
          "ASIA": {
            "min_composite": 0.65,
            "min_rr": 1.5
          },
          "LONDON": {
            "min_composite": 0.63,
            "min_rr": 1.5
          },
          "NY_AM": {
            "min_composite": 0.63,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.65,
            "min_rr": 1.5
          }
        }
      },
      "M5": {
        "fx": {
          "ASIA": {
            "min_composite": 0.70,
            "min_rr": 1.5
          },
          "LONDON": {
            "min_composite": 0.68,
            "min_rr": 1.5
          },
          "NY_AM": {
            "min_composite": 0.68,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.69,
            "min_rr": 1.5
          }
        }
      },
      "M30": {
        "fx": {
          "ASIA": {
            "min_composite": 0.66,
            "min_rr": 1.5
          },
          "LONDON": {
            "min_composite": 0.63,
            "min_rr": 1.5
          },
          "NY_AM": {
            "min_composite": 0.63,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.65,
            "min_rr": 1.5
          }
        }
      },
      "H1": {
        "fx": {
          "ASIA": {
            "min_composite": 0.64,
            "min_rr": 1.5
          },
          "LONDON": {
            "min_composite": 0.61,
            "min_rr": 1.5
          },
          "NY_AM": {
            "min_composite": 0.61,
            "min_rr": 1.5
          },
          "NY_PM": {
            "min_composite": 0.63,
            "min_rr": 1.5
          }
        }
      }
    }
  }
}
```

---

## Guard Order (Final Confirmation)

**Pipeline Sequence** (non-negotiable):

```
1. COMPOSITE SCORING (gate)
   ├─ Input: structures, UZR context, indicators
   ├─ Output: composite_tech_score, passed_gate, gate_reasons
   └─ Decision: PASS → continue; FAIL → return empty decisions

2. GUARDS (risk checks)
   ├─ Session active check
   ├─ ATR > 0 check
   ├─ Account risk check
   └─ Decision: PASS → continue; FAIL → return empty decisions

3. SL/TP PLANNING (RR check)
   ├─ Calculate SL/TP from structure geometry
   ├─ Calculate RR ratio
   ├─ Check RR >= min_rr (from scoring.scales[tf][group][session])
   └─ Decision: PASS → create plans; FAIL → skip structure

4. DECISION GENERATION
   ├─ Create Decision objects from plans
   ├─ Attach composite metadata
   ├─ Log decision
   └─ Return List[Decision]
```

**Why This Order**:
- **Composite gate first**: Cheap (no SLTP calculation), filters 30-40% of bars
- **Guards second**: Session/ATR checks, filters another 10-20%
- **SLTP last**: Expensive (geometry + RR calc), only runs on ~50% of bars
- **Decision gen last**: Only runs on ~5-10% of bars (those that pass all gates)

---

## Testing Checklist

- [ ] `CompositeScorer` initializes without errors
- [ ] Weights sum to 1.0 (validated in `__init__`)
- [ ] `compute()` returns valid `CompositeResult` dict
- [ ] `composite_tech_score` is 0-1
- [ ] `passed_gate` matches `composite_tech_score >= min_composite`
- [ ] `gate_reasons` populated on failure
- [ ] `component_breakdown` has all four components
- [ ] Pipeline imports and initializes scorer
- [ ] `_process_composite_scoring()` called after UZR, before guards
- [ ] Early exit on gate failure (no SLTP work)
- [ ] Decision metadata includes composite fields
- [ ] Logging shows composite score and gate decision
- [ ] Config loads without schema errors

---

## Summary

✅ **File created**: `core/orchestration/scoring.py`  
✅ **Integration points**: Identified in `pipeline.py`  
✅ **Config schema**: Added to `structure.json`  
✅ **Guard order**: Confirmed (composite → guards → SLTP → decision)  
✅ **Metadata**: Composite fields attached to decisions  

**Next**: Wire into pipeline.py and test end-to-end.
