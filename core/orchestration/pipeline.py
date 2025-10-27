"""Trading pipeline orchestration."""

import logging
import json
import os
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Tuple

from ..models.ohlcv import OHLCV
from ..models.structure import Structure
from ..models.decision import Decision, DecisionType, DecisionStatus
from ..models.config import Config
from ..structure.manager import StructureManager
from ..execution.mt5_executor import MT5Executor, ExecutionMode
from ..indicators.atr import compute_atr_simple
from .session_manager import SessionManager
from .structure_exit_planner import StructureExitPlanner

logger = logging.getLogger(__name__)


class TradingPipeline:
    """Main trading pipeline orchestrator."""

    def __init__(self, config: Config, executor: MT5Executor = None):
        self.config = config
        self.structure_manager = StructureManager(config.structure_configs)
        self.executor = executor or MT5Executor(ExecutionMode.DRY_RUN)
        self.processed_bars = 0
        self.decisions_generated = 0
        self.execution_results = []
        self.logger = logger
        self.broker_symbols = {}
        self._all_decisions: List[Decision] = []

        # Session manager initialization (UTC windows)
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sessions_path = os.path.join(base_dir, "configs", "sessions.json")
            system_path = os.path.join(base_dir, "configs", "system.json")
            self.session_mgr = SessionManager(sessions_path, system_path)
        except Exception as e:
            logger.warning("session_manager_init_failed", extra={"error": str(e)})
            self.session_mgr = None

        # Initialize exit planner (Phase 2)
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sltp_path = os.path.join(base_dir, "configs", "sltp.json")
            broker_path = os.path.join(base_dir, "configs", "broker_symbols.json")

            with open(sltp_path, "r", encoding="utf-8") as f:
                sltp_cfg = json.load(f)

            broker_meta = {}
            if os.path.exists(broker_path):
                with open(broker_path, "r", encoding="utf-8") as f:
                    broker_meta = json.load(f)

            self.exit_planner = StructureExitPlanner(sltp_cfg, broker_meta)
        except Exception as e:
            logger.debug("exit_planner_init_failed", extra={"error": str(e)})
            self.exit_planner = None

    def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
        """Process a single bar through the pipeline."""
        decisions = []

        try:
            # Session rotation + close-out + counters reset
            prev_sess, new_sess = self.session_mgr.update_and_rotate(timestamp)
            if new_sess is not None:
                logger.info("session_rotated", extra={
                    "from": prev_sess,
                    "to": self.session_mgr.current_session
                })
                if prev_sess and self.session_mgr.autonomy.get("close_positions_on_session_end", False):
                    self.executor.close_positions(self.session_mgr.tracked_symbols)

            # Market guard
            if not self.executor.is_market_open() or not self.executor.is_symbol_tradable(data.symbol):
                logger.info("market_closed_skip", extra={
                    "symbol": data.symbol,
                    "session": self.session_mgr.current_session,
                    "timestamp": timestamp.isoformat()
                })
                return decisions

        except Exception as e:
            logger.warning("pipeline_processing_error", extra={"error": str(e)})

        try:
            # Pre-filters
            if not self._process_pre_filters(data):
                return decisions

            # Indicators
            if not self._process_indicators(data):
                return decisions

            # Structure detection
            structures = self._process_structure_detection(data)
            if not structures:
                return decisions

            # Decision generation (includes structure-first SLTP if planner enabled)
            decisions = self._process_decision_generation(structures, data, timestamp)

            # Execute decisions
            if self.executor.enabled and decisions:
                for decision in decisions:
                    execution_result = self.executor.execute_order(
                        symbol=data.symbol,
                        order_type=decision.decision_type.value,
                        volume=float(decision.position_size),
                        entry_price=float(decision.entry_price),
                        stop_loss=float(decision.stop_loss),
                        take_profit=float(decision.take_profit),
                        comment=f"DEVI_{decision.metadata.get('structure_type', 'UNKNOWN')}",
                        magic=0
                    )
                    self.execution_results.append(execution_result)

            # Stats + counters
            self.processed_bars += 1
            self.decisions_generated += len(decisions)

            self.session_mgr.session_counters["decisions_attempted"] += len(structures)
            self.session_mgr.session_counters["decisions_accepted"] += len(decisions)
            logger.info("session_counters", extra={
                "session": self.session_mgr.current_session,
                "decisions_attempted": self.session_mgr.session_counters["decisions_attempted"],
                "decisions_accepted": self.session_mgr.session_counters["decisions_accepted"],
                "timestamp": timestamp.isoformat(),
            })

        except Exception as e:
            logger.warning("pipeline_processing_error", extra={"error": str(e)})

        return decisions

    def _process_pre_filters(self, data: OHLCV) -> bool:
        is_test_mode = self.config.system_configs.get('synthetic_mode', False) or \
                       self.config.system_configs.get('data_source') in ['synthetic', 'csv']
        min_bars = 5 if is_test_mode else 50
        return len(data.bars) >= min_bars

    def _process_indicators(self, data: OHLCV) -> bool:
        atr = compute_atr_simple(list(data.bars), 14)
        return atr is not None

    def _process_structure_detection(self, data: OHLCV) -> List[Structure]:
        return self.structure_manager.detect_structures(data, "test_session")

    def _process_decision_generation(self, structures, data, timestamp):
        decisions = []
        atr_val = compute_atr_simple(list(data.bars), 14)
        atr_val = Decimal(str(atr_val)) if atr_val is not None else None

        for structure in structures:
            try:
                decision_type = DecisionType.BUY if structure.is_bullish else DecisionType.SELL
                entry_price = data.latest_bar.close

                # Default SLTP
                planned_sl = None
                planned_tp = None
                planned_method = "legacy"
                expected_rr = None

                # Exit planner (structure-first)
                if self.exit_planner and atr_val is not None and self.exit_planner.cfg.get("enabled", False):
                    side_str = "BUY" if decision_type == DecisionType.BUY else "SELL"

                    def _nearest(structs, t):
                        c = [s for s in structs if s.structure_type.value == t]
                        return min(c, key=lambda s: abs(s.midpoint - entry_price)) if c else None

                    ob = _nearest(structures, "order_block")
                    fvg = _nearest(structures, "fair_value_gap")

                    structures_map = {}
                    if ob:
                        upper = ob.metadata.get("upper_edge", max(ob.high_price, ob.low_price))
                        lower = ob.metadata.get("lower_edge", min(ob.high_price, ob.low_price))
                        structures_map["order_block"] = {
                            "nearest": {
                                "upper_edge": Decimal(str(upper)),
                                "lower_edge": Decimal(str(lower)),
                                "side": "BUY" if ob.is_bullish else "SELL",
                                "age": int(ob.metadata.get('age_bars', 0)),
                                "quality": Decimal(str(ob.quality_score)),
                            }
                        }
                    if fvg:
                        low = fvg.metadata.get("gap_low", min(fvg.high_price, fvg.low_price))
                        high = fvg.metadata.get("gap_high", max(fvg.high_price, fvg.low_price))
                        structures_map["fair_value_gap"] = {
                            "nearest": {
                                "gap_low": Decimal(str(low)),
                                "gap_high": Decimal(str(high)),
                                "side": "BUY" if fvg.is_bullish else "SELL",
                                "age": int(fvg.metadata.get('age_bars', 0)),
                                "quality": Decimal(str(fvg.quality_score)),
                            }
                        }

                    plan = self.exit_planner.plan(side=side_str, entry=entry_price, atr=atr_val, structures=structures_map)
                    if plan:
                        planned_sl = Decimal(str(plan["sl"]))
                        planned_tp = Decimal(str(plan["tp"]))
                        planned_method = plan.get("method", "atr")
                        expected_rr = plan.get("expected_rr")

                # Legacy fallback if planner failed/not enabled
                if planned_sl is None or planned_tp is None:
                    if structure.is_bullish:
                        stop_loss = structure.low_price - (structure.price_range * Decimal('0.1'))
                        take_profit = entry_price + (structure.price_range * Decimal('2.0'))
                    else:
                        stop_loss = structure.high_price + (structure.price_range * Decimal('0.1'))
                        take_profit = entry_price - (structure.price_range * Decimal('2.0'))
                else:
                    stop_loss = planned_sl
                    take_profit = planned_tp

                # Safety clamp
                epsilon = max(Decimal('0.00001'), structure.price_range * Decimal('0.01'))
                if decision_type == DecisionType.BUY:
                    if stop_loss >= entry_price: stop_loss = entry_price - epsilon
                    if take_profit <= entry_price: take_profit = entry_price + epsilon
                    risk = entry_price - stop_loss
                    reward = take_profit - entry_price
                else:
                    if stop_loss <= entry_price: stop_loss = entry_price + epsilon
                    if take_profit >= entry_price: take_profit = entry_price - epsilon
                    risk = stop_loss - entry_price
                    reward = entry_price - take_profit

                if risk <= 0:
                    continue

                rr = reward / risk

                decision = Decision(
                    decision_type=decision_type,
                    symbol=data.symbol,
                    timestamp=timestamp,
                    session_id="test_session",
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_size=Decimal('0.1'),
                    risk_reward_ratio=rr,
                    structure_id=structure.structure_id,
                    confidence_score=structure.quality_score,
                    reasoning=f"{structure.structure_type.value}",
                    status=DecisionStatus.VALIDATED,
                    metadata={
                        "structure_type": structure.structure_type.value,
                        "rr": float(rr),
                        "exit_method": planned_method,
                        "expected_rr": float(expected_rr) if expected_rr else float(rr),
                        "post_clamp_rr": float(rr)
                    }
                )

                decisions.append(decision)
                self._all_decisions.append(decision)

            except Exception as e:
                logger.warning("decision_generation_error", extra={"error": str(e)})

        return decisions

    def finalize_session(self, session_name: str) -> None:
        hist = {"order_block": 0, "fair_value_gap": 0, "atr": 0, "legacy": 0}
        rr_counts = {k: [0, 0] for k in list(hist.keys()) + ["overall"]}

        for d in self._all_decisions:
            method = d.metadata.get("exit_method", "legacy")
            hist[method] = hist.get(method, 0) + 1
            rr = Decimal(str(d.metadata.get("post_clamp_rr", d.risk_reward_ratio)))

            if rr >= Decimal("1.5"):
                rr_counts[method][0] += 1
                rr_counts["overall"][0] += 1
            rr_counts[method][1] += 1
            rr_counts["overall"][1] += 1

        def pct(v):
            return float((Decimal(v[0]) / Decimal(v[1]) * 100) if v[1] else 0)

        logger.info("dry_run_exit_summary", extra={
            "exit_method_hist": hist,
            "rr_gate": {
                "overall_ge_1_5_pct": pct(rr_counts["overall"]),
                "by_method": {k: pct(v) for k, v in rr_counts.items() if k in hist}
            }
        })

    def get_pipeline_stats(self) -> dict:
        return {
            "processed_bars": self.processed_bars,
            "decisions_generated": self.decisions_generated,
            "execution_results": len(self.execution_results),
            "executor_mode": self.executor.mode.value
        }
