#!/usr/bin/env python3
"""
Verify broker symbols configuration.
Standalone script to isolate JSON shape/path issues vs. executor issues.
"""

import json
import os
import sys

BROKER_JSON = os.environ.get("DEVI_BROKER_JSON", "configs/broker_symbols.json")

REQUIRED = [
    "point", "digits", "volume_min", "volume_max", "volume_step",
    "min_stop_distance", "max_stop_distance", "spread"
]


def load_symbols(path):
    """Load and validate broker symbols from JSON."""
    if not os.path.exists(path):
        print(f"FAIL: broker_symbols not found: {path}")
        sys.exit(1)
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # support both shapes: { "symbols": { ... } } or flat { "EURUSD": {...} }
    symbols_root = data.get("symbols", data)
    if not isinstance(symbols_root, dict):
        print("FAIL: broker_symbols.json must be an object or have top-level 'symbols'")
        sys.exit(1)

    out = {}
    for sym, info in symbols_root.items():
        sym_u = sym.strip().upper()
        missing = [k for k in REQUIRED if k not in info]
        if missing:
            print(f"FAIL: {sym_u} missing fields: {missing}")
            sys.exit(1)
        out[sym_u] = {
            "point": float(info["point"]),
            "digits": int(info["digits"]),
            "volume_min": float(info["volume_min"]),
            "volume_max": float(info["volume_max"]),
            "volume_step": float(info["volume_step"]),
            "min_stop_distance": float(info["min_stop_distance"]),
            "max_stop_distance": float(info["max_stop_distance"]),
            "spread": float(info["spread"]),
        }
    
    if not out:
        print("FAIL: no symbols parsed")
        sys.exit(1)
    
    return out


def main():
    """Verify symbols are loaded and all required symbols are present."""
    symbols = load_symbols(BROKER_JSON)
    want = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "XAUUSD"]
    missing = [s for s in want if s not in symbols]
    
    if missing:
        print(f"FAIL: missing required symbols: {missing}")
        print(f"Registered: {sorted(symbols.keys())}")
        sys.exit(1)
    
    print("OK: broker_symbols loaded and all required symbols present")
    print(f"Registered: {sorted(symbols.keys())}")
    print(f"Total symbols: {len(symbols)}")
    
    # Print sample symbol details
    if "EURUSD" in symbols:
        eu = symbols["EURUSD"]
        print(f"\nSample (EURUSD):")
        print(f"  point: {eu['point']}")
        print(f"  digits: {eu['digits']}")
        print(f"  volume_min: {eu['volume_min']}")
        print(f"  volume_max: {eu['volume_max']}")
        print(f"  min_stop_distance: {eu['min_stop_distance']}")
        print(f"  max_stop_distance: {eu['max_stop_distance']}")


if __name__ == "__main__":
    main()
