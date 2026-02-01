#!/usr/bin/env python3
"""
Verify broker symbols configuration.
Standalone script to isolate JSON shape/path issues vs. executor issues.
"""

import json
import os
import sys

BROKER_JSON = os.environ.get("DEVI_BROKER_JSON", "configs/broker_symbols.json")

# Required fields for sizing + guardrails. Additional fields (e.g. bid/ask) are optional.
REQUIRED = [
    "point",
    "contract_size",
    "digits",
    "volume_min",
    "volume_max",
    "volume_step",
    "min_stop_distance",
    "max_stop_distance",
    "spread",
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
    problems = []
    for sym, info in symbols_root.items():
        sym_u = sym.strip().upper()
        missing = [k for k in REQUIRED if k not in info]
        if missing:
            problems.append(f"{sym_u}: missing fields: {missing}")
            # Skip further numeric validation for this symbol
            continue

        try:
            point = float(info["point"])
            contract_size = float(info["contract_size"])
            volume_min = float(info["volume_min"])
            volume_max = float(info["volume_max"])
            volume_step = float(info["volume_step"])
            min_stop_distance = float(info["min_stop_distance"])
            max_stop_distance = float(info["max_stop_distance"])
            spread = float(info["spread"])
        except Exception as e:
            problems.append(f"{sym_u}: type/parse error: {e}")
            continue

        # Semantic checks for sizing-critical fields
        if point <= 0:
            problems.append(f"{sym_u}: point must be > 0 (got {point})")
        if contract_size <= 0:
            problems.append(f"{sym_u}: contract_size must be > 0 (got {contract_size})")
        if volume_min <= 0:
            problems.append(f"{sym_u}: volume_min must be > 0 (got {volume_min})")
        if volume_step <= 0:
            problems.append(f"{sym_u}: volume_step must be > 0 (got {volume_step})")
        if volume_max < volume_min:
            problems.append(f"{sym_u}: volume_max ({volume_max}) must be >= volume_min ({volume_min})")
        if min_stop_distance <= 0:
            problems.append(f"{sym_u}: min_stop_distance must be > 0 (got {min_stop_distance})")
        if max_stop_distance < min_stop_distance:
            problems.append(f"{sym_u}: max_stop_distance ({max_stop_distance}) must be >= min_stop_distance ({min_stop_distance})")
        if spread <= 0:
            problems.append(f"{sym_u}: spread must be > 0 (got {spread})")

        out[sym_u] = {
            "point": point,
            "contract_size": contract_size,
            "digits": int(info["digits"]),
            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,
            "min_stop_distance": min_stop_distance,
            "max_stop_distance": max_stop_distance,
            "spread": spread,
        }

    if not out:
        problems.append("no symbols parsed")

    if problems:
        print("FAIL: broker_symbols validation errors:\n" + "\n".join(f"- {p}" for p in problems))
        sys.exit(1)

    return out


def main():
    """Verify symbols are loaded and all required symbols are present."""
    symbols = load_symbols(BROKER_JSON)
    want = ["EURUSD", "XAUUSD", "USDJPY", "AUDUSD", "AUDJPY", "NVDA", "TSLA"]
    missing = [s for s in want if s not in symbols]

    if missing:
        print(f"FAIL: missing required symbols: {missing}")
        print(f"Registered: {sorted(symbols.keys())}")
        sys.exit(1)

    print("OK: broker_symbols loaded, required symbols present, and sizing meta validated")
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
