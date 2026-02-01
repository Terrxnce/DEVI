"""Trading pipeline orchestration."""

import logging
import json
import os
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

from ..models.ohlcv import OHLCV
from ..models.structure import Structure
from ..models.decision import Decision, DecisionType, DecisionStatus
from ..models.config import Config
from ..structure.manager import StructureManager
from ..execution.mt5_executor import MT5Executor, ExecutionMode
from ..indicators.atr import compute_atr_simple
from .session_manager import SessionManager
from .symbol_onboarding import SymbolOnboardingManager
from .trade_journal import TradeJournal
from .session_filter import SessionFilter

logger = logging.getLogger(__name__)


class TradingPipeline:
    """Main trading pipeline orchestrator."""

    def __init__(self, config: Config, executor: MT5Executor = None):
        self.config = config
        self.structure_manager = StructureManager(config.structure_configs)
        self.executor = executor or MT5Executor(ExecutionMode.DRY_RUN)

        # Counters / accumulators
        self.processed_bars = 0
        self.decisions_generated = 0
        self.execution_results = []
        self._all_decisions: List[Decision] = []

        # ---- PR1: Sessions / guards ----
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            sessions_path = os.path.join(base_dir, "configs", "sessions.json")
            system_path = os.path.join(base_dir, "configs", "system.json")
            self.session_mgr = SessionManager(sessions_path, system_path)
        except Exception as e:
            logger.warning("session_manager_init_failed", extra={"error": str(e)})
            self.session_mgr = None

        # ---- PR3: Risk config + broker meta used by sizer ----
        self.risk_cfg = dict((self.config.system_configs or {}).get("risk", {}) or {})
        # sensible defaults so dry-run never crashes
        self.risk_cfg.setdefault("per_trade_pct", 0.25)                # % of equity
        self.risk_cfg.setdefault("per_symbol_open_risk_cap_pct", 0.75) # % of equity
        self.default_equity = float((self.config.system_configs or {}).get("equity", 10000.0))
        self.allow_meta_fallbacks = bool((self.config.system_configs or {}).get("allow_broker_meta_fallbacks", False))

        if self.allow_meta_fallbacks:
            logger.warning("allowing_broker_meta_fallbacks")

        self.broker_symbols = {}
        try:
            broker_path = os.path.join(base_dir, "configs", "broker_symbols.json")
            if os.path.exists(broker_path):
                with open(broker_path, "r", encoding="utf-8") as f:
                    broker_meta = json.load(f) or {}
                # IMPORTANT: use inner "symbols" object
                self.broker_symbols = broker_meta.get("symbols", {})
            logger.info("broker_symbols_registered", extra={"registered": list(self.broker_symbols.keys())})
            
            # Wire broker symbol metadata into executor for per-symbol guards (e.g., sl_hard_floor_points)
            if hasattr(self.executor, "_symbol_meta"):
                self.executor._symbol_meta = self.broker_symbols
        except Exception as e:
            logger.exception("broker_meta_init_failed", extra={"error": str(e)})
            self.broker_symbols = {}

        # Load execution guards config first (needed by exit planner)
        try:
            guards_path = os.path.join(base_dir, "configs", "execution_guards.json")
            if os.path.exists(guards_path):
                with open(guards_path, "r", encoding="utf-8") as f:
                    self.guards_config = json.load(f) or {}
            else:
                self.guards_config = {}
        except Exception as e:
            logger.warning("execution_guards_config_load_failed", extra={"error": str(e)})
            self.guards_config = {}
        
        # Initialize exit planner (structure-first; optional via dynamic import)
        try:
            import importlib
            sltp_path = os.path.join(base_dir, "configs", "sltp.json")
            with open(sltp_path, "r", encoding="utf-8") as f:
                sltp_cfg = json.load(f)
            planner_mod = importlib.import_module("core.orchestration.structure_exit_planner")
            PlannerCls = getattr(planner_mod, "StructureExitPlanner")
            self.exit_planner = PlannerCls(sltp_cfg, self.broker_symbols, self.guards_config)
        except Exception as e:
            logger.debug("exit_planner_init_failed", extra={"error": str(e)})
            self.exit_planner = None

        # PR4: Symbol onboarding manager (per-symbol execution gate)
        try:
            self.onboarding_mgr = SymbolOnboardingManager()
        except Exception as e:
            logger.warning("symbol_onboarding_init_failed", extra={"error": str(e)})
            self.onboarding_mgr = None

        dd_cfg = dict((self.config.system_configs or {}).get("risk", {}) or {})
        soft_pct = float(dd_cfg.get("daily_soft_stop_pct", -1.0))
        hard_pct = float(dd_cfg.get("daily_hard_stop_pct", -2.0))
        self._dd_soft_stop_frac = soft_pct / 100.0
        self._dd_hard_stop_frac = hard_pct / 100.0
        self._dd_max_consecutive_failures = int(dd_cfg.get("max_consecutive_send_failures", 3))
        self._dd_baseline_equity: float = None
        self._dd_soft_triggered = False
        self._dd_hard_triggered = False
        self._consecutive_send_failures = 0
        self._last_failure_time: Optional[datetime] = None  # Track last failure for cooldown
        self._failure_cooldown_seconds = int(dd_cfg.get("failure_cooldown_seconds", 1800))  # 30 min default
        self._last_reset_date = None  # Track last daily reset for soft stop

        # FTMO limits (shadow safety layer)
        ftmo_cfg = dict((self.config.system_configs or {}).get("ftmo_limits", {}) or {})
        self._ftmo_max_daily_loss_pct = float(ftmo_cfg.get("max_daily_loss_pct", -5.0))
        self._ftmo_max_total_loss_pct = float(ftmo_cfg.get("max_total_loss_pct", -10.0))
        self._ftmo_profit_target_pct = float(ftmo_cfg.get("profit_target_pct", 10.0))
        self._ftmo_daily_warning_pct = -3.0  # Warn at -3% daily
        self._ftmo_total_warning_pct = -7.0  # Warn at -7% total
        self._ftmo_daily_equity_low: float = None  # Intra-day equity low
        self._ftmo_total_equity_low: float = None  # All-time equity low
        self._ftmo_account_start_equity: float = None  # Starting equity for total drawdown
        self._ftmo_daily_warning_logged = False
        self._ftmo_total_warning_logged = False
        self._ftmo_daily_stop_triggered = False
        self._ftmo_total_stop_triggered = False

        # Environment tracking
        env_cfg = dict((self.config.system_configs or {}).get("env", {}) or {})
        self._env_mode = env_cfg.get("mode", "paper")
        self._env_account_size = float(env_cfg.get("account_size", 10000))
        
        # Margin guard configuration (guards_config already loaded above)
        margin_guard = self.guards_config.get('margin_guard', {})
        self.enable_margin_guard = margin_guard.get('enabled', True)
        self.min_margin_level_pct = float(margin_guard.get('min_margin_level_pct', 200.0))
        self.max_free_margin_usage_pct = float(margin_guard.get('max_free_margin_usage_pct', 30.0))
        self.max_total_open_risk_pct = float(margin_guard.get('max_total_open_risk_pct', 4.5))
        
        # Position tracking for close logging
        self.last_position_check_time = datetime.now(timezone.utc)
        
        # Trade journal for outcome tracking
        journal_cfg = self.guards_config.get('trade_journal', {})
        journal_enabled = journal_cfg.get('enabled', True)
        journal_dir = journal_cfg.get('journal_dir', None)
        try:
            self.trade_journal = TradeJournal(journal_dir=journal_dir, enabled=journal_enabled)
        except Exception as e:
            logger.warning("trade_journal_init_failed", extra={"error": str(e)})
            self.trade_journal = None

        # Session filter for session-aware logging (Phase 1: log only, no blocking)
        try:
            self.session_filter = SessionFilter()
        except Exception as e:
            logger.warning("session_filter_init_failed", extra={"error": str(e)})
            self.session_filter = None

        # Position limit configuration (prevents stacking)
        pos_limit_cfg = self.guards_config.get('position_limit', {})
        self._enable_position_limit = pos_limit_cfg.get('enabled', True)
        self._max_positions_per_symbol = int(pos_limit_cfg.get('max_positions_per_symbol', 2))
        self._max_positions_per_direction = int(pos_limit_cfg.get('max_positions_per_direction_per_symbol', 2))
        self._log_position_limit_blocks = pos_limit_cfg.get('log_blocked_trades', True)

        # Conflict resolver configuration (raises threshold when BUY+SELL conflict)
        conflict_cfg = self.guards_config.get('conflict_resolver', {})
        self._enable_conflict_resolver = conflict_cfg.get('enabled', True)
        self._conflict_lookback_bars = int(conflict_cfg.get('lookback_bars', 4))
        self._conflict_threshold_bump = float(conflict_cfg.get('threshold_bump_on_conflict', 0.15))
        self._conflict_require_confluence = conflict_cfg.get('require_confluence_on_conflict', False)
        self._log_conflicts = conflict_cfg.get('log_conflicts', True)
        
        # Signal history for conflict detection: {symbol: [(timestamp, direction, bar_index), ...]}
        self._signal_history: Dict[str, List[Tuple[datetime, str, int]]] = {}

        # HTF Bias configuration (Option A+ - soft scoring)
        htf_cfg = self.guards_config.get('htf_bias', {})
        self._enable_htf_bias = htf_cfg.get('enabled', False)
        self._htf_timeframe = htf_cfg.get('timeframe', 'H1')
        self._htf_ema_period = int(htf_cfg.get('ema_period', 50))
        self._htf_atr_period = int(htf_cfg.get('atr_period', 14))
        self._htf_neutral_zone_mult = float(htf_cfg.get('neutral_zone_atr_mult', 0.5))
        self._htf_bias_bonus = float(htf_cfg.get('bias_bonus', 0.05))
        self._htf_bias_penalty = float(htf_cfg.get('bias_penalty', 0.10))
        self._htf_override_score = float(htf_cfg.get('countertrend_override_score', 0.82))
        self._htf_hard_block = htf_cfg.get('hard_block', False)  # Can be True, False, or 'conditional'
        self._htf_hard_block_clear_mult = float(htf_cfg.get('hard_block_clear_trend_mult', 1.5))
        self._htf_lookback_bars = int(htf_cfg.get('lookback_bars', 100))
        self._htf_log_checks = htf_cfg.get('log_bias_checks', True)
        
        # Structure-specific thresholds (e.g., BoS requires higher confidence)
        self._structure_thresholds = self.guards_config.get('structure_thresholds', {})
        
        # Cache for HTF data: {symbol: {'ema': float, 'atr': float, 'close': float, 'bias': str, 'last_update': datetime}}
        self._htf_cache: Dict[str, Dict[str, Any]] = {}
        self._htf_cache_ttl_seconds = 300  # Refresh HTF data every 5 minutes (reduced from 15 to prevent stale trend data)

    def check_margin_and_risk_before_trade(
        self,
        symbol: str,
        estimated_volume: float,
        estimated_sl_distance: float
    ) -> tuple[bool, Optional[str]]:
        """
        Check margin and open risk before allowing new trade.
        
        Returns:
            (can_trade, reason)
        """
        if not self.enable_margin_guard:
            return True, None
        
        # Only check in LIVE mode with MT5 available
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return True, None
        
        if self.executor.mode != ExecutionMode.LIVE:
            return True, None
        
        try:
            # Get account state
            account = mt5.account_info()
            if account is None:
                logger.error("margin_check_failed", extra={"reason": "account_info_unavailable"})
                return True, None  # Allow trade if we can't check
            
            equity = account.equity
            margin_free = account.margin_free
            margin_level = account.margin_level if account.margin_level else 0
            
            # Get all open positions
            positions = mt5.positions_get()
            open_positions = list(positions) if positions else []
            open_count = len(open_positions)
            
            # Calculate total open risk using actual contract sizes
            total_open_risk = 0.0
            for pos in open_positions:
                if pos.sl > 0:  # Has stop loss
                    sl_distance = abs(pos.price_open - pos.sl)
                    # Get contract size for this position's symbol
                    pos_symbol_info = mt5.symbol_info(pos.symbol)
                    if pos_symbol_info:
                        contract_size = pos_symbol_info.trade_contract_size
                        pos_risk = pos.volume * sl_distance * contract_size
                        total_open_risk += pos_risk
            
            # Calculate new trade risk using actual contract size
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return True, None  # Allow if we can't get symbol info
            
            contract_size = symbol_info.trade_contract_size
            new_trade_risk = estimated_volume * estimated_sl_distance * contract_size
            
            # Total risk after new trade
            total_risk_after = total_open_risk + new_trade_risk
            total_risk_pct = (total_risk_after / equity) * 100 if equity > 0 else 0
            
            # Calculate margin requirements (symbol_info already retrieved above)
            estimated_margin_needed = estimated_volume * symbol_info.margin_initial
            
            # GUARD 1: Margin level too low
            if margin_level > 0 and margin_level < self.min_margin_level_pct:
                logger.warning("margin_guard_blocked", extra={
                    "symbol": symbol,
                    "reason": "margin_level_too_low",
                    "margin_level": margin_level,
                    "min_required": self.min_margin_level_pct,
                    "margin_free": margin_free,
                    "open_positions": open_count
                })
                return False, f"Margin level {margin_level:.0f}% < {self.min_margin_level_pct:.0f}%"
            
            # GUARD 2: Insufficient free margin
            if margin_free > 0:
                margin_usage_pct = (estimated_margin_needed / margin_free) * 100
                if margin_usage_pct > self.max_free_margin_usage_pct:
                    logger.warning("margin_guard_blocked", extra={
                        "symbol": symbol,
                        "reason": "insufficient_free_margin",
                        "estimated_margin_needed": estimated_margin_needed,
                        "margin_free": margin_free,
                        "usage_pct": margin_usage_pct,
                        "max_allowed_pct": self.max_free_margin_usage_pct,
                        "open_positions": open_count
                    })
                    return False, f"Trade needs {margin_usage_pct:.1f}% of free margin (max {self.max_free_margin_usage_pct:.0f}%)"
            
            # GUARD 3: Total open risk exceeds cap
            if total_risk_pct > self.max_total_open_risk_pct:
                logger.warning("margin_guard_blocked", extra={
                    "symbol": symbol,
                    "reason": "open_risk_cap_exceeded",
                    "total_risk_after": total_risk_after,
                    "total_risk_pct": total_risk_pct,
                    "max_open_risk_pct": self.max_total_open_risk_pct,
                    "open_positions": open_count,
                    "new_trade_risk": new_trade_risk
                })
                return False, f"Total risk {total_risk_pct:.2f}% > {self.max_total_open_risk_pct:.1f}%"
            
            # All checks passed
            logger.info("margin_check_passed", extra={
                "symbol": symbol,
                "margin_free": margin_free,
                "margin_level": margin_level,
                "open_positions": open_count,
                "total_open_risk": total_open_risk,
                "new_trade_risk": new_trade_risk,
                "total_risk_pct": total_risk_pct
            })
            
            return True, None
            
        except Exception as e:
            logger.warning("margin_check_error", extra={
                "symbol": symbol,
                "error": str(e)
            })
            return True, None  # Allow trade if check fails

    def check_position_limit(self, symbol: str, direction: str) -> Tuple[bool, Optional[str]]:
        """
        Check if we can open a new position based on position limits.
        
        Args:
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            
        Returns:
            (can_trade, reason) - True if allowed, False with reason if blocked
        """
        if not self._enable_position_limit:
            return True, None
        
        # Only check in LIVE mode with MT5 available
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return True, None
        
        if self.executor.mode != ExecutionMode.LIVE:
            return True, None
        
        try:
            # Get all open positions for this symbol
            positions = mt5.positions_get(symbol=symbol)
            if positions is None:
                positions = []
            
            total_positions = len(positions)
            same_direction_positions = sum(
                1 for p in positions 
                if (p.type == mt5.ORDER_TYPE_BUY and direction == 'BUY') or
                   (p.type == mt5.ORDER_TYPE_SELL and direction == 'SELL')
            )
            
            # Check total positions per symbol
            if total_positions >= self._max_positions_per_symbol:
                if self._log_position_limit_blocks:
                    logger.info("position_limit_blocked", extra={
                        "symbol": symbol,
                        "direction": direction,
                        "reason": "max_positions_per_symbol",
                        "current_positions": total_positions,
                        "max_allowed": self._max_positions_per_symbol
                    })
                return False, f"Max {self._max_positions_per_symbol} positions per symbol reached ({total_positions} open)"
            
            # Check positions per direction
            if same_direction_positions >= self._max_positions_per_direction:
                if self._log_position_limit_blocks:
                    logger.info("position_limit_blocked", extra={
                        "symbol": symbol,
                        "direction": direction,
                        "reason": "max_positions_per_direction",
                        "same_direction_positions": same_direction_positions,
                        "max_allowed": self._max_positions_per_direction
                    })
                return False, f"Max {self._max_positions_per_direction} {direction} positions reached ({same_direction_positions} open)"
            
            return True, None
            
        except Exception as e:
            logger.warning("position_limit_check_error", extra={
                "symbol": symbol,
                "direction": direction,
                "error": str(e)
            })
            return True, None  # Allow trade if check fails

    def check_signal_conflict(
        self, 
        symbol: str, 
        direction: str, 
        current_bar_index: int,
        confidence_score: float
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Check for conflicting signals (BUY and SELL within lookback window).
        If conflict detected, raises the required threshold.
        
        Args:
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            current_bar_index: Current bar index for lookback calculation
            confidence_score: Original confidence score of the signal
            
        Returns:
            (can_trade, adjusted_threshold, conflict_info)
        """
        if not self._enable_conflict_resolver:
            return True, 0.0, None
        
        # Initialize signal history for symbol if needed
        if symbol not in self._signal_history:
            self._signal_history[symbol] = []
        
        # Clean old signals outside lookback window
        min_bar_index = current_bar_index - self._conflict_lookback_bars
        self._signal_history[symbol] = [
            (ts, d, idx) for ts, d, idx in self._signal_history[symbol]
            if idx >= min_bar_index
        ]
        
        # Check for opposing signals in recent history
        recent_signals = self._signal_history[symbol]
        buy_count = sum(1 for _, d, _ in recent_signals if d == 'BUY')
        sell_count = sum(1 for _, d, _ in recent_signals if d == 'SELL')
        
        # Add current signal to history
        self._signal_history[symbol].append((datetime.now(timezone.utc), direction, current_bar_index))
        
        # Detect conflict: both BUY and SELL signals in lookback window
        has_conflict = (
            (direction == 'BUY' and sell_count > 0) or
            (direction == 'SELL' and buy_count > 0)
        )
        
        if has_conflict:
            adjusted_threshold = self._conflict_threshold_bump
            conflict_info = f"Conflict detected: {buy_count} BUY, {sell_count} SELL in last {self._conflict_lookback_bars} bars"
            
            if self._log_conflicts:
                logger.info("signal_conflict_detected", extra={
                    "symbol": symbol,
                    "direction": direction,
                    "buy_signals_in_window": buy_count,
                    "sell_signals_in_window": sell_count,
                    "lookback_bars": self._conflict_lookback_bars,
                    "threshold_bump": adjusted_threshold,
                    "original_confidence": float(confidence_score),
                    "required_confidence": float(confidence_score) + adjusted_threshold
                })
            
            # Check if signal meets raised threshold
            # We return the bump amount; caller decides if score is high enough
            return True, adjusted_threshold, conflict_info
        
        return True, 0.0, None

    def get_htf_bias(self, symbol: str) -> Tuple[str, float, Dict[str, Any]]:
        """
        Calculate HTF bias using EMA on H1 timeframe.
        
        Returns:
            (bias, score_modifier, details)
            - bias: 'bullish', 'bearish', or 'neutral'
            - score_modifier: bonus/penalty to apply to confidence score
            - details: dict with calculation details for logging
        """
        if not self._enable_htf_bias:
            return 'neutral', 0.0, {'enabled': False}
        
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return 'neutral', 0.0, {'error': 'mt5_unavailable'}
        
        if self.executor.mode != ExecutionMode.LIVE:
            return 'neutral', 0.0, {'error': 'not_live_mode'}
        
        now = datetime.now(timezone.utc)
        
        # Check cache first
        if symbol in self._htf_cache:
            cached = self._htf_cache[symbol]
            age_seconds = (now - cached.get('last_update', now)).total_seconds()
            if age_seconds < self._htf_cache_ttl_seconds:
                return cached['bias'], cached['score_modifier'], cached['details']
        
        try:
            # Map timeframe string to MT5 constant
            tf_map = {
                'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1, 'W1': mt5.TIMEFRAME_W1
            }
            htf = tf_map.get(self._htf_timeframe, mt5.TIMEFRAME_H1)
            
            # Fetch HTF bars
            rates = mt5.copy_rates_from_pos(symbol, htf, 0, self._htf_lookback_bars)
            if rates is None or len(rates) < max(self._htf_ema_period, self._htf_atr_period) + 1:
                return 'neutral', 0.0, {'error': 'insufficient_htf_data', 'bars': len(rates) if rates is not None else 0}
            
            # Extract close prices and calculate EMA
            closes = [float(r['close']) for r in rates]
            highs = [float(r['high']) for r in rates]
            lows = [float(r['low']) for r in rates]
            
            # Calculate EMA
            ema = self._calculate_ema(closes, self._htf_ema_period)
            if ema is None:
                return 'neutral', 0.0, {'error': 'ema_calculation_failed'}
            
            # Calculate ATR for neutral zone
            atr = self._calculate_atr(highs, lows, closes, self._htf_atr_period)
            if atr is None or atr <= 0:
                return 'neutral', 0.0, {'error': 'atr_calculation_failed'}
            
            current_close = closes[-1]
            neutral_zone = atr * self._htf_neutral_zone_mult
            
            # Determine bias
            if current_close > ema + neutral_zone:
                bias = 'bullish'
            elif current_close < ema - neutral_zone:
                bias = 'bearish'
            else:
                bias = 'neutral'
            
            # Score modifier is 0 for neutral (applied per-trade based on direction)
            score_modifier = 0.0  # Will be calculated per-trade in apply_htf_bias
            
            details = {
                'timeframe': self._htf_timeframe,
                'ema': round(ema, 5),
                'atr': round(atr, 5),
                'current_close': round(current_close, 5),
                'neutral_zone': round(neutral_zone, 5),
                'upper_bound': round(ema + neutral_zone, 5),
                'lower_bound': round(ema - neutral_zone, 5),
                'bias': bias
            }
            
            # Cache the result
            self._htf_cache[symbol] = {
                'bias': bias,
                'score_modifier': score_modifier,
                'details': details,
                'last_update': now
            }
            
            return bias, score_modifier, details
            
        except Exception as e:
            logger.warning("htf_bias_calculation_error", extra={
                "symbol": symbol,
                "error": str(e)
            })
            return 'neutral', 0.0, {'error': str(e)}

    def apply_htf_bias(
        self, 
        symbol: str, 
        direction: str, 
        original_score: float,
        structure_type: str = ""
    ) -> Tuple[float, bool, Dict[str, Any]]:
        """
        Apply HTF bias to a trade decision.
        
        Args:
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            original_score: Original confidence score
            structure_type: Structure type (e.g., 'rejection', 'engulfing') for elite override eligibility
            
        Returns:
            (adjusted_score, should_block, details)
            - adjusted_score: Score after applying bonus/penalty
            - should_block: True if hard_block is on and trade is counter-trend without override
            - details: Dict with calculation details for logging
        """
        if not self._enable_htf_bias:
            return original_score, False, {'enabled': False}
        
        bias, _, htf_details = self.get_htf_bias(symbol)
        
        # Determine alignment
        is_aligned = (
            (bias == 'bullish' and direction == 'BUY') or
            (bias == 'bearish' and direction == 'SELL')
        )
        is_counter = (
            (bias == 'bullish' and direction == 'SELL') or
            (bias == 'bearish' and direction == 'BUY')
        )
        is_neutral = (bias == 'neutral')
        
        # Calculate score adjustment
        if is_aligned:
            score_modifier = self._htf_bias_bonus
            alignment = 'aligned'
        elif is_counter:
            score_modifier = -self._htf_bias_penalty
            alignment = 'counter'
        else:
            score_modifier = 0.0
            alignment = 'neutral'
        
        adjusted_score = original_score + score_modifier
        
        # Determine if we're in a clear trend FIRST (before elite override check)
        # This must be calculated regardless of elite override status
        is_clear_trend = False
        if is_counter and self._htf_hard_block == 'conditional':
            ema = htf_details.get('ema', 0)
            current_close = htf_details.get('current_close', 0)
            neutral_zone = htf_details.get('neutral_zone', 0)
            
            if ema and current_close and neutral_zone:
                distance_from_ema = abs(current_close - ema)
                clear_threshold = neutral_zone * self._htf_hard_block_clear_mult
                is_clear_trend = distance_from_ema > clear_threshold
        
        # Check for elite override (counter-trend but high confidence)
        # CRITICAL FIX: Elite override is NOT allowed when is_clear_trend is true
        # This prevents high-confidence counter-trend trades in obvious trends
        # ADDITIONAL FIX: Rejection signals are NOT eligible for elite override
        # because big rejection candles often occur as counter-trend bounces in strong trends
        elite_eligible_structures = {'engulfing', 'order_block', 'break_of_structure', 'fair_value_gap'}
        is_elite_eligible = structure_type in elite_eligible_structures or structure_type == ""
        elite_override = is_counter and original_score >= self._htf_override_score and not is_clear_trend and is_elite_eligible
        
        # Determine if we should hard block
        # Supports: True (always block counter), False (never block), 'conditional' (block only clear trends)
        should_block = False
        
        if is_counter and not elite_override:
            if self._htf_hard_block == True:
                # Always hard block counter-trend (unless elite)
                should_block = True
            elif self._htf_hard_block == 'conditional':
                # Block when price is clearly outside neutral zone
                # is_clear_trend already calculated above
                should_block = is_clear_trend
        
        details = {
            'htf_bias': bias,
            'direction': direction,
            'alignment': alignment,
            'original_score': round(original_score, 4),
            'score_modifier': round(score_modifier, 4),
            'adjusted_score': round(adjusted_score, 4),
            'elite_override': elite_override,
            'override_threshold': self._htf_override_score,
            'hard_block_mode': self._htf_hard_block,
            'is_clear_trend': is_clear_trend,
            'should_block': should_block,
            **htf_details
        }
        
        if self._htf_log_checks:
            logger.info("htf_bias_applied", extra={
                "symbol": symbol,
                **details
            })
        
        return adjusted_score, should_block, details

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate EMA for the given prices."""
        if len(prices) < period:
            return None
        
        multiplier = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period  # SMA for initial value
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema

    def _calculate_atr(
        self, 
        highs: List[float], 
        lows: List[float], 
        closes: List[float], 
        period: int
    ) -> Optional[float]:
        """Calculate ATR for the given OHLC data."""
        if len(highs) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return None
        
        # Simple average of last 'period' true ranges
        return sum(true_ranges[-period:]) / period

    def track_position_closes(self):
        """Check for closed positions since last check and log them."""
        position_tracking = self.guards_config.get('position_tracking', {})
        if not position_tracking.get('enabled', True):
            return
        
        # Only track in LIVE mode with MT5 available
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return
        
        if self.executor.mode != ExecutionMode.LIVE:
            return
        
        try:
            # Get deals since last check
            from_date = self.last_position_check_time
            to_date = datetime.now(timezone.utc)
            
            deals = mt5.history_deals_get(from_date, to_date)
            if deals is None or len(deals) == 0:
                self.last_position_check_time = to_date
                return
            
            # Filter for position closes (DEAL_ENTRY_OUT)
            for deal in deals:
                if deal.entry == mt5.DEAL_ENTRY_OUT:  # Position close
                    # Get original position details
                    position_ticket = deal.position_id
                    
                    # Try to get original order details
                    orders = mt5.history_orders_get(position=position_ticket)
                    original_order = orders[0] if orders and len(orders) > 0 else None
                    
                    # Determine close reason
                    close_reason = "unknown"
                    comment_lower = deal.comment.lower() if deal.comment else ""
                    if "sl" in comment_lower or "stop" in comment_lower:
                        close_reason = "sl_hit"
                    elif "tp" in comment_lower or "profit" in comment_lower:
                        close_reason = "tp_hit"
                    elif "manual" in comment_lower:
                        close_reason = "manual"
                    elif comment_lower:
                        close_reason = deal.comment
                    
                    # Calculate duration
                    duration_seconds = None
                    if original_order and hasattr(original_order, 'time_setup'):
                        try:
                            duration_seconds = (deal.time - original_order.time_setup).total_seconds()
                        except:
                            pass
                    
                    # Log position close (existing behavior)
                    logger.info("position_closed", extra={
                        "ticket": position_ticket,
                        "deal_ticket": deal.ticket,
                        "symbol": deal.symbol,
                        "volume": deal.volume,
                        "entry_price": original_order.price_open if original_order else None,
                        "close_price": deal.price,
                        "profit": deal.profit,
                        "close_reason": close_reason,
                        "close_time": deal.time.isoformat() if hasattr(deal.time, 'isoformat') else str(deal.time),
                        "duration_seconds": duration_seconds
                    })
                    
                    # Record outcome in trade journal
                    if self.trade_journal is not None:
                        try:
                            # Get point for pip calculation
                            symbol_info = mt5.symbol_info(deal.symbol)
                            point = symbol_info.point if symbol_info else None
                            
                            self.trade_journal.record_outcome(
                                ticket=position_ticket,
                                exit_price=deal.price,
                                exit_reason=close_reason,
                                pnl_usd=deal.profit,
                                exit_time=to_date,
                                symbol=deal.symbol,
                                volume=deal.volume,
                                point=point
                            )
                        except Exception as je:
                            logger.warning("trade_journal_record_failed", extra={
                                "ticket": position_ticket,
                                "error": str(je)
                            })
            
            # Update last check time
            self.last_position_check_time = to_date
            
        except Exception as e:
            logger.warning("position_tracking_error", extra={
                "error": str(e)
            })

    def process_bar(self, data: OHLCV, timestamp: datetime) -> List[Decision]:
        """Process a single bar through the pipeline."""
        decisions: List[Decision] = []

        try:
            # NEW: Track position closes at start of each bar
            self.track_position_closes()
            
            # Session rotation + optional close-out (PR1)
            prev_sess, new_sess = self.session_mgr.update_and_rotate(timestamp)
            if new_sess is not None:
                logger.info("session_rotated", extra={"from": prev_sess, "to": self.session_mgr.current_session})
                if prev_sess and self.session_mgr.autonomy.get("close_positions_on_session_end", False):
                    self.executor.close_positions(self.session_mgr.tracked_symbols)

            # Daily reset for soft stop and baseline equity (00:00 UTC)
            current_date = timestamp.date()
            if self._last_reset_date is None or current_date > self._last_reset_date:
                # Get current equity for new baseline
                if hasattr(self.executor, "get_equity"):
                    try:
                        current_equity = float(self.executor.get_equity())
                    except Exception:
                        current_equity = self.default_equity
                else:
                    current_equity = self.default_equity
                
                if self._dd_soft_triggered or self._dd_baseline_equity is not None:
                    logger.info("daily_reset_soft_stop", extra={
                        "date": current_date.isoformat(),
                        "previous_soft_stop": self._dd_soft_triggered,
                        "previous_baseline_equity": self._dd_baseline_equity,
                        "new_baseline_equity": current_equity,
                    })
                
                # Set new baseline to current equity at midnight
                self._dd_soft_triggered = False
                self._dd_baseline_equity = current_equity
                self._last_reset_date = current_date
                
                # Reset FTMO daily tracking with current equity as starting point
                self._ftmo_daily_equity_low = current_equity
                self._ftmo_daily_warning_logged = False
                self._ftmo_daily_stop_triggered = False

            # Market guards (PR1)
            if not self.executor.is_market_open() or not self.executor.is_symbol_tradable(data.symbol):
                logger.info(
                    "market_closed_skip",
                    extra={"symbol": data.symbol, "session": self.session_mgr.current_session, "timestamp": timestamp.isoformat()},
                )
                return decisions

            # Count the bar EARLY so early-return paths still count
            self.processed_bars += 1

            # Circuit breaker gate (PR2)
            if self.session_mgr.session_counters.get("full_sl_hits", 0) >= self.session_mgr.get_max_full_sl_hits():
                logger.info(
                    "circuit_breaker_tripped",
                    extra={"session": self.session_mgr.current_session, "full_sl_hits": self.session_mgr.session_counters.get("full_sl_hits", 0)},
                )
                return decisions

            # Volatility pause auto-resume (PR2)
            if self.session_mgr.clear_pause_if_elapsed(timestamp):
                logger.info("volatility_pause_cleared", extra={"session": self.session_mgr.current_session, "timestamp": timestamp.isoformat()})
            if self.session_mgr.is_paused(timestamp):
                logger.info("volatility_pause_active", extra={"session": self.session_mgr.current_session, "timestamp": timestamp.isoformat()})
                return decisions

            # Volatility pause trigger (spread/ATR) (PR2)
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
                    from datetime import timedelta
                    pause_secs = int(vp.get("min_pause_seconds", 120))
                    until = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
                    self.session_mgr.pause_until(until + timedelta(seconds=pause_secs))
                    logger.info(
                        "volatility_pause",
                        extra={
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
                        },
                    )
                    return decisions

        except Exception as e:
            logger.exception(
                "pipeline_processing_error",
                extra={"error": str(e), "symbol": getattr(data, "symbol", None), "timestamp": timestamp.isoformat()},
            )

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

            # Decision generation (structure-first exit plan + clamps)
            decisions = self._process_decision_generation(structures, data, timestamp)
            logger.debug("stage_5_decisions_generated", extra={"count": len(decisions)})

            # Deduplicate: take only the best decision per bar to prevent multiple orders
            if len(decisions) > 1:
                original_count = len(decisions)
                # Sort by confidence score (highest first)
                decisions = sorted(decisions, key=lambda d: float(d.confidence_score or 0.0), reverse=True)
                # Keep only the best decision
                best_decision = decisions[0]
                decisions = [best_decision]
                logger.info(
                    "decisions_deduplicated",
                    extra={
                        "symbol": data.symbol,
                        "original_count": original_count,
                        "kept_count": 1,
                        "best_structure": best_decision.metadata.get("structure_type", "unknown") if best_decision.metadata else "unknown",
                        "best_confidence": float(best_decision.confidence_score or 0.0),
                    },
                )

            # ---- PR3: Risk sizing + per-symbol open-risk cap, then execute ----
            if self.executor.enabled and decisions:
                # Check if daily soft stop has been triggered - if so, skip execution
                if self._dd_soft_triggered:
                    logger.info(
                        "execution_skipped_soft_stop",
                        extra={
                            "symbol": data.symbol,
                            "reason": "daily_soft_stop_active",
                        },
                    )
                    return decisions
                
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

                if (
                    self.executor.mode == ExecutionMode.LIVE
                    and getattr(self.executor, "enable_real_mt5_orders", False)
                ):
                    if self._dd_baseline_equity is None:
                        self._dd_baseline_equity = equity
                    if self._dd_baseline_equity and self._dd_baseline_equity > 0:
                        dd_frac = (equity - self._dd_baseline_equity) / self._dd_baseline_equity
                        if (not self._dd_hard_triggered) and dd_frac <= self._dd_hard_stop_frac:
                            self._dd_hard_triggered = True
                            self._dd_soft_triggered = True
                            try:
                                self.executor.close_positions([sym])
                            except Exception:
                                pass
                            logger.info(
                                "daily_hard_stop_hit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "baseline_equity": self._dd_baseline_equity,
                                    "dd_frac": float(dd_frac),
                                },
                            )
                            return decisions
                        if (not self._dd_soft_triggered) and dd_frac <= self._dd_soft_stop_frac:
                            self._dd_soft_triggered = True
                            logger.info(
                                "daily_soft_stop_hit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "baseline_equity": self._dd_baseline_equity,
                                    "dd_frac": float(dd_frac),
                                },
                            )
                            return decisions

                    # FTMO equity-based monitoring (shadow safety layer)
                    # Initialize account start equity if not set
                    if self._ftmo_account_start_equity is None:
                        self._ftmo_account_start_equity = equity
                    
                    # Track intra-day equity low
                    if self._ftmo_daily_equity_low is None or equity < self._ftmo_daily_equity_low:
                        self._ftmo_daily_equity_low = equity
                    
                    # Track all-time equity low
                    if self._ftmo_total_equity_low is None or equity < self._ftmo_total_equity_low:
                        self._ftmo_total_equity_low = equity
                    
                    # Compute daily drawdown from baseline (intra-day low)
                    if self._dd_baseline_equity and self._dd_baseline_equity > 0:
                        ftmo_daily_dd_pct = ((self._ftmo_daily_equity_low - self._dd_baseline_equity) / self._dd_baseline_equity) * 100.0
                        
                        # Hard stop at FTMO daily limit (-5%)
                        if (not self._ftmo_daily_stop_triggered) and ftmo_daily_dd_pct <= self._ftmo_max_daily_loss_pct:
                            self._ftmo_daily_stop_triggered = True
                            try:
                                self.executor.close_positions([sym])
                            except Exception:
                                pass
                            logger.critical(
                                "ftmo_daily_limit_hit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "daily_equity_low": self._ftmo_daily_equity_low,
                                    "baseline_equity": self._dd_baseline_equity,
                                    "daily_dd_pct": float(ftmo_daily_dd_pct),
                                    "ftmo_limit_pct": self._ftmo_max_daily_loss_pct,
                                    "env_mode": self._env_mode,
                                },
                            )
                            return decisions
                        
                        # Warning at -3% daily
                        if (not self._ftmo_daily_warning_logged) and ftmo_daily_dd_pct <= self._ftmo_daily_warning_pct:
                            self._ftmo_daily_warning_logged = True
                            logger.warning(
                                "approaching_ftmo_daily_limit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "daily_equity_low": self._ftmo_daily_equity_low,
                                    "baseline_equity": self._dd_baseline_equity,
                                    "daily_dd_pct": float(ftmo_daily_dd_pct),
                                    "warning_threshold_pct": self._ftmo_daily_warning_pct,
                                    "ftmo_limit_pct": self._ftmo_max_daily_loss_pct,
                                    "env_mode": self._env_mode,
                                },
                            )
                    
                    # Compute total drawdown from account start (all-time low)
                    if self._ftmo_account_start_equity and self._ftmo_account_start_equity > 0:
                        ftmo_total_dd_pct = ((self._ftmo_total_equity_low - self._ftmo_account_start_equity) / self._ftmo_account_start_equity) * 100.0
                        
                        # Hard stop at FTMO total limit (-10%)
                        if (not self._ftmo_total_stop_triggered) and ftmo_total_dd_pct <= self._ftmo_max_total_loss_pct:
                            self._ftmo_total_stop_triggered = True
                            try:
                                self.executor.close_positions([sym])
                            except Exception:
                                pass
                            logger.critical(
                                "ftmo_total_limit_hit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "total_equity_low": self._ftmo_total_equity_low,
                                    "account_start_equity": self._ftmo_account_start_equity,
                                    "total_dd_pct": float(ftmo_total_dd_pct),
                                    "ftmo_limit_pct": self._ftmo_max_total_loss_pct,
                                    "env_mode": self._env_mode,
                                },
                            )
                            return decisions
                        
                        # Warning at -7% total
                        if (not self._ftmo_total_warning_logged) and ftmo_total_dd_pct <= self._ftmo_total_warning_pct:
                            self._ftmo_total_warning_logged = True
                            logger.warning(
                                "approaching_ftmo_total_limit",
                                extra={
                                    "session": self.session_mgr.current_session,
                                    "symbol": sym,
                                    "equity": equity,
                                    "total_equity_low": self._ftmo_total_equity_low,
                                    "account_start_equity": self._ftmo_account_start_equity,
                                    "total_dd_pct": float(ftmo_total_dd_pct),
                                    "warning_threshold_pct": self._ftmo_total_warning_pct,
                                    "ftmo_limit_pct": self._ftmo_max_total_loss_pct,
                                    "env_mode": self._env_mode,
                                },
                            )

                    if self._consecutive_send_failures >= max(self._dd_max_consecutive_failures, 0):
                        logger.info(
                            "order_send_failure_pause",
                            extra={
                                "session": self.session_mgr.current_session,
                                "symbol": sym,
                                "consecutive_failures": self._consecutive_send_failures,
                            },
                        )
                        return decisions

                if hasattr(self.executor, "get_open_risk_by_symbol"):
                    try:
                        open_risk_before_fn = self.executor.get_open_risk_by_symbol
                    except Exception:
                        open_risk_before_fn = None
                else:
                    open_risk_before_fn = None

                per_trade_pct = float(self.risk_cfg.get("per_trade_pct", 0.0025))
                cap_pct = float(self.risk_cfg.get("per_symbol_open_risk_cap_pct", 0.0075))
                risk_budget = max(equity * per_trade_pct, 0.0)
                cap_budget = equity * cap_pct

                # Optional probation overrides (no-op for now; future PR may adjust risk caps/RR)
                if self.onboarding_mgr is not None:
                    try:
                        derived_risk_cfg = self.onboarding_mgr.apply_probation_overrides(sym, {
                            "per_trade_pct": per_trade_pct,
                            "per_symbol_open_risk_cap_pct": cap_pct,
                        })
                        per_trade_pct = float(derived_risk_cfg.get("per_trade_pct", per_trade_pct))
                        cap_pct = float(derived_risk_cfg.get("per_symbol_open_risk_cap_pct", cap_pct))
                        risk_budget = max(equity * per_trade_pct, 0.0)
                        cap_budget = equity * cap_pct
                    except Exception:
                        # If onboarding manager fails, fall back to original risk config
                        pass

                for idx, decision in enumerate(decisions):
                    stop_distance_points = abs(float(decision.entry_price) - float(decision.stop_loss)) / max(point, 1e-12)
                    if stop_distance_points <= 0:
                        logger.info(
                            "risk_too_small",
                            extra={
                                "session": self.session_mgr.current_session,
                                "symbol": sym,
                                "equity": equity,
                                "per_trade_pct": per_trade_pct,
                                "reason": "non_positive_stop_distance",
                            },
                        )
                        continue

                    # Reject setups with SL tighter than broker hard floor before sizing
                    sl_hard_floor_points = float(meta.get("sl_hard_floor_points", 0))
                    if sl_hard_floor_points > 0 and stop_distance_points < sl_hard_floor_points:
                        logger.info(
                            "setup_rejected_tight_sl",
                            extra={
                                "session": self.session_mgr.current_session,
                                "symbol": sym,
                                "stop_distance_points": stop_distance_points,
                                "sl_hard_floor_points": sl_hard_floor_points,
                                "reason": "sl_tighter_than_broker_minimum",
                            },
                        )
                        continue

                    point_value_per_lot = contract_size * point
                    volume_raw = risk_budget / max((stop_distance_points * point_value_per_lot), 1e-12)
                    steps = max(int(volume_raw / lot_step), 0)
                    volume_rounded = steps * lot_step
                    if volume_rounded < min_lot:
                        logger.info(
                            "risk_too_small",
                            extra={
                                "session": self.session_mgr.current_session,
                                "symbol": sym,
                                "equity": equity,
                                "per_trade_pct": per_trade_pct,
                                "min_lot": min_lot,
                                "computed_volume": volume_raw,
                            },
                        )
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
                        logger.info(
                            "risk_cap_hit",
                            extra={
                                "session": self.session_mgr.current_session,
                                "symbol": sym,
                                "open_risk": open_risk_before,
                                "new_trade_risk": new_trade_risk,
                                "cap_pct": cap_pct,
                                "equity": equity,
                            },
                        )
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
                        position_size=Decimal(str(volume_rounded)),
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
                            "risk_budget": float(risk_budget),
                            "cap_budget": float(cap_budget),
                            "session": self.session_mgr.current_session,
                            "entry": float(sized_decision.entry_price),
                            "sl": float(sized_decision.stop_loss),
                            "tp": float(sized_decision.take_profit),
                        },
                    )

                    should_exec = True
                    onboarding_state = None
                    if self.onboarding_mgr is not None:
                        try:
                            onboarding_state = self.onboarding_mgr.get_state(sym)
                            should_exec = self.onboarding_mgr.should_execute(sym)
                        except Exception:
                            should_exec = True

                    if should_exec:
                        # NEW: Margin and risk guard before execution
                        can_trade, margin_reason = self.check_margin_and_risk_before_trade(
                            symbol=sym,
                            estimated_volume=float(sized_decision.position_size),
                            estimated_sl_distance=abs(float(sized_decision.entry_price) - float(sized_decision.stop_loss))
                        )
                        
                        if not can_trade:
                            logger.info("trade_blocked_by_margin_guard", extra={
                                "symbol": sym,
                                "reason": margin_reason,
                                "volume": float(sized_decision.position_size),
                                "entry": float(sized_decision.entry_price),
                                "sl": float(sized_decision.stop_loss)
                            })
                            continue  # Skip this trade
                        
                        # Structure-specific threshold check (e.g., BoS requires 0.70)
                        direction_str = sized_decision.decision_type.value
                        structure_type = sized_decision.metadata.get("structure_type", "unknown")
                        
                        # Check for direction-specific threshold first (e.g., rejection_buy)
                        # Falls back to general structure threshold if direction-specific not found
                        direction_specific_key = f"{structure_type}_{direction_str.lower()}"
                        structure_threshold = self._structure_thresholds.get(direction_specific_key)
                        if structure_threshold is None:
                            structure_threshold = self._structure_thresholds.get(structure_type)
                        
                        if structure_threshold is not None:
                            current_confidence = float(sized_decision.confidence_score)
                            if current_confidence < structure_threshold:
                                logger.info("trade_blocked_by_structure_threshold", extra={
                                    "symbol": sym,
                                    "direction": direction_str,
                                    "structure_type": structure_type,
                                    "confidence": current_confidence,
                                    "required_threshold": structure_threshold
                                })
                                continue  # Skip this trade
                        
                        # Position limit check - prevents stacking
                        can_trade_pos, pos_reason = self.check_position_limit(sym, direction_str)
                        if not can_trade_pos:
                            logger.info("trade_blocked_by_position_limit", extra={
                                "symbol": sym,
                                "direction": direction_str,
                                "reason": pos_reason,
                                "structure_type": sized_decision.metadata.get("structure_type", "unknown"),
                                "confidence": float(sized_decision.confidence_score)
                            })
                            continue  # Skip this trade
                        
                        # Conflict resolver check - raises threshold when BUY+SELL conflict
                        _, threshold_bump, conflict_info = self.check_signal_conflict(
                            symbol=sym,
                            direction=direction_str,
                            current_bar_index=self.processed_bars,
                            confidence_score=float(sized_decision.confidence_score)
                        )
                        
                        if threshold_bump > 0:
                            # Get base threshold from config based on current session
                            current_session = self.session_mgr.current_session if self.session_mgr else "LONDON"
                            scales = (self.config.structure_configs or {}).get("scoring", {}).get("scales", {})
                            session_config = scales.get("M15", {}).get("fx", {}).get(current_session, {})
                            base_threshold = float(session_config.get("min_composite", 0.45))
                            required_threshold = base_threshold + threshold_bump
                            
                            if float(sized_decision.confidence_score) < required_threshold:
                                logger.info("trade_blocked_by_conflict_resolver", extra={
                                    "symbol": sym,
                                    "direction": direction_str,
                                    "confidence": float(sized_decision.confidence_score),
                                    "base_threshold": base_threshold,
                                    "threshold_bump": threshold_bump,
                                    "required_threshold": required_threshold,
                                    "conflict_info": conflict_info,
                                    "structure_type": sized_decision.metadata.get("structure_type", "unknown")
                                })
                                continue  # Skip this trade
                        
                        # HTF Bias check - applies score modifier and optional hard block
                        original_confidence = float(sized_decision.confidence_score)
                        adjusted_confidence, htf_blocked, htf_details = self.apply_htf_bias(
                            symbol=sym,
                            direction=direction_str,
                            original_score=original_confidence,
                            structure_type=structure_type
                        )
                        
                        if htf_blocked:
                            logger.info("trade_blocked_by_htf_bias", extra={
                                "symbol": sym,
                                "direction": direction_str,
                                "original_confidence": original_confidence,
                                "htf_bias": htf_details.get('htf_bias', 'unknown'),
                                "alignment": htf_details.get('alignment', 'unknown'),
                                "structure_type": sized_decision.metadata.get("structure_type", "unknown")
                            })
                            continue  # Skip this trade
                        
                        # Update decision metadata with HTF bias info
                        sized_decision.metadata['htf_bias'] = htf_details.get('htf_bias', 'neutral')
                        sized_decision.metadata['htf_alignment'] = htf_details.get('alignment', 'neutral')
                        sized_decision.metadata['htf_score_modifier'] = htf_details.get('score_modifier', 0.0)
                        sized_decision.metadata['confidence_after_htf'] = adjusted_confidence
                        
                        # Session filter check - block bad symbol/session combos
                        if self.session_filter is not None:
                            should_block, session_name, session_relevance = self.session_filter.should_block(sym)
                            if should_block:
                                logger.info("trade_blocked_by_session_filter", extra={
                                    "symbol": sym,
                                    "direction": direction_str,
                                    "session_name": session_name,
                                    "session_relevance": session_relevance,
                                    "structure_type": sized_decision.metadata.get("structure_type", "unknown"),
                                    "confidence": float(sized_decision.confidence_score)
                                })
                                continue  # Skip this trade
                        
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

                        # Enhanced exit logging for FTMO analysis
                        if getattr(execution_result, "success", False):
                            meta = sized_decision.metadata
                            entry = float(sized_decision.entry_price)
                            sl_final = float(sized_decision.stop_loss)
                            tp_final = float(sized_decision.take_profit)
                            point = float(self.broker_symbols.get(sym, {}).get("point", 0.0001))
                            
                            # Calculate distances in points
                            if sized_decision.decision_type == DecisionType.BUY:
                                sl_distance_points = (entry - sl_final) / point if point > 0 else 0
                                tp_distance_points = (tp_final - entry) / point if point > 0 else 0
                            else:
                                sl_distance_points = (sl_final - entry) / point if point > 0 else 0
                                tp_distance_points = (entry - tp_final) / point if point > 0 else 0
                            
                            # Calculate intended RR
                            risk_dist = abs(entry - sl_final)
                            reward_dist = abs(tp_final - entry)
                            intended_rr = reward_dist / risk_dist if risk_dist > 0 else 0
                            
                            # Get session context for trade journal
                            session_name = ""
                            session_relevance = ""
                            if self.session_filter is not None:
                                try:
                                    session_name, session_relevance, _ = self.session_filter.evaluate(
                                        symbol=sym,
                                        direction=sized_decision.decision_type.value,
                                        structure_type=meta.get("structure_type", "unknown"),
                                        confidence=float(sized_decision.confidence_score)
                                    )
                                except Exception:
                                    pass
                            
                            # Cache entry in trade journal for outcome tracking
                            if self.trade_journal is not None:
                                ticket = getattr(execution_result, "order_id", None)
                                if ticket:
                                    try:
                                        # Compute HTF distance in ATR units
                                        htf_distance_atr = None
                                        ema = htf_details.get('ema')
                                        atr = htf_details.get('atr')
                                        current_close = htf_details.get('current_close')
                                        if ema and atr and current_close and atr > 0:
                                            htf_distance_atr = round(abs(current_close - ema) / atr, 3)
                                        
                                        self.trade_journal.cache_entry(
                                            ticket=ticket,
                                            symbol=sym,
                                            direction=sized_decision.decision_type.value,
                                            structure_type=meta.get("structure_type", "unknown"),
                                            entry_price=entry,
                                            sl=sl_final,
                                            tp=tp_final,
                                            volume=float(sized_decision.position_size),
                                            intended_rr=intended_rr,
                                            magic=0,
                                            comment=f"DEVI_{meta.get('structure_type', 'UNKNOWN')}",
                                            session_name=session_name,
                                            session_relevance=session_relevance,
                                            htf_bias=htf_details.get('htf_bias', ''),
                                            htf_alignment=htf_details.get('alignment', ''),
                                            htf_distance_atr=htf_distance_atr,
                                            htf_clear_trend=htf_details.get('is_clear_trend')
                                        )
                                    except Exception as je:
                                        logger.warning("trade_journal_cache_failed", extra={
                                            "ticket": ticket,
                                            "symbol": sym,
                                            "error": str(je)
                                        })
                            
                            logger.info(
                                "trade_executed_enhanced",
                                extra={
                                    "symbol": sym,
                                    "order_type": sized_decision.decision_type.value,
                                    "exit_method": meta.get("exit_method", "unknown"),
                                    "structure_type": meta.get("structure_type", "unknown"),
                                    "entry": entry,
                                    "sl_requested": meta.get("sl_requested"),
                                    "sl_final": sl_final,
                                    "tp_requested": meta.get("tp_requested"),
                                    "tp_final": tp_final,
                                    "sl_distance_points": float(sl_distance_points),
                                    "tp_distance_points": float(tp_distance_points),
                                    "computed_rr": float(meta.get("post_clamp_rr", 0)),
                                    "clamped": meta.get("clamped", False),
                                    "volume": float(sized_decision.position_size),
                                    "env_mode": meta.get("env_mode", "unknown"),
                                    "session": self.session_mgr.current_session,
                                },
                            )

                        if (
                            self.executor.mode == ExecutionMode.LIVE
                            and getattr(self.executor, "enable_real_mt5_orders", False)
                        ):
                            if getattr(execution_result, "success", False):
                                # Reset failure counter on success
                                self._consecutive_send_failures = 0
                                self._last_failure_time = None
                            elif not getattr(execution_result, "precheck_block", False):
                                # Only count actual broker failures, not pre-check blocks
                                self._consecutive_send_failures += 1
                                self._last_failure_time = datetime.now(timezone.utc)
                            
                            # Cooldown reset: if enough time passed since last failure, reset counter
                            # This prevents temporary market conditions from killing the whole session
                            if (
                                self._last_failure_time is not None
                                and self._consecutive_send_failures > 0
                            ):
                                elapsed = (datetime.now(timezone.utc) - self._last_failure_time).total_seconds()
                                if elapsed > self._failure_cooldown_seconds:
                                    logger.info("failure_counter_cooldown_reset", extra={
                                        "previous_failures": self._consecutive_send_failures,
                                        "elapsed_seconds": elapsed,
                                        "cooldown_seconds": self._failure_cooldown_seconds,
                                    })
                                    self._consecutive_send_failures = 0
                                    self._last_failure_time = None

                        # Track open-risk accumulation in dry-run if executor supports it
                        if getattr(execution_result, "success", False) and hasattr(self.executor, "add_open_risk"):
                            try:
                                self.executor.add_open_risk(sym, new_trade_risk)
                            except Exception:
                                pass
                    else:
                        logger.info(
                            "symbol_onboarding_state",
                            extra={
                                "symbol": sym,
                                "state": (onboarding_state or {}).get("state", "observe_only"),
                                "execute": False,
                                "reason": "observe_only",
                                "sessions_seen": (onboarding_state or {}).get("sessions_seen"),
                                "trades_seen": (onboarding_state or {}).get("trades_seen"),
                                "validation_errors": (onboarding_state or {}).get("validation_errors"),
                            },
                        )

                # Record onboarding counters after processing sized decisions
                if self.onboarding_mgr is not None and decisions:
                    try:
                        self.onboarding_mgr.record_decisions(
                            symbol=sym,
                            decisions=decisions,
                            session_id=self.session_mgr.current_session if self.session_mgr else None,
                            validation_errors=0,
                        )
                    except Exception:
                        pass

            # stats
            self.decisions_generated += len(decisions)

            # Session counters (PR1)
            self.session_mgr.session_counters["decisions_attempted"] += len(structures)
            self.session_mgr.session_counters["decisions_accepted"] += len(decisions)
            logger.info(
                "session_counters",
                extra={
                    "session": self.session_mgr.current_session,
                    "decisions_attempted": self.session_mgr.session_counters["decisions_attempted"],
                    "decisions_accepted": self.session_mgr.session_counters["decisions_accepted"],
                    "timestamp": timestamp.isoformat(),
                },
            )

        except Exception as e:
            logger.exception(
                "pipeline_processing_error",
                extra={"error": str(e), "symbol": getattr(data, "symbol", None), "timestamp": timestamp.isoformat()},
            )

        return decisions

    def _process_pre_filters(self, data: OHLCV) -> bool:
        is_test_mode = self.config.system_configs.get("synthetic_mode", False) or \
                       self.config.system_configs.get("data_source") in ["synthetic", "csv"]
        min_bars = 5 if is_test_mode else 50
        return len(data.bars) >= min_bars

    def _process_indicators(self, data: OHLCV) -> bool:
        atr = compute_atr_simple(list(data.bars), 14)
        return atr is not None

    def _process_structure_detection(self, data: OHLCV) -> List[Structure]:
        return self.structure_manager.detect_structures(data, "test_session")

    def _process_decision_generation(self, structures: List[Structure], data: OHLCV, timestamp: datetime) -> List[Decision]:
        decisions: List[Decision] = []

        atr_val = compute_atr_simple(list(data.bars), 14)
        atr_val = Decimal(str(atr_val)) if atr_val is not None else None
        entry_price = data.latest_bar.close

        for structure in structures:
            try:
                decision_type = DecisionType.BUY if structure.is_bullish else DecisionType.SELL

                # Defaults
                planned_sl = None
                planned_tp = None
                planned_method = "legacy"
                expected_rr = None
                sl_requested = None
                tp_requested = None
                clamped = False

                # Structure-first exit planning (if enabled and ATR available)
                if self.exit_planner and atr_val is not None and getattr(self.exit_planner, "cfg", {}).get("enabled", False):
                    side_str = "BUY" if decision_type == DecisionType.BUY else "SELL"

                    def _nearest(structs, t):
                        c = [s for s in structs if s.structure_type.value == t]
                        return min(c, key=lambda s: abs(s.midpoint - entry_price)) if c else None

                    ob = _nearest(structures, "order_block")
                    fvg = _nearest(structures, "fair_value_gap")
                    uzr = _nearest(structures, "rejection")

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
                    if uzr:
                        # UZR zone boundaries are the high/low of the rejection structure
                        zone_low = min(uzr.high_price, uzr.low_price)
                        zone_high = max(uzr.high_price, uzr.low_price)
                        structures_map["rejection"] = {
                            "nearest": {
                                "zone_low": Decimal(str(zone_low)),
                                "zone_high": Decimal(str(zone_high)),
                                "side": "BUY" if uzr.is_bullish else "SELL",
                                "age": int(uzr.metadata.get("age_bars", 0)),
                                "quality": Decimal(str(uzr.quality_score)),
                            }
                        }

                    plan = self.exit_planner.plan(side=side_str, entry=entry_price, atr=atr_val, structures=structures_map)
                    if plan:
                        planned_sl = Decimal(str(plan["sl"]))
                        planned_tp = Decimal(str(plan["tp"]))
                        planned_method = plan.get("method", "atr")
                        expected_rr = plan.get("expected_rr")
                        sl_requested = plan.get("sl_requested")
                        tp_requested = plan.get("tp_requested")
                        clamped = plan.get("clamped", False)

                # Use planned values if available; otherwise fallback
                if planned_sl is not None and planned_tp is not None:
                    stop_loss = planned_sl
                    take_profit = planned_tp
                else:
                    # Log when legacy exit method is used
                    logger.info(
                        "legacy_exit_used",
                        extra={
                            "symbol": data.symbol,
                            "structure_type": structure.structure_type.value,
                            "reason": "exit_planner_returned_none",
                            "is_bullish": structure.is_bullish,
                        },
                    )
                    if structure.is_bullish:
                        stop_loss = structure.low_price - (structure.price_range * Decimal("0.1"))
                        take_profit = entry_price + (structure.price_range * Decimal("2.0"))
                    else:
                        stop_loss = structure.high_price + (structure.price_range * Decimal("0.1"))
                        take_profit = entry_price - (structure.price_range * Decimal("2.0"))

                # Safety clamp
                epsilon = max(Decimal("0.00001"), structure.price_range * Decimal("0.01"))
                if decision_type == DecisionType.BUY:
                    if stop_loss >= entry_price:
                        stop_loss = entry_price - epsilon
                    if take_profit <= entry_price:
                        take_profit = entry_price + epsilon
                    risk = entry_price - stop_loss
                    reward = take_profit - entry_price
                else:
                    if stop_loss <= entry_price:
                        stop_loss = entry_price + epsilon
                    if take_profit >= entry_price:
                        take_profit = entry_price - epsilon
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
                    position_size=Decimal("0.1"),
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
                        "post_clamp_rr": float(rr),
                        "env_mode": self._env_mode,
                        "env_account_size": self._env_account_size,
                        "sl_requested": float(sl_requested) if sl_requested else None,
                        "tp_requested": float(tp_requested) if tp_requested else None,
                        "sl_final": float(stop_loss),
                        "tp_final": float(take_profit),
                        "clamped": clamped,
                    },
                )

                decisions.append(decision)
                self._all_decisions.append(decision)

            except Exception as e:
                logger.exception("decision_generation_error", extra={"error": str(e)})

        return decisions

    def finalize_session(self, session_name: str) -> None:
        hist = {"order_block": 0, "fair_value_gap": 0, "rejection": 0, "atr": 0, "legacy": 0}
        rr_counts = {k: [0, 0] for k in list(hist.keys()) + ["overall"]}
        
        # Legacy-specific tracking
        legacy_total = 0
        legacy_passed = 0
        legacy_failed = 0
        legacy_by_structure = {}

        for d in self._all_decisions:
            method = str(d.metadata.get("exit_method", "legacy"))
            hist[method] = hist.get(method, 0) + 1
            rr = Decimal(str(d.metadata.get("post_clamp_rr", d.risk_reward_ratio)))

            if rr >= Decimal("1.5"):
                rr_counts[method][0] += 1
                rr_counts["overall"][0] += 1
                if method == "legacy":
                    legacy_passed += 1
            else:
                if method == "legacy":
                    legacy_failed += 1
            
            rr_counts[method][1] += 1
            rr_counts["overall"][1] += 1
            
            # Track legacy by structure type
            if method == "legacy":
                legacy_total += 1
                struct_type = d.metadata.get("structure_type", "unknown")
                if struct_type not in legacy_by_structure:
                    legacy_by_structure[struct_type] = {"total": 0, "passed": 0, "failed": 0}
                legacy_by_structure[struct_type]["total"] += 1
                if rr >= Decimal("1.5"):
                    legacy_by_structure[struct_type]["passed"] += 1
                else:
                    legacy_by_structure[struct_type]["failed"] += 1

        def pct(v):
            return float((Decimal(v[0]) / Decimal(v[1]) * 100) if v[1] else 0)

        logger.info(
            "dry_run_exit_summary",
            extra={
                "exit_method_hist": hist,
                "rr_gate": {
                    "overall_ge_1_5_pct": pct(rr_counts["overall"]),
                    "by_method": {k: pct(rr_counts[k]) for k in hist.keys()},
                },
                "legacy_tracking": {
                    "total_legacy_exits": legacy_total,
                    "legacy_passed_rr": legacy_passed,
                    "legacy_failed_rr": legacy_failed,
                    "legacy_pass_rate_pct": pct([legacy_passed, legacy_total]),
                    "by_structure": legacy_by_structure,
                },
            },
        )

    def get_pipeline_stats(self) -> dict:
        return {
            "processed_bars": self.processed_bars,
            "decisions_generated": self.decisions_generated,
            "execution_results": len(self.execution_results),
            "executor_mode": self.executor.mode.value,
        }


