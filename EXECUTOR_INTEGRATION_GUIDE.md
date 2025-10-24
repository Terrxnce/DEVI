# MT5 Executor Integration Guide

## Overview

The MT5 Executor validates order payloads against broker rules in dry-run mode before any live execution. This guide shows how to integrate it into the pipeline.

---

## Step 1: Add Execution Config to `configs/structure.json`

```json
{
  "execution": {
    "enabled": true,
    "mode": "dry-run",
    "min_rr": 1.5,
    "price_side": {
      "BUY": "ASK",
      "SELL": "BID"
    },
    "emergency_close": {
      "deviation": 20,
      "type_filling": "IOC",
      "max_retries": 3
    }
  }
}
```

**Config Fields**:
- `enabled`: Enable/disable executor
- `mode`: `"dry-run"` (validate only), `"paper"` (paper trading), `"live"` (real trades)
- `min_rr`: Minimum risk-reward ratio (default 1.5)
- `price_side`: Which price to use for entry (ASK for BUY, BID for SELL)
- `emergency_close`: Settings for emergency close orders (deviation, filling type, retries)

---

## Step 2: Import and Initialize in `pipeline.py`

```python
from .execution.mt5_executor import MT5Executor, BrokerSymbolInfo

class TradingPipeline:
    def __init__(self, config: Dict, logger: logging.Logger):
        # ... existing code ...
        
        # Initialize executor
        exec_config = config.system_configs.get("execution", {})
        self.executor = MT5Executor(exec_config, logger)
        
        # Register broker symbol info (from MT5 or config)
        # Example: EURUSD with typical broker constraints
        self._register_broker_symbols()
    
    def _register_broker_symbols(self) -> None:
        """Register broker symbol constraints."""
        # TODO: Fetch from MT5 or load from config
        # Example for EURUSD:
        eurusd_info = BrokerSymbolInfo(
            symbol="EURUSD",
            bid=1.0950,
            ask=1.0952,
            point=0.00001,
            digits=5,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            min_stop_distance=50,  # 50 points
            max_stop_distance=5000,  # 5000 points
            spread=2.0  # 2 points
        )
        self.executor.register_symbol_info("EURUSD", eurusd_info)
```

---

## Step 3: Call Executor After Decision Generation

**Location**: `pipeline.py` → `process_bar()` method, after decisions are generated

```python
def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
    # ... existing pipeline stages ...
    
    # Decision generation
    decisions = self._generate_decisions(scored_structures, uzr_context, data, session)
    
    # ✅ EXECUTE ORDERS (dry-run or live)
    if self.executor.enabled and decisions:
        for decision in decisions:
            execution_result = self.executor.execute_order(
                symbol=data.symbol,
                order_type=decision.type,  # "BUY" or "SELL"
                volume=decision.volume,
                entry_price=decision.entry_price,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                comment=f"DEVI_{decision.origin_structure_type}_{session.name}",
                magic=self._generate_magic_number(data.symbol, session)
            )
            
            # Log execution result
            self._log_execution_result(execution_result, decision)
    
    return decisions
```

---

## Step 4: Helper Methods for Pipeline

Add these helper methods to `TradingPipeline`:

```python
def _generate_magic_number(self, symbol: str, session) -> int:
    """
    Generate unique magic number for order tracking.
    Format: SSYYMMDDHH (session + date + hour)
    """
    from datetime import datetime
    now = datetime.utcnow()
    session_code = {"ASIA": 1, "LONDON": 2, "NY_AM": 3, "NY_PM": 4}.get(session.name, 0)
    magic = (session_code * 1000000000 +
             now.year % 100 * 10000000 +
             now.month * 100000 +
             now.day * 1000 +
             now.hour)
    return magic

def _log_execution_result(self, result, decision) -> None:
    """Log execution result with full details."""
    if result.success:
        self.logger.info("order_sent", extra={
            "symbol": result.symbol,
            "type": result.order_type,
            "volume": result.volume,
            "entry": result.entry_price,
            "sl": result.stop_loss,
            "tp": result.take_profit,
            "rr": result.rr,
            "mode": self.executor.mode.value,
        })
    else:
        self.logger.warning("order_blocked", extra={
            "symbol": result.symbol,
            "type": result.order_type,
            "volume": result.volume,
            "entry": result.entry_price,
            "sl": result.stop_loss,
            "tp": result.take_profit,
            "rr": result.rr,
            "errors": result.validation_errors,
            "mode": self.executor.mode.value,
        })
```

