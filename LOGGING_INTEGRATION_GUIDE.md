# Logging Integration Guide

## Quick Start: Wire Helpers into Pipeline

### 1. Import Helpers (Top of `pipeline.py`)

```python
from .scoring_helpers import ema_alignment_score, zone_proximity_score
from .logging_utils import (
    log_gate_evaluation,
    log_decision,
    summarize_day,
    log_daily_summary,
    alert_on_drift,
)
```

---

## 2. Per-Bar Gate Evaluation Logging

**Location**: `pipeline.py` → `process_bar()` method, right after `CompositeScorer.compute()`

```python
def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
    # ... existing code ...
    
    # Composite scoring
    composite = self.composite_scorer.compute(
        structures=scored_structures,
        uzr_context=uzr_context,
        indicators=indicators,
        context={"session": session, "data": data}
    )
    
    # ✅ LOG GATE EVALUATION
    log_gate_evaluation(
        logger=self.logger,
        session_name=session.name,
        symbol=data.symbol,
        timeframe=data.timeframe,
        composite_score=composite["composite_tech_score"],
        passed_gate=composite["passed_gate"],
        component_breakdown=composite["component_breakdown"],
        gate_reasons=composite["gate_reasons"]
    )
    
    # Early exit if gate failed
    if not composite["passed_gate"]:
        return decisions
    
    # ... rest of pipeline ...
```

---

## 3. Per-Decision Logging

**Location**: `pipeline.py` → `_generate_decisions()` method, when creating each Decision

```python
def _generate_decisions(self, structures, uzr_context, data, session):
    decisions = []
    
    for structure in structures:
        # ... SL/TP planning, RR calculation ...
        
        decision = Decision(
            type=decision_type,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            # ... other fields ...
        )
        
        # ✅ LOG DECISION
        log_decision(
            logger=self.logger,
            decision_type=decision_type,
            rr=decision.rr,
            origin_structure_type=structure.type,
            quality_score=structure.quality_score,
            uzr_flags={
                "rejection": uzr_context.get("rejection", False),
                "rejection_confirmed_next": uzr_context.get("rejection_confirmed_next", False),
            }
        )
        
        decisions.append(decision)
    
    return decisions
```

---

## 4. Daily Summary Aggregation

**Location**: New method in `pipeline.py` or separate `monitoring.py`

```python
def finalize_session(self, session_name: str, gate_eval_logs: List[Dict]) -> None:
    """
    Call at session close (e.g., 17:00 UTC for LONDON).
    Aggregates gate_eval events and logs daily summary.
    
    Args:
        session_name: Session identifier (ASIA, LONDON, NY_AM, NY_PM)
        gate_eval_logs: List of gate_eval log dicts from the day
    """
    # Aggregate by session
    session_breakdown = summarize_day(gate_eval_logs)
    
    # Calculate RR statistics (from decision logs)
    rr_values = [d["rr"] for d in self.decision_logs if d.get("rr")]
    avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0.0
    median_rr = sorted(rr_values)[len(rr_values) // 2] if rr_values else 0.0
    
    # Count structures
    structure_counts = {
        "FVG": len([s for s in self.all_structures if s.type == "FVG"]),
        "OB": len([s for s in self.all_structures if s.type == "OB"]),
        "BOS": len([s for s in self.all_structures if s.type == "BOS"]),
        "Sweep": len([s for s in self.all_structures if s.type == "Sweep"]),
        "Rejection": len([s for s in self.all_structures if s.type == "Rejection"]),
        "Engulfing": len([s for s in self.all_structures if s.type == "Engulfing"]),
    }
    
    # ✅ LOG DAILY SUMMARY
    log_daily_summary(
        logger=self.logger,
        session_breakdown=session_breakdown,
        avg_rr=avg_rr,
        median_rr=median_rr,
        structure_counts=structure_counts
    )
    
    # ✅ CHECK FOR DRIFT
    if session_name in self.yesterday_avg_composite:
        alert_on_drift(
            logger=self.logger,
            today_avg=session_breakdown[session_name]["avg_composite"],
            yesterday_avg=self.yesterday_avg_composite[session_name],
            session=session_name,
            threshold=0.05
        )
    
    # Store for tomorrow's comparison
    self.yesterday_avg_composite[session_name] = session_breakdown[session_name]["avg_composite"]
```

---

## 5. EMA Alignment & Zone Proximity Helpers

**Location**: `CompositeScorer.compute()` in `scoring.py`

```python
from .scoring_helpers import ema_alignment_score, zone_proximity_score

def compute(self, structures, uzr_context, indicators, context):
    # ... existing code ...
    
    # ✅ EMA ALIGNMENT (using helper)
    ema_alignment = ema_alignment_score(
        ema21=indicators.get("ema21", 0),
        ema50=indicators.get("ema50", 0),
        ema200=indicators.get("ema200", 0),
        slope21=indicators.get("ema21_slope", 0),
        slope_min=self.defaults.get("ema_slope_min", 0.0)
    )
    
    # ✅ ZONE PROXIMITY (using helper)
    zone_proximity = zone_proximity_score(
        price=context["data"].close,
        zones=structures,  # OB + FVG structures
        atr=context["data"].atr,
        max_atr=self.defaults.get("proximity_max_atr", 2.0)
    )
    
    # ... rest of compute ...
```

