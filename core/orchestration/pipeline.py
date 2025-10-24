"""Trading pipeline orchestration."""

import logging
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
