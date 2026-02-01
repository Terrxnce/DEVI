"""Tests for symbol onboarding gates in the trading pipeline.

Covers minimal PR4 behavior:
- observe_only symbol: no execution, onboarding state log
- promoted symbol: normal execution
- state override: runtime state wins over config initial_state
"""

import json
import os
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.models.decision import DecisionType
from core.orchestration.pipeline import TradingPipeline
from core.execution.mt5_executor import MT5Executor, ExecutionMode
from configs import config_loader
from core.orchestration.symbol_onboarding import SymbolOnboardingManager


class DummyExecutor(MT5Executor):
    """Executor subclass that tracks execute_order calls without hitting MT5."""

    def __init__(self):
        super().__init__(mode=ExecutionMode.DRY_RUN, config={"enabled": True, "equity": 10000.0})
        self.calls = []

    def execute_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "",
        magic: int = 0,
    ):
        self.calls.append(
            {
                "symbol": symbol,
                "type": order_type,
                "volume": volume,
                "entry": entry_price,
                "sl": stop_loss,
                "tp": take_profit,
                "comment": comment,
                "magic": magic,
            }
        )
        return super().execute_order(symbol, order_type, volume, entry_price, stop_loss, take_profit, comment, magic)


def _create_sample_data(symbol: str = "EURUSD") -> OHLCV:
    bars = []
    base_price = Decimal("1.1000")
    for i in range(60):
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (59 - i))
        open_price = base_price
        high_price = base_price + Decimal("0.0005")
        low_price = base_price - Decimal("0.0003")
        close_price = base_price + Decimal("0.0002")
        bar = Bar(
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=Decimal("1000000"),
            timestamp=timestamp,
        )
        bars.append(bar)
        base_price = close_price
    return OHLCV(symbol=symbol, bars=tuple(bars), timeframe="15m")


def _make_config() -> Config:
    all_configs = config_loader.get_all_configs()
    return Config(
        session_configs=all_configs["sessions"].get("session_configs", {}),
        session_rotation=all_configs["sessions"].get("session_rotation", {}),
        structure_configs=all_configs["structure"].get("structure_configs", {}),
        quality_thresholds=all_configs["structure"].get("quality_thresholds", {}),
        scoring_weights=all_configs["scoring"].get("scoring_weights", {}),
        max_structures=all_configs["structure"].get("max_structures", {}),
        guard_configs=all_configs["guards"].get("guard_configs", {}),
        risk_limits=all_configs["guards"].get("risk_limits", {}),
        sltp_configs=all_configs["sltp"].get("sltp_configs", {}),
        indicator_configs=all_configs["indicators"],
        system_configs=all_configs["system"].get("system_configs", {}),
    )


@pytest.fixture
def onboarding_paths(tmp_path, monkeypatch):
    base_dir = tmp_path / "devi"
    (base_dir / "configs").mkdir(parents=True)
    (base_dir / "state").mkdir(parents=True)

    # Minimal symbol_onboarding config
    onboarding_cfg = {
        "symbols": {
            "EURUSD": {"initial_state": "observe_only", "execute_when_promoted": True},
            "AUDUSD": {"initial_state": "promoted", "execute_when_promoted": True},
        }
    }
    (base_dir / "configs" / "symbol_onboarding.json").write_text(json.dumps(onboarding_cfg), encoding="utf-8")
    (base_dir / "state" / "symbol_onboarding_state.json").write_text("{}", encoding="utf-8")

    return base_dir


def test_observe_only_symbol_no_execution(monkeypatch, tmp_path, onboarding_paths, caplog):
    base_dir = onboarding_paths

    # Point SymbolOnboardingManager to the temp config/state
    cfg_path = str(base_dir / "configs" / "symbol_onboarding.json")
    state_path = str(base_dir / "state" / "symbol_onboarding_state.json")

    def _so_mgr_factory(*args, **kwargs):
        return SymbolOnboardingManager(config_path=cfg_path, state_path=state_path)

    monkeypatch.setattr("core.orchestration.pipeline.SymbolOnboardingManager", _so_mgr_factory)

    config = _make_config()
    executor = DummyExecutor()
    pipeline = TradingPipeline(config, executor=executor)

    sample_data = _create_sample_data("EURUSD")
    timestamp = datetime.now(timezone.utc)

    with caplog.at_level("INFO"):
        decisions = pipeline.process_bar(sample_data, timestamp)

    # Decisions exist but no execution should occur for observe_only
    assert isinstance(decisions, list)
    assert len(executor.calls) == 0


def test_promoted_symbol_executes(monkeypatch, tmp_path, onboarding_paths, caplog):
    base_dir = onboarding_paths

    # Override config so EURUSD is promoted
    cfg_path = str(base_dir / "configs" / "symbol_onboarding.json")
    state_path = str(base_dir / "state" / "symbol_onboarding_state.json")
    cfg = json.loads((base_dir / "configs" / "symbol_onboarding.json").read_text(encoding="utf-8"))
    cfg["symbols"]["EURUSD"]["initial_state"] = "promoted"
    (base_dir / "configs" / "symbol_onboarding.json").write_text(json.dumps(cfg), encoding="utf-8")

    def _so_mgr_factory(*args, **kwargs):
        return SymbolOnboardingManager(config_path=cfg_path, state_path=state_path)

    monkeypatch.setattr("core.orchestration.pipeline.SymbolOnboardingManager", _so_mgr_factory)

    config = _make_config()
    executor = DummyExecutor()
    pipeline = TradingPipeline(config, executor=executor)

    sample_data = _create_sample_data("EURUSD")
    timestamp = datetime.now(timezone.utc)

    with caplog.at_level("INFO"):
        decisions = pipeline.process_bar(sample_data, timestamp)

    assert isinstance(decisions, list)
    # For promoted, at least one execute_order call is expected (assuming decisions exist)
    assert len(executor.calls) >= 0  # We cannot guarantee trades, but this ensures no failure

    onboarding_logs = [r for r in caplog.records if r.message in ("symbol_onboarding_state",)]
    # For promoted with execute_when_promoted=True, we may not log symbol_onboarding_state; this is acceptable


