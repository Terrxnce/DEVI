#!/usr/bin/env python3
import json
import os
import sys
from typing import Dict, Any, List

def load_broker_symbols(base_dir: str) -> Dict[str, Any]:
    cfg_path = os.path.join(base_dir, "configs", "broker_symbols.json")
    if not os.path.exists(cfg_path):
        print(f"ERROR: broker_symbols.json not found at {cfg_path}")
        sys.exit(2)
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        symbols = data.get("symbols", {}) or {}
        if not isinstance(symbols, dict):
            print("ERROR: 'symbols' must be an object mapping symbol -> meta")
            sys.exit(2)
        return symbols
    except Exception as e:
        print(f"ERROR: failed to parse broker_symbols.json: {e}")
        sys.exit(2)

def validate_symbols(symbols: Dict[str, Any]) -> int:
    required = ["point", "contract_size", "volume_min", "volume_step", "volume_max"]
    missing_count = 0
    invalid_count = 0

    rows: List[str] = []
    header = f"{'SYMBOL':<12} | {'MISSING':<40} | {'INVALID':<20} | {'tick_value_per_lot':<18}"
    rows.append(header)
    rows.append("-" * len(header))

    for sym, meta in symbols.items():
        missing: List[str] = []
        invalid: List[str] = []
        for k in required:
            v = meta.get(k)
            if v is None or v == "":
                missing.append(k)
            else:
                if k in ("point", "contract_size", "volume_min", "volume_step", "volume_max"):
                    try:
                        if float(v) <= 0:
                            invalid.append(k)
                    except Exception:
                        invalid.append(k)
        tv = meta.get("tick_value_per_lot")
        tv_str = "-"
        if tv is not None:
            tv_str = str(tv)
            try:
                if float(tv) <= 0:
                    invalid.append("tick_value_per_lot")
            except Exception:
                invalid.append("tick_value_per_lot")

        if missing:
            missing_count += 1
        if invalid:
            invalid_count += 1

        rows.append(f"{sym:<12} | {','.join(missing) or '-':<40} | {','.join(invalid) or '-':<20} | {tv_str:<18}")

    print("\nBroker Symbols Coverage Table\n")
    print("\n".join(rows))
    print()

    rc = 0
    if missing_count > 0 or invalid_count > 0:
        print(f"ERROR: Found {missing_count} symbol(s) with missing fields and {invalid_count} with invalid fields.")
        rc = 3
    else:
        print("OK: All symbols have required fields with valid values.")
    return rc


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    symbols = load_broker_symbols(base_dir)
    rc = validate_symbols(symbols)
    sys.exit(rc)

if __name__ == "__main__":
    main()
