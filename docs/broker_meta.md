# Broker Metadata Validation (PR4-1)

## Required fields per symbol
- **point**: price increment (float > 0)
- **contract_size**: units per lot (float > 0)
- **volume_min**: minimum lot size (float > 0)
- **volume_step**: lot step (float > 0)
- **volume_max**: maximum lot size (float > 0)

## Optional fields
- **tick_value_per_lot**: preferred when present; overrides `contract_size * point` as per-lot tick value in account currency (float > 0)

## Policy
- **allow_broker_meta_fallbacks=false** by default (fail-fast). If set true in `configs/system.json` → a single loud startup log lists defaulted/invalid fields.
- When fallbacks are allowed, pipeline uses defaults:
  - `point=0.0001`, `contract_size=100000` (non-XAU) or `100` (XAU*), `volume_min=0.01`, `volume_step=0.01`, `volume_max=100.0`

## CLI coverage check
```bash
python tools/check_broker_meta.py
```
- Prints a per-symbol table of missing/invalid fields.
- Exits non-zero if any required fields are missing/invalid.

## Examples
```json
{
  "symbols": {
    "EURUSD": {
      "point": 0.0001,
      "contract_size": 100000,
      "volume_min": 0.01,
      "volume_step": 0.01,
      "volume_max": 100.0,
      "tick_value_per_lot": 10.0
    }
  }
}
```

## Notes
- For non-USD quotes, metals, CFDs, and equities: define `tick_value_per_lot` to avoid sizing drift.
- PR4-4 will add spread-aware minimum SL distance enforcement and symbol-level `risk_overrides`.