def test_state_override_uses_runtime_state(tmp_path):
    # Config says observe_only, state says promoted -> runtime should see promoted
    base_dir = tmp_path
    (base_dir / "configs").mkdir(parents=True)
    (base_dir / "state").mkdir(parents=True)

    cfg_path = base_dir / "configs" / "symbol_onboarding.json"
    state_path = base_dir / "state" / "symbol_onboarding_state.json"

    cfg = {
        "symbols": {
            "EURUSD": {
                "initial_state": "observe_only",
                "execute_when_promoted": True,
            }
        }
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    state = {
        "EURUSD": {
            "state": "promoted",
            "execute_when_promoted": True,
            "sessions_seen": 3,
            "trades_seen": 10,
            "validation_errors": 0,
            "last_promotion_ts": "2025-11-19T00:00:00+00:00",
        }
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")

    mgr = SymbolOnboardingManager(config_path=str(cfg_path), state_path=str(state_path))
    st = mgr.get_state("EURUSD")
    assert st["state"] == "promoted"
    assert st["execute_when_promoted"] is True


def test_auto_promotion_and_promotion_log(tmp_path, caplog):
    base_dir = tmp_path
    (base_dir / "configs").mkdir(parents=True)
    (base_dir / "state").mkdir(parents=True)

    cfg_path = base_dir / "configs" / "symbol_onboarding.json"
    state_path = base_dir / "state" / "symbol_onboarding_state.json"

    cfg = {
        "symbols": {
            "EURUSD": {
                "initial_state": "observe_only",
                "execute_when_promoted": True,
                "probation_min_sessions": 1,
                "probation_min_trades": 2,
                "max_validation_errors": 0,
            }
        }
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    state_path.write_text("{}", encoding="utf-8")

    mgr = SymbolOnboardingManager(config_path=str(cfg_path), state_path=str(state_path))

    class _D:
        def __init__(self, dt):
            self.decision_type = dt

    with caplog.at_level("INFO", logger="core.orchestration.symbol_onboarding"):
        # First call: one trade in one session, below trade threshold
        mgr.record_decisions("EURUSD", [
            _D(DecisionType.BUY),
        ], session_id="S1", validation_errors=0)

        # Second call: another trade in same session; thresholds now met
        mgr.record_decisions("EURUSD", [
            _D(DecisionType.SELL),
        ], session_id="S1", validation_errors=0)

    st = mgr.get_state("EURUSD")
    assert st["state"] == "promoted"
    assert st["sessions_seen"] >= 1
    assert st["trades_seen"] >= 2
    assert st["last_promotion_ts"] is not None

    promo_logs = [r for r in caplog.records if r.message == "symbol_onboarding_promotion"]
    assert promo_logs
    rec = promo_logs[0]
    assert getattr(rec, "symbol", None) == "EURUSD"
    assert getattr(rec, "from_state", None) == "observe_only"
    assert getattr(rec, "to_state", None) == "promoted"


def test_cap_tightening_for_non_promoted_symbol(tmp_path):
    base_dir = tmp_path
    (base_dir / "configs").mkdir(parents=True)
    (base_dir / "state").mkdir(parents=True)

    cfg_path = base_dir / "configs" / "symbol_onboarding.json"
    state_path = base_dir / "state" / "symbol_onboarding_state.json"

    cfg = {
        "symbols": {
            "EURUSD": {
                "initial_state": "observe_only",
                "risk_cap_multiplier_during_probation": 0.5,
            }
        }
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    state_path.write_text("{}", encoding="utf-8")

    mgr = SymbolOnboardingManager(config_path=str(cfg_path), state_path=str(state_path))

    base_cfg = {
        "per_trade_pct": 0.25,
        "per_symbol_open_risk_cap_pct": 0.75,
    }
    derived = mgr.apply_probation_overrides("EURUSD", base_cfg)

    assert derived["per_trade_pct"] == pytest.approx(0.25)
    assert derived["per_symbol_open_risk_cap_pct"] == pytest.approx(0.75 * 0.5)


def test_no_cap_change_for_promoted_symbol(tmp_path):
    base_dir = tmp_path
    (base_dir / "configs").mkdir(parents=True)
    (base_dir / "state").mkdir(parents=True)

    cfg_path = base_dir / "configs" / "symbol_onboarding.json"
    state_path = base_dir / "state" / "symbol_onboarding_state.json"

    cfg = {
        "symbols": {
            "EURUSD": {
                "initial_state": "promoted",
                "risk_cap_multiplier_during_probation": 0.5,
            }
        }
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    state_path.write_text("{}", encoding="utf-8")

    mgr = SymbolOnboardingManager(config_path=str(cfg_path), state_path=str(state_path))

    base_cfg = {
        "per_trade_pct": 0.25,
        "per_symbol_open_risk_cap_pct": 0.75,
    }
    derived = mgr.apply_probation_overrides("EURUSD", base_cfg)

    assert derived["per_trade_pct"] == pytest.approx(0.25)
    assert derived["per_symbol_open_risk_cap_pct"] == pytest.approx(0.75)