---

## Step 5: Session Close — Log Dry-Run Summary

**Location**: `pipeline.py` → `finalize_session()` method

```python
def finalize_session(self, session_name: str) -> None:
    """Call at session close (e.g., 17:00 UTC for LONDON)."""
    
    # ... existing session finalization ...
    
    # Log executor dry-run summary
    if self.executor.enabled and self.executor.mode.value == "dry-run":
        self.executor.log_dry_run_summary()
```

---

## Step 6: Broker Symbol Info — Load from MT5 or Config

### Option A: Load from MT5 at Runtime

```python
import MetaTrader5 as mt5

def _register_broker_symbols_from_mt5(self, symbols: List[str]) -> None:
    """Fetch broker constraints from MT5."""
    if not mt5.initialize():
        self.logger.error("MT5 initialization failed")
        return
    
    for symbol in symbols:
        info = mt5.symbol_info(symbol)
        if info:
            broker_info = BrokerSymbolInfo(
                symbol=symbol,
                bid=info.bid,
                ask=info.ask,
                point=info.point,
                digits=info.digits,
                volume_min=info.volume_min,
                volume_max=info.volume_max,
                volume_step=info.volume_step,
                min_stop_distance=info.trade_stops_level,
                max_stop_distance=info.trade_stops_level * 100,  # Estimate
                spread=info.spread
            )
            self.executor.register_symbol_info(symbol, broker_info)
```

### Option B: Load from Config File

Create `configs/broker_symbols.json`:

```json
{
  "symbols": {
    "EURUSD": {
      "bid": 1.0950,
      "ask": 1.0952,
      "point": 0.00001,
      "digits": 5,
      "volume_min": 0.01,
      "volume_max": 100.0,
      "volume_step": 0.01,
      "min_stop_distance": 50,
      "max_stop_distance": 5000,
      "spread": 2.0
    },
    "GBPUSD": {
      "bid": 1.2650,
      "ask": 1.2652,
      "point": 0.0001,
      "digits": 4,
      "volume_min": 0.01,
      "volume_max": 100.0,
      "volume_step": 0.01,
      "min_stop_distance": 50,
      "max_stop_distance": 5000,
      "spread": 2.0
    }
  }
}
```

Then load in pipeline:

```python
import json

def _register_broker_symbols_from_config(self, config_path: str) -> None:
    """Load broker constraints from config file."""
    with open(config_path, 'r') as f:
        broker_config = json.load(f)
    
    for symbol, info_dict in broker_config.get("symbols", {}).items():
        broker_info = BrokerSymbolInfo(**info_dict)
        self.executor.register_symbol_info(symbol, broker_info)
```

---

## Dry-Run Workflow

### 1. Backtest in Dry-Run Mode

```bash
# Run backtest with dry-run executor
python scripts/backtest.py --config configs/structure.json --mode dry-run --symbol EURUSD --start 2025-01-01 --end 2025-10-20
```

**Expected Output**:
- Per-bar: `order_validation_passed` or `order_validation_failed` events
- Session close: `dry_run_summary` with pass rate
- Log file: `logs/pipeline.json` with full order payloads

**Success Criteria**:
- Pass rate ≥95% (most orders valid)
- 0 validation errors for valid orders
- All RR ≥1.5
- All SL/TP distances within broker limits

### 2. Run Live in Dry-Run for 1 Week

