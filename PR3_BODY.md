## Summary
PR3 introduces risk-based position sizing and a per-symbol open-risk cap:
- Size per trade from % of equity (defaults: per_trade_pct=0.25%).
- Enforce per-symbol open-risk cap (default: per_symbol_open_risk_cap_pct=0.75% of equity).
- Structured logs for observability, including `execution_sized` with risk metadata.

## Changes
- `core/orchestration/pipeline.py`:
  - Post-clamp SL distance → compute `stop_distance_points`.
  - Broker meta lookups (`point`, `contract_size`, `volume_step`, `volume_min/max`) with sane FX/XAU fallbacks.
  - Volume from risk budget → rounded down to `lot_step`, bounded by min/max.
  - Guards: `risk_too_small`, `risk_cap_hit`.
  - New INFO: `execution_sized` (includes `symbol`, `order_type`, `volume_rounded`, `risk`, `risk_budget`, `cap_budget`, `entry`, `sl`, `tp`).
- Keeps PR1/PR2: sessions/guards, volatility pause, circuit breaker. Planner is optional during PR3 validation (sizing path unaffected).

## Config keys
```json
"risk": {
  "per_trade_pct": 0.25,
  "per_symbol_open_risk_cap_pct": 0.75
}cd CD
```

## Validation (EURUSD, 100 bars, dry-run)
- risk_cap_hit (cap temporarily 0.10):
```json
{"timestamp": "2025-10-28T19:16:20.770262+00:00", "level": "INFO", "logger": "core.orchestration.pipeline", "message": "risk_cap_hit", "taskName": null, "session": null, "symbol": "EURUSD", "open_risk": 0.0, "new_trade_risk": 24.666999999997774, "cap_pct": 0.001, "equity": 10000.0}
```

- risk_too_small (per_trade_pct temporarily 0.01):
```json
{"timestamp": "2025-10-28T19:53:43.582478+00:00", "level": "INFO", "logger": "core.orchestration.pipeline", "message": "risk_too_small", "taskName": null, "session": null, "symbol": "EURUSD", "equity": 10000.0, "per_trade_pct": 0.0001, "min_lot": 0.01, "computed_volume": 0.009041591320071913}
```

- execution_sized (cap restored to 0.75):
```json
{"timestamp": "2025-10-28T19:56:47.778025+00:00", "level": "INFO", "logger": "core.orchestration.pipeline", "message": "execution_sized", "taskName": null, "symbol": "EURUSD", "order_type": "SELL", "volume_rounded": 0.34, "risk": {"new_trade_risk": 24.666999999997774, "open_risk_before": 0.0, "cap_pct": 0.0075, "equity": 10000.0, "stop_distance_points": 72.54999999999345, "volume_rounded": 0.34}, "risk_budget": 25.0, "cap_budget": 75.0, "session": null, "entry": 1.161585, "sl": 1.1623105, "tp": 1.159675}
```

## Risks / Assumptions
- `configs/broker_symbols.json` coverage varies by symbol; FX/XAU fallbacks applied when fields are missing.
- Additional symbols should be onboarded/validated in PR4.

## Next
PR4: Symbol Onboarding + broker meta validator + unit tests for the sizer and log contract.

## Sanity checks I’ll look for
- `risk_too_small`: shows `min_lot` and `computed_volume`.
- `execution_sized`: `volume_rounded` ≈ `risk_budget / (stop_points * contract_size * point)` after rounding; `risk_budget = equity * per_trade_pct`; `cap_budget = equity * cap_pct`.

## Tests and artifacts
- `tests/unit/test_pr3_risk_sizer.py`:
  - `test_risk_too_small_guard_logs_and_skips`
  - `test_risk_cap_hit_guard_logs_and_skips`
  - `test_execution_sized_happy_path_contract`
- Current branch: all three tests pass (`pytest tests/unit/test_pr3_risk_sizer.py -q`).
