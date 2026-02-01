# Symbol Onboarding

Minimal PR4 onboarding gate for per-symbol execution control.

## Config: `configs/symbol_onboarding.json`

Shape:

```jsonc
{
  "symbols": {
    "EURUSD": {
      "initial_state": "promoted",              // "observe_only" | "promoted"
      "execute_when_promoted": true,            // if false, stays log-only even when promoted
      "probation_min_sessions": 5,
      "probation_min_trades": 10,
      "max_validation_errors": 0,
      "min_rr_during_probation": 2.0,
      "risk_cap_multiplier_during_probation": 0.5
    }
  }
}
```

### Defaults (when fields are omitted)

For each symbol, the onboarding manager applies sensible defaults:

- `initial_state` → **`"promoted"`**
- `execute_when_promoted` → **`true`**
- `probation_min_sessions` → `0`
- `probation_min_trades` → `0`
- `max_validation_errors` → `0`
- `min_rr_during_probation` → `null` (no RR override)
- `risk_cap_multiplier_during_probation` → `1.0` (no cap tightening)

These fields are parsed and exposed in runtime state. Probation thresholds and overrides are in place for future PRs but are not yet actively enforced.

---

## Runtime state: `state/symbol_onboarding_state.json`

The runtime state file is the **source of truth** for onboarding decisions.

Example shape:

```jsonc
{
  "EURUSD": {
    "state": "promoted",                   // "observe_only" | "promoted"
    "execute_when_promoted": true,
    "sessions_seen": 12,
    "trades_seen": 47,
    "validation_errors": 0,
    "last_promotion_ts": "2025-11-19T00:00:00+00:00",

    "probation_min_sessions": 5,
    "probation_min_trades": 10,
    "max_validation_errors": 0,
    "min_rr_during_probation": 2.0,
    "risk_cap_multiplier_during_probation": 0.5
  }
}
```

### Precedence

For each symbol:

1. **Defaults** are applied.
2. **Config** (`configs/symbol_onboarding.json`) is merged on top.
3. **State file** (`state/symbol_onboarding_state.json`) overrides config.

This means you can manually promote a symbol by editing the state file, even if the config `initial_state` is `"observe_only"`.

---

## SymbolOnboardingManager API

Implementation: `core/orchestration/symbol_onboarding.py`.

```python
class SymbolOnboardingManager:
    def get_state(self, symbol: str) -> dict: ...
    def record_decisions(
        self,
        symbol: str,
        decisions: list,
        session_id: str | None,
        validation_errors: int = 0,
    ) -> None: ...
    def should_execute(self, symbol: str) -> bool: ...
    def apply_probation_overrides(self, symbol: str, risk_cfg: dict) -> dict: ...
```

### `get_state(symbol)`

- Returns the merged onboarding state for a symbol, including:
  - `symbol`, `state`, `execute_when_promoted`
  - `probation_min_sessions`, `probation_min_trades`, `max_validation_errors`
  - `min_rr_during_probation`, `risk_cap_multiplier_during_probation`
  - `sessions_seen`, `trades_seen`, `validation_errors`, `last_promotion_ts`

### `record_decisions(...)`

- Called by the pipeline after decisions are sized.
- Updates counters:
  - `sessions_seen` (+1 when a session_id is present)
  - `trades_seen` (+len(decisions))
  - `validation_errors` (+validation_errors)
- Persists `state/symbol_onboarding_state.json`.
- **No automatic promotion yet**: promotion is manual via the state file.

### `should_execute(symbol)`

- Minimal gate used by the pipeline:

```python
st = get_state(symbol)
if st["state"] != "promoted":
    return False
if not st["execute_when_promoted"]:
    return False
return True
```

- If `False`, trades for that symbol are **not** executed.
- If `True`, the executor behaves as normal.

### `apply_probation_overrides(symbol, risk_cfg)`

- Currently a **no-op** that returns a deep copy of `risk_cfg`.
- The pipeline already calls this hook; future PRs can implement stricter RR / caps here without mutating the original risk config.

---

## Current pipeline behavior

Location: `core/orchestration/pipeline.py` (inside `TradingPipeline.process_bar`).

1. **Risk sizing (PR3)**
   - Decisions are sized using account equity, per-trade risk, and per-symbol open-risk caps.
   - Logs emitted:
     - `risk_too_small`
     - `risk_cap_hit`
     - `execution_sized` (with risk metadata and budgets)

2. **Onboarding gate (this PR)**

   After a decision is sized and `execution_sized` is logged:

   - The pipeline calls `SymbolOnboardingManager`:

   ```python
   onboarding_state = onboarding_mgr.get_state(symbol)
   should_exec = onboarding_mgr.should_execute(symbol)
   ```

   - **If `should_execute(symbol)` is `False`**:
     - `executor.execute_order` is **not** called.
     - Sized decisions and `execution_sized` logs are still produced.
     - An informational log `symbol_onboarding_state` is emitted when there is a sized trade, including:
       - `symbol`, `state`, `execute=False`, `reason="observe_only"`
       - `sessions_seen`, `trades_seen`, `validation_errors`

   - **If `should_execute(symbol)` is `True`**:
     - The executor is called as before.
     - Open-risk tracking is unchanged.

3. **Counters**

   - After processing sized decisions for a symbol, the pipeline calls:

   ```python
   onboarding_mgr.record_decisions(symbol, decisions, session_id, validation_errors=0)
   ```

   - This updates `sessions_seen`, `trades_seen`, and `validation_errors` in the state file.

---

## Manual promotion (current behavior)

At this stage, **promotion is manual**:

- To keep a symbol in **observe_only**:
  - Set `state` to `"observe_only"` in `state/symbol_onboarding_state.json`, or
  - Use `initial_state = "observe_only"` and no overriding state entry.

- To **promote** a symbol:
  - Edit `state/symbol_onboarding_state.json` and set:

    ```jsonc
    "SYMBOL": {
      "state": "promoted",
      "execute_when_promoted": true
    }
    ```

  - On the next run, `should_execute("SYMBOL")` will return `True` and trades will execute as normal.

Automatic promotion based on `sessions_seen` / `trades_seen` / `validation_errors` and probation-specific RR / caps will be implemented in a follow-up PR using the existing hooks.