```bash
# Deploy with dry-run mode enabled
# No real trades, just logs
# Monitor: pass rate, validation errors, RR distribution
```

**Daily Checklist**:
- [ ] Check `dry_run_summary` (pass rate ≥95%)
- [ ] Review `order_validation_failed` events (if any)
- [ ] Verify all RR ≥1.5
- [ ] Check for any SL/TP distance violations
- [ ] Monitor execution latency (should be <1ms)

### 3. Validate & Switch to Paper/Live

Once dry-run shows 0 validation errors for 1 week:

```json
{
  "execution": {
    "mode": "paper"  // or "live"
  }
}
```

---

## Expected Log Output

### Order Validation Passed (Dry-Run)

```json
{
  "timestamp": "2025-10-21 02:30:15,123",
  "level": "INFO",
  "event": "order_validation_passed",
  "mode": "dry-run",
  "symbol": "EURUSD",
  "type": "BUY",
  "volume": 0.5,
  "entry": 1.0950,
  "sl": 1.0920,
  "tp": 1.0995,
  "rr": 1.5,
  "comment": "DEVI_OB_LONDON"
}
```

### Order Validation Failed (Dry-Run)

```json
{
  "timestamp": "2025-10-21 02:30:16,456",
  "level": "WARNING",
  "event": "order_validation_failed",
  "mode": "dry-run",
  "symbol": "EURUSD",
  "type": "SELL",
  "volume": 0.5,
  "entry": 1.0950,
  "sl": 1.0980,
  "tp": 1.0900,
  "rr": 1.0,
  "errors": [
    "RR 1.0 < min 1.5",
    "SL distance 300 pts > max 5000 pts"
  ],
  "comment": "DEVI_FVG_ASIA"
}
```

### Dry-Run Summary (Session Close)

```json
{
  "timestamp": "2025-10-21 17:00:00,000",
  "level": "INFO",
  "event": "dry_run_summary",
  "total_orders": 45,
  "passed": 43,
  "failed": 2,
  "pass_rate": "95.6%"
}
```

---

## Metrics to Track (Week 1 Dry-Run)

| Metric | Target | Action if Miss |
|--------|--------|-----------------|
| Pass rate | ≥95% | Review failed orders, adjust SL/TP logic |
| RR distribution | All ≥1.5 | Check SL/TP planning |
| SL distance | Within limits | Verify broker constraints |
| TP distance | Within limits | Verify broker constraints |
| Volume validation | 100% pass | Check volume step logic |
| Execution latency | <1ms | Optimize validation |

---

## Troubleshooting

### High Failure Rate (Pass Rate <95%)

**Check**:
1. Are broker symbol constraints correct? (min_stop_distance, volume_step)
2. Is SL/TP planning generating valid distances?
3. Are RR calculations correct?

**Fix**:
1. Verify broker constraints in `configs/broker_symbols.json`
2. Review SL/TP planning logic in pipeline
3. Adjust min_rr if needed (e.g., 1.4 instead of 1.5)

### Validation Errors in Live Dry-Run

**Check**:
1. Did broker constraints change? (spread, min_stop_distance)
2. Is market volatility affecting SL/TP distances?

**Fix**:
1. Update broker symbol info from MT5
2. Adjust SL/TP planning for current volatility
3. Review failed orders in logs

### Execution Latency High

**Check**:
1. Is validation logic slow? (many checks)
2. Is logging overhead high?

**Fix**:
1. Profile validation logic
2. Cache broker symbol info
3. Batch log writes

---

## Next Steps

1. **Wire executor into pipeline.py** (15 min)
2. **Load broker symbol constraints** (10 min)
3. **Run backtest in dry-run mode** (30 min)
4. **Deploy live in dry-run for 1 week** (ongoing)
5. **Validate 0 errors, then switch to paper/live** (1 week)

Once dry-run is validated, integrate AI decision layer (LLaMA reasoning).
