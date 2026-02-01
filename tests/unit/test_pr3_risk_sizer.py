"""PR3 risk sizing and open-risk cap tests.

Covers:
- risk_too_small guard
- risk_cap_hit guard
- execution_sized happy-path contract
"""

import json
import logging
import os
import sys
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.models.ohlcv import Bar, OHLCV
from core.models.config import Config
from core.orchestration.pipeline import TradingPipeline
from configs import config_loader


def _create_sample_data(symbol: str = "EURUSD") -> OHLCV:
    """Create deterministic OHLCV sample data similar to other pipeline tests."""
    bars = []
    base_price = Decimal("1.1000")

    for i in range(100):
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=15 * (99 - i))
        price_change = Decimal(str((i % 10 - 5) * 0.0001))
        open_price = base_price + price_change
        high_price = open_price + Decimal("0.0005")
        low_price = open_price - Decimal("0.0003")
        close_price = open_price + Decimal(str((i % 3 - 1) * 0.0002))

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
    """Construct Config from on-disk JSON configs via ConfigLoader."""
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


class TestPR3RiskSizer:
    """Tests for PR3 risk-based sizing and open-risk cap behavior."""

    def test_risk_too_small_guard_logs_and_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        """When per-trade risk is tiny, pipeline should log risk_too_small and not execute orders."""
        all_configs = config_loader.get_all_configs()
        # Make per_trade_pct extremely small so computed volume falls below min_lot.
        all_configs["system"]["system_configs"].setdefault("risk", {})["per_trade_pct"] = 0.0001

        config = Config(
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

        pipeline = TradingPipeline(config)
        sample_data = _create_sample_data("EURUSD")
        timestamp = datetime.now(timezone.utc)

        with caplog.at_level(logging.INFO, logger="core.orchestration.pipeline"):
            decisions = pipeline.process_bar(sample_data, timestamp)

        # Decisions may still be produced, but no executions should occur when risk is too small.
        assert isinstance(decisions, list)
        assert len(pipeline.execution_results) == 0

        risk_records = [
            r
            for r in caplog.records
            if r.name == "core.orchestration.pipeline" and r.message == "risk_too_small"
        ]
        assert risk_records, "Expected at least one risk_too_small log record"

        record = risk_records[0]
        # Log contract: symbol, equity, per_trade_pct, min_lot, computed_volume.
        assert getattr(record, "symbol", None) == "EURUSD"
        assert hasattr(record, "equity")
        assert hasattr(record, "per_trade_pct")
        assert hasattr(record, "min_lot")
        assert hasattr(record, "computed_volume")
        # per_trade_pct should be a small positive fraction
        assert 0 < record.per_trade_pct < 1

    def test_risk_cap_hit_guard_logs_and_skips(self, caplog: pytest.LogCaptureFixture) -> None:
        """When open-risk + new trade risk exceeds cap, pipeline should log risk_cap_hit and skip execution."""
        all_configs = config_loader.get_all_configs()
        # Configure risk so a normal trade exceeds the cap on the first attempt:
        # - per_trade_pct relatively large
        # - cap_pct tiny so risk_budget > cap_budget
        risk_cfg = all_configs["system"].setdefault("system_configs", {}).setdefault("risk", {})
        risk_cfg["per_trade_pct"] = 1.0
        risk_cfg["per_symbol_open_risk_cap_pct"] = 0.001

        config = Config(
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

        pipeline = TradingPipeline(config)
        sample_data = _create_sample_data("EURUSD")
        timestamp = datetime.now(timezone.utc)

        with caplog.at_level(logging.INFO, logger="core.orchestration.pipeline"):
            decisions = pipeline.process_bar(sample_data, timestamp)

        assert isinstance(decisions, list)
        # With cap_pct extremely small, no executions should be recorded.
        assert len(pipeline.execution_results) == 0

        cap_records = [
            r
            for r in caplog.records
            if r.name == "core.orchestration.pipeline" and r.message == "risk_cap_hit"
        ]
        assert cap_records, "Expected at least one risk_cap_hit log record"

        record = cap_records[0]
        # Log contract: symbol, open_risk, new_trade_risk, cap_pct, equity.
        assert getattr(record, "symbol", None) == "EURUSD"
        assert hasattr(record, "open_risk")
        assert hasattr(record, "new_trade_risk")
        assert hasattr(record, "cap_pct")
        assert hasattr(record, "equity")
        # For this test we expect open_risk to be zero (no prior trades).
        assert record.open_risk == 0.0

    def test_execution_sized_happy_path_contract(self, caplog: pytest.LogCaptureFixture) -> None:
        """On a normal path, execution_sized log should match the PR3 contract semantics."""
        # Use configs from disk but adjust risk so that:
        # - per_trade_pct is large enough to avoid risk_too_small
        # - cap_pct is much larger so we do not hit the cap
        all_configs = config_loader.get_all_configs()
        risk_cfg = all_configs["system"].setdefault("system_configs", {}).setdefault("risk", {})
        risk_cfg["per_trade_pct"] = 5.0
        risk_cfg["per_symbol_open_risk_cap_pct"] = 50.0

        config = Config(
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
        pipeline = TradingPipeline(config)
        sample_data = _create_sample_data("EURUSD")
        timestamp = datetime.now(timezone.utc)

        with caplog.at_level(logging.INFO, logger="core.orchestration.pipeline"):
            decisions = pipeline.process_bar(sample_data, timestamp)

        assert isinstance(decisions, list)

        sized_records = [
            r
            for r in caplog.records
            if r.name == "core.orchestration.pipeline" and r.message == "execution_sized"
        ]
        assert sized_records, "Expected at least one execution_sized log record"

        record = sized_records[0]

        # Top-level fields from PR3 contract.
        assert getattr(record, "symbol", None) == "EURUSD"
        assert hasattr(record, "order_type")
        assert hasattr(record, "volume_rounded")
        assert hasattr(record, "risk")
        assert hasattr(record, "risk_budget")
        assert hasattr(record, "cap_budget")
        assert hasattr(record, "entry")
        assert hasattr(record, "sl")
        assert hasattr(record, "tp")

        risk_meta = record.risk
        assert isinstance(risk_meta, dict)
        # Risk dict contract.
        for key in [
            "new_trade_risk",
            "open_risk_before",
            "cap_pct",
            "equity",
            "stop_distance_points",
            "volume_rounded",
        ]:
            assert key in risk_meta

        # Sanity: risk and budgets must be positive.
        assert record.risk_budget > 0
        assert record.cap_budget > 0
        assert risk_meta["new_trade_risk"] > 0
        assert risk_meta["volume_rounded"] > 0

        # Numeric relationship from PR3: new_trade_risk ~= stop_points * contract_size * point * volume_rounded.
        with open("configs/broker_symbols.json", "r", encoding="utf-8") as f:
            broker_meta = json.load(f)["symbols"]["EURUSD"]
        point = float(broker_meta["point"])
        contract_size = 100000.0  # Default FX contract size used in pipeline when not specified in broker meta.

        stop_points = float(risk_meta["stop_distance_points"])
        vol = float(risk_meta["volume_rounded"])
        expected_risk = stop_points * contract_size * point * vol
        assert pytest.approx(risk_meta["new_trade_risk"], rel=1e-6) == expected_risk

        # risk_budget and cap_budget should reflect equity * pct/100 semantics.
        # We cannot see pct directly here, but budgets must be consistent ordering.
        assert record.cap_budget > record.risk_budget