---

## 6. Logger Configuration (One-Time Setup)

**Location**: `core/logging_config.py` (or similar)

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        # Merge extra fields
        if hasattr(record, '__dict__'):
            for key, value in record.__dict__.items():
                if key not in ('name', 'msg', 'args', 'created', 'filename', 'funcName', 
                              'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message',
                              'pathname', 'process', 'processName', 'relativeCreated', 'thread',
                              'threadName', 'exc_info', 'exc_text', 'stack_info'):
                    log_obj[key] = value
        return json.dumps(log_obj)

def setup_logger(name: str, log_file: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Console handler (JSON)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())
    logger.addHandler(console_handler)
    
    # File handler (JSON)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
    
    return logger

# Usage in pipeline.py
self.logger = setup_logger("devi_pipeline", log_file="logs/pipeline.json")
```

---

## 7. Monitoring Script (Optional)

**Location**: `scripts/monitor_live.py`

```python
import json
from pathlib import Path
from collections import defaultdict
from logging_utils import summarize_day, alert_on_drift

def monitor_live(log_file: str = "logs/pipeline.json"):
    """Read live logs and print metrics every hour."""
    
    gate_eval_logs = []
    decision_logs = []
    
    with open(log_file, 'r') as f:
        for line in f:
            try:
                log_obj = json.loads(line)
                if log_obj.get("event") == "gate_eval":
                    gate_eval_logs.append(log_obj)
                elif log_obj.get("event") == "decision":
                    decision_logs.append(log_obj)
            except json.JSONDecodeError:
                pass
    
    # Aggregate
    session_breakdown = summarize_day(gate_eval_logs)
    
    print("\n=== LIVE METRICS ===")
    for session, metrics in session_breakdown.items():
        print(f"\n{session}:")
        print(f"  Bars: {metrics['bars']}")
        print(f"  Pass-rate: {metrics['pass_rate']:.1%}")
        print(f"  Avg composite: {metrics['avg_composite']:.3f}")
        print(f"  Gated-in: {metrics['gated_in']}")
    
    # RR stats
    rr_values = [d["rr"] for d in decision_logs]
    if rr_values:
        print(f"\nRR Stats:")
        print(f"  Avg: {sum(rr_values)/len(rr_values):.2f}")
        print(f"  Median: {sorted(rr_values)[len(rr_values)//2]:.2f}")
        print(f"  ≥1.5: {sum(1 for r in rr_values if r >= 1.5) / len(rr_values):.1%}")

if __name__ == "__main__":
    monitor_live()
```

---

## 8. Integration Checklist

- [ ] Import helpers at top of `pipeline.py`
- [ ] Call `log_gate_evaluation()` after `CompositeScorer.compute()`
- [ ] Call `log_decision()` in `_generate_decisions()`
- [ ] Implement `finalize_session()` for daily summary
- [ ] Set up logger with JSON formatter
- [ ] Test warmup (first 50 bars) for structured logs only
- [ ] Verify no `print()` statements in logs
- [ ] Run determinism test (replay twice, compare logs)
- [ ] Deploy and monitor first 3 days

---

## 9. Expected Log Output

### Per-Bar Gate Eval
```json
{
  "timestamp": "2025-10-21 02:15:30,123",
  "level": "INFO",
  "event": "gate_eval",
  "session": "ASIA",
  "symbol": "EURUSD",
  "tf": "M15",
  "composite_tech_score": 0.71,
  "passed_gate": true,
  "component_breakdown": {
    "structure_quality": 0.74,
    "uzr_strength": 0.60,
    "ema_alignment": 0.70,
    "zone_proximity": 0.40
  },
  "gate_reasons": []
}
```

### Per-Decision
```json
{
  "timestamp": "2025-10-21 02:15:30,456",
  "level": "INFO",
  "event": "decision",
  "type": "BUY",
  "rr": 1.83,
  "origin_structure_type": "OB",
  "quality_score": 0.78,
  "uzr_flags": {
    "rejection": true,
    "rejection_confirmed_next": true
  }
}
```

### Daily Summary
```json
{
  "timestamp": "2025-10-21 17:00:00,000",
  "level": "INFO",
  "event": "daily_summary",
  "session_breakdown": {
    "ASIA": {
      "bars": 240,
      "gated_in": 18,
      "pass_rate": 0.075,
      "avg_composite": 0.71
    }
  },
  "avg_rr": 1.62,
  "median_rr": 1.58,
  "structure_counts": {
    "FVG": 45,
    "OB": 38,
    "BOS": 12,
    "Sweep": 8,
    "Rejection": 22,
    "Engulfing": 15
  }
}
```

---

## Done! 🚀

Your logging is now production-ready and 1:1 aligned with the Composite Scorer.
