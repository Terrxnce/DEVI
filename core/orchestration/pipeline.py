"""Trading pipeline orchestration."""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Tuple
import os
import json

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
        # Counters / accumulators
        self.processed_bars = 0            # bars that passed session/market guards (now increments early)
        self.decisions_generated = 0
        self.execution_results = []
        self.logger = logger

        # ---- PR1: Sessions / guards ----
        sessions_path = os.path.join(os.getcwd(), "configs", "sessions.json")
        system_path = os.path.join(os.getcwd(), "configs", "system.json")
        self.session_mgr = SessionManager(sessions_path, system_path)

        # ---- PR3: Risk config + broker meta used by sizer ----
        self.risk_cfg = dict((self.config.system_configs or {}).get("risk", {}) or {})
        # sensible defaults so dry-run never crashes
        self.risk_cfg.setdefault("per_trade_pct", 0.25)                # % of equity
        self.risk_cfg.setdefault("per_symbol_open_risk_cap_pct", 0.75) # % of equity
        self.default_equity = float((self.config.system_configs or {}).get("equity", 10000.0))

        self.broker_symbols = {}
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            broker_path = os.path.join(base_dir, "configs", "broker_symbols.json")
            if os.path.exists(broker_path):
                with open(broker_path, "r", encoding="utf-8") as f:
                    broker_meta = json.load(f) or {}
                # IMPORTANT: use inner "symbols" object
                self.broker_symbols = broker_meta.get("symbols", {})
            logger.info("broker_symbols_registered", extra={"registered": list(self.broker_symbols.keys())})
        except Exception as e:
            logger.exception("broker_meta_init_failed", extra={"error": str(e)})
            self.broker_symbols = {}

        # ---- Structure-first exit planner (PR: SLTP v1.6.0) ----
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sltp_path = os.path.join(base_dir, "configs", "sltp.json")
            with open(sltp_path, "r", encoding="utf-8") as f:
                sltp_cfg = json.load(f)
            self.exit_planner = StructureExitPlanner(sltp_cfg, self.broker_symbols)
        except Exception as e:
            logger.exception("exit_planner_init_failed", extra={"error": str(e)})
            self.exit_planner = None
    def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
        """
        Process a single bar through the pipeline.
        
        Args:
            data: OHLCV time series (cumulative bars up to current)
            timestamp: Current bar timestamp
        
        Returns:
            List of decisions generated
        """
        decisions = []

        try:
            # Session rotation and market status guard
            prev_sess, new_sess = self.session_mgr.update_and_rotate(timestamp)
            if new_sess is not None:
                logger.info("session_rotated", extra={"from": prev_sess, "to": self.session_mgr.current_session})
                if prev_sess and self.session_mgr.autonomy.get("close_positions_on_session_end", False):
                    self.executor.close_positions(self.session_mgr.tracked_symbols)

            # Market-closed / Symbol-unavailable guard
            if not self.executor.is_market_open() or not self.executor.is_symbol_tradable(data.symbol):
                logger.info("market_closed_skip", extra={
                    "symbol": data.symbol,
                    "session": self.session_mgr.current_session,
                    "timestamp": timestamp.isoformat()
                })
                return decisions

            # >>> Count the bar EARLY so early-return paths still count
            self.processed_bars += 1

            # Circuit breaker gate
            if self.session_mgr.session_counters.get("full_sl_hits", 0) >= self.session_mgr.get_max_full_sl_hits():
                logger.info("circuit_breaker_tripped", extra={
                    "session": self.session_mgr.current_session,
                    "full_sl_hits": self.session_mgr.session_counters.get("full_sl_hits", 0),
                })
                return decisions

            # Volatility pause auto-resume
            if self.session_mgr.clear_pause_if_elapsed(timestamp):
                logger.info("volatility_pause_cleared", extra={
                    "session": self.session_mgr.current_session,
                    "timestamp": timestamp.isoformat(),
                })
            if self.session_mgr.is_paused(timestamp):
                logger.info("volatility_pause_active", extra={
                    "session": self.session_mgr.current_session,
                    "timestamp": timestamp.isoformat(),
                })
                return decisions

            # Volatility pause trigger (spread/ATR)
            vp = self.session_mgr.volatility_pause_cfg or {}
            if vp.get("enable", False):
                baseline_spread = self.executor.get_baseline_spread(data.symbol)
                current_spread = self.executor.get_spread(data.symbol)
                spread_mult = float((vp.get("spread_multipliers", {}) or {}).get("default", 1.8))
                # ATR now and lookback avg over last N bars
                lookback = int(vp.get("lookback_bars", 100))
                atr_now = None
                atr_avg = None
                if len(data.bars) >= max(14, 2):
                    try:
                        atr_now = float(compute_atr_simple(list(data.bars)[-15:], 14) or 0)
                        # naive TR average over last lookback
                        bars_slice = list(data.bars)[-lookback:]
                        trs = [float(abs(b.high - b.low)) for b in bars_slice] if bars_slice else []
                        atr_avg = sum(trs) / len(trs) if trs else 0.0
                    except Exception:
                        atr_now = None
                        atr_avg = None
                atr_mult = float(vp.get("atr_spike_multiplier", 2.0))
                spread_bad = current_spread > spread_mult * baseline_spread if baseline_spread and current_spread else False
                atr_bad = (atr_now is not None and atr_avg and atr_avg > 0 and atr_now > atr_mult * atr_avg)
                if spread_bad or atr_bad:
                    pause_secs = int(vp.get("min_pause_seconds", 120))
                    until = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
                    until = until + (timezone.utc.utcoffset(until) or (until - until))  # no-op ensure tz
                    # naive add seconds
                    from datetime import timedelta
                    self.session_mgr.pause_until(until + timedelta(seconds=pause_secs))
                    logger.info("volatility_pause", extra={
                        "session": self.session_mgr.current_session,
                        "symbol": data.symbol,
                        "spread": current_spread,
                        "baseline_spread": baseline_spread,
                        "spread_multiplier": spread_mult,
                        "atr_now": atr_now,
                        "atr_avg": atr_avg,
                        "atr_multiplier": atr_mult,
                        "pause_seconds": pause_secs,
                        "timestamp": timestamp.isoformat(),
                    })
                    return decisions
        except Exception as e:
            logger.exception(
                "pipeline_processing_error",
                extra={"error": str(e), "symbol": getattr(data, "symbol", None), "timestamp": timestamp.isoformat()},
            )

        try:
            # Stage 1: Pre-filters
            if not self._process_pre_filters(data):
                logger.debug("stage_2_pre_filters_failed")
                return decisions
            
            # Stage 2: Indicators
            if not self._process_indicators(data):
                logger.debug("stage_3_indicators_failed")
                return decisions
            
            # Stage 3: Structure detection
            structures = self._process_structure_detection(data)
            logger.debug("stage_4_structures_detected", extra={"count": len(structures)})
            
            if not structures:
                logger.debug("stage_4_no_structures")
                return decisions
            
            # Stage 4: Decision generation
            decisions = self._process_decision_generation(structures, data, timestamp)
            logger.debug("stage_5_decisions_generated", extra={"count": len(decisions)})
            
            # Stage 5: Execution with risk sizing and caps
            if self.executor.enabled and decisions:
                sym = data.symbol
                meta = self.broker_symbols.get(sym, {})
                point = float(meta.get("point", 0.0001))
                # sane defaults: FX 100k, XAU 100
                contract_size = float(meta.get("contract_size", 0.0)) or (100.0 if sym.upper().startswith("XAU") else 100000.0)
                min_lot = float(meta.get("volume_min", 0.01))
                max_lot = float(meta.get("volume_max", 100.0))
                lot_step = float(meta.get("volume_step", 0.01))

                # SAFE equity + open-risk with fallbacks (keeps dry-run alive)
                if hasattr(self.executor, "get_equity"):
                    try:
                        equity = float(self.executor.get_equity())
                    except Exception:
                        equity = self.default_equity
                else:
                    equity = self.default_equity

                if hasattr(self.executor, "get_open_risk_by_symbol"):
                    try:
                        open_risk_before_fn = self.executor.get_open_risk_by_symbol
                    except Exception:
                        open_risk_before_fn = None
                else:
                    open_risk_before_fn = None

                per_trade_pct = float(self.risk_cfg.get("per_trade_pct", 0.25)) / 100.0
                cap_pct = float(self.risk_cfg.get("per_symbol_open_risk_cap_pct", 0.75)) / 100.0
                risk_budget = max(equity * per_trade_pct, 0.0)
                cap_budget = equity * cap_pct

                # iterate with index so we can replace decisions[i] with a sized copy
                for idx, decision in enumerate(decisions):
                    stop_distance_points = abs(float(decision.entry_price) - float(decision.stop_loss)) / max(point, 1e-12)
                    if stop_distance_points <= 0:
                        logger.info("risk_too_small", extra={
                            "session": self.session_mgr.current_session,
                            "symbol": sym,
                            "equity": equity,
                            "per_trade_pct": per_trade_pct,
                            "reason": "non_positive_stop_distance"
                        })
                        continue

                    # Point value per lot: for USD-quoted FX and XAU this is contract_size * point
                    point_value_per_lot = contract_size * point
                    # raw volume from risk budget
                    volume_raw = risk_budget / max((stop_distance_points * point_value_per_lot), 1e-12)
                    # Round down to lot_step
                    steps = max(int(volume_raw / lot_step), 0)
                    volume_rounded = steps * lot_step
                    if volume_rounded < min_lot:
                        logger.info("risk_too_small", extra={
                            "session": self.session_mgr.current_session,
                            "symbol": sym,
                            "equity": equity,
                            "per_trade_pct": per_trade_pct,
                            "min_lot": min_lot,
                            "computed_volume": volume_raw
                        })
                        continue
                    volume_rounded = min(volume_rounded, max_lot)

                    new_trade_risk = stop_distance_points * point_value_per_lot * volume_rounded
                    open_risk_before = 0.0
                    if open_risk_before_fn:
                        try:
                            open_risk_before = float(open_risk_before_fn(sym))
                        except Exception:
                            open_risk_before = 0.0

                    if open_risk_before + new_trade_risk > cap_budget:
                        logger.info("risk_cap_hit", extra={
                            "session": self.session_mgr.current_session,
                            "symbol": sym,
                            "open_risk": open_risk_before,
                            "new_trade_risk": new_trade_risk,
                            "cap_pct": cap_pct,
                            "equity": equity,
                        })
                        continue

                    # Build a new sized Decision (frozen dataclass safe)
                    new_meta = dict(decision.metadata or {})
                    new_meta["risk"] = {
                        "new_trade_risk": float(new_trade_risk),
                        "open_risk_before": float(open_risk_before),
                        "cap_pct": float(cap_pct),
                        "equity": float(equity),
                        "stop_distance_points": float(stop_distance_points),
                        "volume_rounded": float(volume_rounded),
                    }

                    sized_decision = Decision(
                        decision_type=decision.decision_type,
                        symbol=decision.symbol,
                        timestamp=decision.timestamp,
                        session_id=decision.session_id,
                        entry_price=decision.entry_price,
                        stop_loss=decision.stop_loss,
                        take_profit=decision.take_profit,
                        position_size=Decimal(str(volume_rounded)),  # updated size
                        risk_reward_ratio=decision.risk_reward_ratio,
                        structure_id=decision.structure_id,
                        confidence_score=decision.confidence_score,
                        reasoning=decision.reasoning,
                        status=decision.status,
                        metadata=new_meta,
                    )

                    decisions[idx] = sized_decision

                    # Explicit structured log of final sized trade (for PR3 artifacts)
                    logger.info(
                        "execution_sized",
                        extra={
                            "symbol": sym,
                            "order_type": sized_decision.decision_type.value,
                            "volume_rounded": float(sized_decision.position_size),
                            "risk": sized_decision.metadata.get("risk", {}),
                            "session": self.session_mgr.current_session,
                            "entry": float(sized_decision.entry_price),
                            "sl": float(sized_decision.stop_loss),
                            "tp": float(sized_decision.take_profit),
                        },
                    )

                    execution_result = self.executor.execute_order(
                        symbol=sym,
                        order_type=sized_decision.decision_type.value,
                        volume=float(sized_decision.position_size),
                        entry_price=float(sized_decision.entry_price),
                        stop_loss=float(sized_decision.stop_loss),
                        take_profit=float(sized_decision.take_profit),
                        comment=f"DEVI_{sized_decision.metadata.get('structure_type', 'UNKNOWN')}",
                        magic=0,
                    )
                    self.execution_results.append(execution_result)
                    if getattr(execution_result, "success", False):
                        # track open risk accumulation in dry-run
                        if hasattr(self.executor, "add_open_risk"):
                            try:
                                self.executor.add_open_risk(sym, new_trade_risk)
                            except Exception:
                                pass
            # tally decisions
            self.decisions_generated += len(decisions)
            # Update session counters
            self.session_mgr.session_counters["decisions_attempted"] += len(structures)
            self.session_mgr.session_counters["decisions_accepted"] += len(decisions)
            logger.info("session_counters", extra={
                "session": self.session_mgr.current_session,
                "decisions_attempted": self.session_mgr.session_counters["decisions_attempted"],
                "decisions_accepted": self.session_mgr.session_counters["decisions_accepted"],
                "timestamp": timestamp.isoformat(),
            })
            
        except Exception as e:
            logger.exception(
                "pipeline_processing_error",
                extra={"error": str(e), "symbol": getattr(data, "symbol", None), "timestamp": timestamp.isoformat()},
            )
        return decisions
    
    def _process_pre_filters(self, data: OHLCV) -> bool:
        """Check pre-filter conditions."""
        is_test_mode = self.config.system_configs.get('synthetic_mode', False) or \
                       self.config.system_configs.get('data_source') in ['synthetic', 'csv']
        min_bars = 5 if is_test_mode else 50
        
        if len(data.bars) < min_bars:
            logger.debug("pre_filter_insufficient_bars", extra={"bars": len(data.bars), "min_required": min_bars})
            return False
        
        return True
    
    def _process_indicators(self, data: OHLCV) -> bool:
        """Calculate indicators."""
        atr = compute_atr_simple(list(data.bars), 14)
        if atr is None:
            logger.debug("indicator_atr_failed")
            return False
        
        logger.debug("indicator_atr_success", extra={"atr": float(atr)})
        return True
    
    def _process_structure_detection(self, data: OHLCV) -> List[Structure]:
        """Detect market structures."""
        session_id = "test_session"
        structures = self.structure_manager.detect_structures(data, session_id)
        return structures
    
    def _process_decision_generation(self, structures: List[Structure], data: OHLCV, timestamp: datetime) -> List[Decision]:
        """Generate trading decisions from structures."""
        decisions = []
        
        for structure in structures:
            try:
                decision_type = DecisionType.BUY if structure.is_bullish else DecisionType.SELL

                # Establish entry and ATR for planning
                entry_price = data.latest_bar.close
                atr_val = compute_atr_simple(list(data.bars), 14)

                # Defaults
                planned_sl = None
                planned_tp = None
                planned_method = "legacy"
                expected_rr = None

                # Structure-first exit planning (if enabled and ATR available)
                if self.exit_planner and atr_val is not None and getattr(self.exit_planner, "cfg", {}).get("enabled", False):
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
                                "age": int(ob.metadata.get("age_bars", 0)),
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
                                "age": int(fvg.metadata.get("age_bars", 0)),
                                "quality": Decimal(str(fvg.quality_score)),
                            }
                        }

                    plan = self.exit_planner.plan(side=side_str, entry=entry_price, atr=atr_val, structures=structures_map)
                    if plan:
                        planned_sl = Decimal(str(plan["sl"]))
                        planned_tp = Decimal(str(plan["tp"]))
                        planned_method = plan.get("method", "atr")
                        expected_rr = plan.get("expected_rr")

                # Use planned values if available; otherwise fallback
                if planned_sl is not None and planned_tp is not None:
                    stop_loss = planned_sl
                    take_profit = planned_tp
                else:
                    if structure.is_bullish:
                        stop_loss = structure.low_price - (structure.price_range * Decimal("0.1"))
                        take_profit = entry_price + (structure.price_range * Decimal("2.0"))
                    else:
                        stop_loss = structure.high_price + (structure.price_range * Decimal("0.1"))
                        take_profit = entry_price - (structure.price_range * Decimal("2.0"))
                
                if decision_type == DecisionType.BUY:
                    risk = entry_price - stop_loss
                    reward = take_profit - entry_price
                else:
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
                    reasoning=f"Structure: {structure.structure_type.value}",
                    status=DecisionStatus.VALIDATED,
                    metadata={
                        'structure_type': structure.structure_type.value,
                        'structure_quality': structure.quality.value,
                        'rr': float(rr)
                    }
                )
                
                decisions.append(decision)
                logger.debug("decision_generated", extra={
                    "type": decision_type.value,
                    "rr": float(rr),
                    "structure": structure.structure_type.value
                })
            
            except Exception as e:
<<<<<<< Updated upstream
                logger.warning("decision_generation_error", extra={"error": str(e)})
        
=======
                logger.exception("decision_generation_error", extra={"error": str(e)})

>>>>>>> Stashed changes
        return decisions
    
    def finalize_session(self, session_name: str) -> None:
        """Finalize session and log summary."""
        self.executor.log_dry_run_summary()
        logger.info("session_finalized", extra={
            "session": session_name,
            "bars_processed": self.processed_bars,
            "decisions_generated": self.decisions_generated,
            "execution_results": len(self.execution_results)
        })
    
    def get_pipeline_stats(self) -> dict:
        """Get pipeline statistics."""
        return {
            "processed_bars": self.processed_bars,
            "decisions_generated": self.decisions_generated,
            "execution_results": len(self.execution_results),
            "executor_mode": self.executor.mode.value
        }
