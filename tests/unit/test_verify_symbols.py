"""Tests for scripts.verify_symbols broker symbol validator.

Covers:
- Failure on missing required field
- Success on valid JSON with minimal symbol set
"""

import json
import os
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts import verify_symbols


def _write_temp_json(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "symbols.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_load_symbols_fails_on_missing_required_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Validator should exit non-zero when a required field is missing."""
    payload = {
        "symbols": {
            "EURUSD": {
                # point present, but missing contract_size
                "point": 0.0001,
                "digits": 4,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
                "min_stop_distance": 50,
                "max_stop_distance": 5000,
                "spread": 2.0,
            }
        }
    }
    json_path = _write_temp_json(tmp_path, payload)

    # Call load_symbols directly; it should raise SystemExit on missing required field.
    with pytest.raises(SystemExit) as excinfo:
        verify_symbols.load_symbols(json_path)

    assert excinfo.value.code == 1


def test_load_symbols_succeeds_on_valid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Validator should succeed on a minimal, valid symbol set."""
    payload = {
        "symbols": {
            "EURUSD": {
                "point": 0.0001,
                "contract_size": 100000.0,
                "digits": 4,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
                "min_stop_distance": 50,
                "max_stop_distance": 5000,
                "spread": 2.0,
            }
        }
    }
    json_path = _write_temp_json(tmp_path, payload)

    monkeypatch.setenv("DEVI_BROKER_JSON", json_path)

    # load_symbols should parse and return the symbols dict without exiting
    symbols = verify_symbols.load_symbols(json_path)
    assert "EURUSD" in symbols
    meta = symbols["EURUSD"]
    assert meta["point"] == pytest.approx(0.0001)
    assert meta["contract_size"] == pytest.approx(100000.0)
    assert meta["volume_min"] == pytest.approx(0.01)
    assert meta["volume_max"] == pytest.approx(100.0)
    assert meta["volume_step"] == pytest.approx(0.01)
    assert meta["min_stop_distance"] == pytest.approx(50.0)
    assert meta["max_stop_distance"] == pytest.approx(5000.0)
    assert meta["spread"] == pytest.approx(2.0)
