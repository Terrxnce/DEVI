"""Trading pipeline orchestration."""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Tuple
import os

from ..models.ohlcv import OHLCV
from ..models.structure import Structure
from ..models.decision import Decision, DecisionType, DecisionStatus
from ..models.config import Config
from ..structure.manager import StructureManager
from ..execution.mt5_executor import MT5Executor, ExecutionMode
from ..indicators.atr import compute_atr_simple
from .session_manager import SessionManager

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
        # Session manager initialization (UTC windows)
        sessions_path = os.path.join(os.getcwd(), 'configs', 'sessions.json')
        system_path = os.path.join(os.getcwd(), 'configs', 'system.json')
        self.session_mgr = SessionManager(sessions_path, system_path)
    
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
            logger.warning("pipeline_processing_error", extra={"error": str(e)})

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
            
            # Stage 5: Execution
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
            
            self.processed_bars += 1
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
            logger.warning("pipeline_processing_error", extra={"error": str(e)})
        
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
                
                if structure.is_bullish:
                    entry_price = data.latest_bar.close
                    stop_loss = structure.low_price - (structure.price_range * Decimal('0.1'))
                    take_profit = entry_price + (structure.price_range * Decimal('2.0'))
                else:
                    entry_price = data.latest_bar.close
                    stop_loss = structure.high_price + (structure.price_range * Decimal('0.1'))
                    take_profit = entry_price - (structure.price_range * Decimal('2.0'))
                
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
                logger.warning("decision_generation_error", extra={"error": str(e)})
        
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
