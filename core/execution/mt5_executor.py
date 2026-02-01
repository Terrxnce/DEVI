"""
MT5 executor for dry-run and live trading.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:  # MT5 is optional; we guard usage at runtime
    import MetaTrader5 as mt5  # type: ignore

    MT5_AVAILABLE = True
except Exception:  # pragma: no cover - MT5 not installed in most test envs
    mt5 = None
    MT5_AVAILABLE = False


class ExecutionMode(Enum):
    """Execution modes."""
    DRY_RUN = "dry-run"
    PAPER = "paper"
    LIVE = "live"


@dataclass
class ExecutionResult:
    """Result of order execution."""
    success: bool
    order_id: Optional[int] = None
    error_message: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    rr: Optional[float] = None
    validation_errors: List[str] = None
    precheck_block: bool = False  # True if blocked by pre-check (not a broker failure)
    
    def __init__(self, success, order_id=None, error_message=None, payload=None, timestamp=None, rr=None, validation_errors=None, precheck_block=False):
        self.success = success
        self.order_id = order_id
        self.error_message = error_message
        self.payload = payload
        self.timestamp = timestamp if timestamp else datetime.now(timezone.utc)
        self.rr = rr
        self.precheck_block = precheck_block
        self.validation_errors = validation_errors or []
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class MT5Executor:
    """Executes orders in dry-run or live mode."""
    
    def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN, config: Dict[str, Any] = None, guards_config: Dict[str, Any] = None):
        self.mode = mode
        self.config = config or {}
        self.guards_config = guards_config or {}
        self.enabled = self.config.get('enabled', True)
        self.min_rr = Decimal(str(self.config.get('min_rr', 1.5)))
        # Safety flag and transport-related settings for real MT5 sends in LIVE mode
        self.enable_real_mt5_orders: bool = bool(self.config.get("enable_real_mt5_orders", False))
        self.max_slippage_points: int = int(self.config.get("max_slippage_points", 5))
        self.deviation_points: int = int(self.config.get("deviation_points", 10))
        self.max_requotes: int = int(self.config.get("max_requotes", 1))
        # Additional safety buffer (in points) applied on top of spread / stop_level
        self.sl_buffer_points: int = int(self.config.get("sl_buffer_points", 3))
        self.dry_run_orders = []
        logger.info(f"MT5Executor initialized in {mode.value} mode")
        # Broker symbol registry placeholder (populated elsewhere in pipeline)
        self._symbol_meta: Dict[str, Any] = {}
        # Open risk ledger for dry-run
        self._open_risk_by_symbol: Dict[str, float] = {}
        
        # Execution guards configuration
        stop_guard = self.guards_config.get('broker_stop_level_guard', {})
        self.enable_stop_level_guard = stop_guard.get('enabled', True)
        self.spread_buffer_multiplier = float(stop_guard.get('spread_buffer_multiplier', 2.0))
        self.min_stops_level_when_zero = int(stop_guard.get('min_stops_level_when_zero', 10))
        self.use_tick_based_stop_validation = bool(stop_guard.get('use_tick_based_stop_validation', True))
        self.tick_spread_multiplier = float(stop_guard.get('tick_spread_multiplier', 3.0))
        self.tick_spread_buffer_points = float(stop_guard.get('tick_spread_buffer_points', 20.0))
        self.default_symbol_floor_points = int(stop_guard.get('default_symbol_floor_points', 50))
        self.symbol_floor_points = dict(stop_guard.get('symbol_floor_points', {}) or {})

        invalid_stops_cfg = self.guards_config.get('invalid_stops_handling', {})
        self.enable_adaptive_retry_on_10016 = bool(invalid_stops_cfg.get('enable_adaptive_retry_on_10016', True))
        self.retry_tick_spread_multiplier = float(invalid_stops_cfg.get('retry_tick_spread_multiplier', 4.0))
        self.retry_tick_spread_buffer_points = float(invalid_stops_cfg.get('retry_tick_spread_buffer_points', 30.0))
        self.retry_safety_margin_points = float(invalid_stops_cfg.get('retry_safety_margin_points', 20.0))
        self.enable_naked_entry_fallback_on_10016 = bool(invalid_stops_cfg.get('enable_naked_entry_fallback_on_10016', False))
        self.close_on_modify_failure = bool(invalid_stops_cfg.get('close_on_modify_failure', False))
        
        rescale_cfg = self.guards_config.get('sl_tp_rescaling', {})
        self.enable_rescaling = rescale_cfg.get('enabled', True)
        self.max_rescale_attempts = int(rescale_cfg.get('max_rescale_attempts', 3))
        self.rescale_widening_factors = rescale_cfg.get('exponential_widening_factors', [1.0, 1.2, 1.6, 2.4])
        self.maintain_risk_via_volume = rescale_cfg.get('maintain_risk_via_volume', True)
    
    def execute_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "",
        magic: int = 0
    ) -> ExecutionResult:
        """
        Execute an order (dry-run or live).
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            order_type: 'BUY' or 'SELL'
            volume: Position size
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            comment: Order comment
            magic: Magic number
        
        Returns:
            ExecutionResult with success status
        """
        if not self.enabled:
            return ExecutionResult(success=False, error_message="Executor disabled")
        
        # Validate order
        error, is_precheck_block = self._validate_order(symbol, order_type, volume, entry_price, stop_loss, take_profit)
        if error:
            logger.warning("order_validation_failed", extra={"error": error, "symbol": symbol, "precheck_block": is_precheck_block})
            return ExecutionResult(success=False, error_message=error, precheck_block=is_precheck_block)
        
        # Build payload
        payload = {
            "symbol": symbol,
            "type": order_type,
            "volume": volume,
            "entry": entry_price,
            "sl": stop_loss,
            "tp": take_profit,
            "comment": comment,
            "magic": magic,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Log the intent to send an order (used for both paper and live modes)
        # Enhanced logging: capture all variables for ground truth analysis
        # Uses bid/ask reference (matching broker validation) and tick-based spread
        try:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if info is not None and info.point > 0 and tick is not None:
                point = info.point
                digits = getattr(info, "digits", 5)
                stops_level = getattr(info, "stops_level", 0)
                bid = tick.bid
                ask = tick.ask
                
                # Calculate spread from live tick (more accurate than symbol_info.spread)
                spread_pts = (ask - bid) / point
                
                # Calculate distances from bid/ask reference (matching broker validation)
                if order_type == "BUY":
                    reference_price = ask
                    sl_distance_pts = (reference_price - stop_loss) / point
                    tp_distance_pts = (take_profit - reference_price) / point
                else:  # SELL
                    reference_price = bid
                    sl_distance_pts = (stop_loss - reference_price) / point
                    tp_distance_pts = (reference_price - take_profit) / point
                
                symbol_floor = int(self.symbol_floor_points.get(symbol, self.default_symbol_floor_points))
                min_required_pts = max(
                    float(symbol_floor),
                    float(spread_pts) * float(self.tick_spread_multiplier) + float(self.tick_spread_buffer_points),
                )
                
                logger.info("trade_validation_detail", extra={
                    "symbol": symbol,
                    "order_type": order_type,
                    "entry": entry_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "volume": volume,
                    "bid": bid,
                    "ask": ask,
                    "reference_price": reference_price,
                    "sl_distance_from_ref_pts": sl_distance_pts,
                    "tp_distance_from_ref_pts": tp_distance_pts,
                    "spread_pts": spread_pts,
                    "symbol_floor": symbol_floor,
                    "min_required_pts": min_required_pts,
                    "broker_stops_level": stops_level,
                    "broker_point": point,
                    "digits": digits,
                    "pre_check_enabled": self.enable_stop_level_guard,
                    "pre_check_would_pass": sl_distance_pts >= min_required_pts if self.enable_stop_level_guard else None,
                })
        except Exception as e:
            logger.warning("trade_validation_detail_failed", extra={"symbol": symbol, "error": str(e)})
        
        logger.info("order_send_attempt", extra={
            "symbol": symbol,
            "type": order_type,
            "volume": volume,
            "entry": entry_price,
            "sl": stop_loss,
            "tp": take_profit,
            "mode": self.mode.value,
        })

        if self.mode == ExecutionMode.DRY_RUN:
            self.dry_run_orders.append(payload)
            logger.info("order_validation_passed", extra={"symbol": symbol, "type": order_type})
            # In dry-run there is no broker interaction; we simulate a successful send.
            logger.info("order_send_result", extra={
                "symbol": symbol,
                "mode": self.mode.value,
                "ticket": len(self.dry_run_orders),
                "retcode": "SIMULATED",
                "retcode_description": "Dry-run mode: no MT5 order sent",
            })
            return ExecutionResult(success=True, payload=payload, order_id=len(self.dry_run_orders))

        # PAPER mode and LIVE mode with real MT5 orders disabled continue to use
        # the simulated send path so behaviour is unchanged by default.
        if self.mode in (ExecutionMode.PAPER, ExecutionMode.LIVE) and (
            not (self.mode == ExecutionMode.LIVE and self.enable_real_mt5_orders)
        ):
            logger.info("order_validation_passed", extra={"symbol": symbol, "type": order_type})
            logger.info("order_send_result", extra={
                "symbol": symbol,
                "mode": self.mode.value,
                "ticket": None,
                "retcode": "SIMULATED",
                "retcode_description": "Simulated send: MT5 order_send not invoked",
            })
            return ExecutionResult(success=True, payload=payload)

        # At this point we are in LIVE mode with enable_real_mt5_orders=True.
        return self._send_order_mt5(payload)
    
    def validate_broker_stops_before_order(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        order_type: str,
    ) -> tuple[bool, Optional[str]]:
        if not self.enable_stop_level_guard:
            return True, None

        if self.mode != ExecutionMode.LIVE or not MT5_AVAILABLE or mt5 is None:
            return True, None

        try:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if info is None or info.point <= 0:
                logger.warning("broker_stop_check_failed", extra={
                    "symbol": symbol,
                    "reason": "symbol_info_unavailable",
                })
                return True, None

            point = float(info.point)
            digits = int(getattr(info, "digits", 5))

            if self.use_tick_based_stop_validation:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    logger.warning("broker_stop_check_failed", extra={
                        "symbol": symbol,
                        "reason": "tick_unavailable",
                    })
                    return True, None

                bid = float(tick.bid)
                ask = float(tick.ask)
                spread_pts = (ask - bid) / point

                symbol_floor = int(self.symbol_floor_points.get(
                    symbol,
                    self.default_symbol_floor_points,
                ))

                min_required_pts = max(
                    float(symbol_floor),
                    float(spread_pts) * float(self.tick_spread_multiplier) + float(self.tick_spread_buffer_points),
                )

                if order_type == "BUY":
                    reference_price = ask
                    sl_distance_pts = (reference_price - stop_loss) / point
                    tp_distance_pts = (take_profit - reference_price) / point
                else:
                    reference_price = bid
                    sl_distance_pts = (stop_loss - reference_price) / point
                    tp_distance_pts = (reference_price - take_profit) / point

            else:
                spread = float(getattr(info, "spread", 0.0))
                symbol_floor = int(self.symbol_floor_points.get(symbol, self.default_symbol_floor_points))
                min_required_pts = max(float(symbol_floor), float(spread) + 20.0)
                reference_price = float(entry_price)
                sl_distance_pts = abs(entry_price - stop_loss) / point
                tp_distance_pts = abs(take_profit - entry_price) / point
                bid = None
                ask = None
                spread_pts = None

            sl_normalized = round(float(stop_loss), digits)
            tp_normalized = round(float(take_profit), digits)

            if sl_distance_pts < min_required_pts:
                logger.warning("sl_too_close_for_broker", extra={
                    "symbol": symbol,
                    "order_type": order_type,
                    "reference_price": reference_price,
                    "bid": bid,
                    "ask": ask,
                    "spread_pts": spread_pts,
                    "symbol_floor": symbol_floor,
                    "min_required_pts": min_required_pts,
                    "sl": float(stop_loss),
                    "sl_normalized": sl_normalized,
                    "tp": float(take_profit),
                    "actual_sl_distance_pts": sl_distance_pts,
                    "shortfall_pts": min_required_pts - sl_distance_pts,
                })
                return False, f"SL too close to {order_type} reference: {sl_distance_pts:.1f} pts < {min_required_pts:.0f} pts required"

            if tp_distance_pts < min_required_pts:
                logger.warning("tp_too_close_for_broker", extra={
                    "symbol": symbol,
                    "order_type": order_type,
                    "reference_price": reference_price,
                    "bid": bid,
                    "ask": ask,
                    "spread_pts": spread_pts,
                    "symbol_floor": symbol_floor,
                    "min_required_pts": min_required_pts,
                    "sl": float(stop_loss),
                    "tp": float(take_profit),
                    "tp_normalized": tp_normalized,
                    "actual_tp_distance_pts": tp_distance_pts,
                    "shortfall_pts": min_required_pts - tp_distance_pts,
                })
                return False, f"TP too close to {order_type} reference: {tp_distance_pts:.1f} pts < {min_required_pts:.0f} pts required"

            return True, None

        except Exception as e:
            logger.warning("broker_stop_check_error", extra={
                "symbol": symbol,
                "error": str(e),
            })
            return True, None
    
    def _validate_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> tuple[Optional[str], bool]:
        """
        Validate order parameters.
        
        Returns:
            (error_message, is_precheck_block) - error_message is None if valid
        """
        if order_type not in ['BUY', 'SELL']:
            return f"Invalid order type: {order_type}", False
        
        if volume <= 0:
            return "Volume must be positive", False
        
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return "Prices must be positive", False
        
        # Validate SL/TP logic
        if order_type == 'BUY':
            if stop_loss >= entry_price:
                return f"For BUY: SL ({stop_loss}) must be < entry ({entry_price})", False
            if take_profit <= entry_price:
                return f"For BUY: TP ({take_profit}) must be > entry ({entry_price})", False
        
        elif order_type == 'SELL':
            if stop_loss <= entry_price:
                return f"For SELL: SL ({stop_loss}) must be > entry ({entry_price})", False
            if take_profit >= entry_price:
                return f"For SELL: TP ({take_profit}) must be < entry ({entry_price})", False
        
        # Validate RR
        if order_type == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        
        if risk <= 0:
            return "Risk must be positive", False
        
        rr = reward / risk
        # Use <= with small epsilon to handle floating-point precision
        if rr < float(self.min_rr) - 1e-9:
            return f"RR ({rr:.2f}) must be >= {float(self.min_rr)}", False
        
        # NEW: Broker stop-level pre-check
        is_valid, broker_error = self.validate_broker_stops_before_order(
            symbol, entry_price, stop_loss, take_profit, order_type
        )
        if not is_valid:
            return broker_error, True  # This is a pre-check block
        
        return None, False
    
    def get_dry_run_stats(self) -> Dict[str, Any]:
        """Get dry-run statistics."""
        return {
            "total_orders": len(self.dry_run_orders),
            "passed": len(self.dry_run_orders),
            "failed": 0
        }
    
    def log_dry_run_summary(self) -> None:
        """Log dry-run summary."""
        stats = self.get_dry_run_stats()
        logger.info("dry_run_summary", extra=stats)

    # --- Session wiring support methods ---

    def is_market_open(self) -> bool:
        """Stub: return True in dry-run; real impl would query MT5 market status."""
        return True

    def is_symbol_tradable(self, symbol: str) -> bool:
        """Stub: return True if symbol appears valid; real impl would query MT5 symbol select/info."""
        return bool(symbol) and isinstance(symbol, str)

    def close_positions(self, symbols: Optional[List[str]] = None) -> None:
        """Stub: close positions for provided symbols. In dry-run, just log."""
        symbols = symbols or []
        logger.info("positions_closed", extra={"symbols": symbols, "mode": self.mode.value})
        # Clear open risk for specified symbols (or all if empty)
        if symbols:
            for s in symbols:
                self._open_risk_by_symbol[s] = 0.0
        else:
            self._open_risk_by_symbol = {}

    def get_spread(self, symbol: str) -> float:
        """Stub: current spread. In dry-run returns a small positive value (in price units)."""
        return 0.00010

    def get_baseline_spread(self, symbol: str) -> float:
        """Stub: baseline spread estimate for symbol (in price units)."""
        return 0.00010

    # --- Risk sizing helpers ---

    def get_equity(self) -> float:
        """Get account equity from MT5 in LIVE mode, or config default otherwise."""
        if self.mode == ExecutionMode.LIVE and MT5_AVAILABLE and mt5 is not None:
            try:
                account_info = mt5.account_info()
                if account_info is not None:
                    return float(account_info.equity)
            except Exception:
                pass
        # Fallback to config for DRY_RUN, PAPER, or if MT5 read fails
        return float(self.config.get('equity', 10000.0))

    def _send_order_mt5(self, payload: Dict[str, Any]) -> ExecutionResult:
        """Send a real order to MT5 in LIVE mode, with safety guards and logging.

        This path is only used when mode == ExecutionMode.LIVE and
        enable_real_mt5_orders == True. PAPER and DRY_RUN never reach here.
        """
        if not MT5_AVAILABLE or mt5 is None:
            error_msg = "MetaTrader5 package not available; cannot send real orders"
            logger.error("order_send_error", extra={
                "symbol": payload.get("symbol"),
                "mode": self.mode.value,
                "error": error_msg,
            })
            return ExecutionResult(success=False, error_message=error_msg, payload=payload)

        symbol = payload["symbol"]
        order_type = payload["type"]
        volume = float(payload["volume"])
        entry = float(payload["entry"])
        sl = float(payload["sl"])
        tp = float(payload["tp"])
        comment = str(payload.get("comment", ""))
        magic = int(payload.get("magic", 0))

        # Enforce a dynamic minimum distance for SL/TP based on spread and a safety buffer.
        # This helps avoid MT5 10016 (Invalid stops) while keeping risk and RR consistent.
        try:
            # Ensure symbol is selected in Market Watch to get live quotes
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        except Exception:
            info = None

        adjusted = False
        orig_sl = sl
        orig_tp = tp
        orig_volume = volume

        if info is not None and info.point > 0:
            point = info.point
            bid = getattr(info, "bid", 0.0)
            ask = getattr(info, "ask", 0.0)
            if bid and ask:
                spread_points = int(abs(ask - bid) / point)
            else:
                spread_points = 0

            stop_level = getattr(info, "stop_level", 0)
            
            # Get per-symbol hard floor from broker metadata
            symbol_meta = self._symbol_meta.get(symbol, {})
            hard_floor_points = int(symbol_meta.get("sl_hard_floor_points", 0))
            
            # Compute minimum required distance as max of:
            # 1. Broker's static stop_level
            # 2. Dynamic spread + buffer
            # 3. Hard floor (absolute minimum we will ever allow)
            min_sl_pts = max(
                int(stop_level),
                spread_points + self.sl_buffer_points,
                hard_floor_points
            )

            # Current distances in points
            sl_dist_pts = int(abs(entry - sl) / point) if sl != 0 else 0
            tp_dist_pts = int(abs(tp - entry) / point) if tp != 0 else 0

            # Determine if we need to push SL/TP outward
            need_adjust_sl = sl_dist_pts < min_sl_pts
            need_adjust_tp = tp_dist_pts < min_sl_pts

            if need_adjust_sl or need_adjust_tp:
                adjusted = True

                # Compute new SL/TP at minimum distance
                min_offset_price = min_sl_pts * point
                if order_type == "BUY":
                    if need_adjust_sl:
                        sl = entry - min_offset_price
                    if need_adjust_tp:
                        tp = entry + min_offset_price
                else:  # SELL
                    if need_adjust_sl:
                        sl = entry + min_offset_price
                    if need_adjust_tp:
                        tp = entry - min_offset_price

                # Rescale volume to keep monetary risk approximately constant:
                # risk ∝ volume * |entry - SL|, so adjust volume by old_dist / new_dist.
                old_sl_dist_price = abs(entry - orig_sl)
                new_sl_dist_price = abs(entry - sl)
                if new_sl_dist_price <= 0:
                    logger.info("sl_tp_min_distance_violation", extra={
                        "symbol": symbol,
                        "min_required_points": min_sl_pts,
                        "spread_points": spread_points,
                        "orig_sl": orig_sl,
                        "orig_tp": orig_tp,
                        "orig_volume": orig_volume,
                        "reason": "non_positive_new_sl_distance",
                    })
                    return ExecutionResult(success=False, error_message="SL/TP adjustment produced invalid distance", payload=payload)

                if old_sl_dist_price > 0:
                    volume = volume * (old_sl_dist_price / new_sl_dist_price)

                # Recompute RR with adjusted SL/TP
                if order_type == "BUY":
                    risk_price = entry - sl
                    reward_price = tp - entry
                else:
                    risk_price = sl - entry
                    reward_price = entry - tp

                if risk_price <= 0 or reward_price <= 0:
                    logger.info("sl_tp_min_distance_violation", extra={
                        "symbol": symbol,
                        "min_required_points": min_sl_pts,
                        "spread_points": spread_points,
                        "orig_sl": orig_sl,
                        "orig_tp": orig_tp,
                        "orig_volume": orig_volume,
                        "adj_sl": sl,
                        "adj_tp": tp,
                        "adj_volume": volume,
                        "reason": "non_positive_risk_or_reward",
                    })
                    return ExecutionResult(success=False, error_message="RR invalid after SL/TP adjustment", payload=payload)

                rr = reward_price / risk_price
                if rr < float(self.min_rr):
                    logger.info("sl_tp_min_distance_violation", extra={
                        "symbol": symbol,
                        "min_required_points": min_sl_pts,
                        "spread_points": spread_points,
                        "orig_sl": orig_sl,
                        "orig_tp": orig_tp,
                        "orig_volume": orig_volume,
                        "adj_sl": sl,
                        "adj_tp": tp,
                        "adj_volume": volume,
                        "rr_after_adjustment": rr,
                    })
                    return ExecutionResult(success=False, error_message="RR below minimum after SL/TP adjustment", payload=payload)

                logger.info("sl_adjusted_for_min_distance", extra={
                    "symbol": symbol,
                    "min_required_points": min_sl_pts,
                    "spread_points": spread_points,
                    "hard_floor_points": hard_floor_points,
                    "stop_level": stop_level,
                    "orig_sl": orig_sl,
                    "orig_tp": orig_tp,
                    "orig_volume": orig_volume,
                    "adj_sl": sl,
                    "adj_tp": tp,
                    "adj_volume": volume,
                })

            # Always normalize volume to broker constraints, regardless of SL/TP adjustment.
            # This ensures we never send invalid volumes to MT5.
            vol_min = getattr(info, "volume_min", 0.01)
            vol_step = getattr(info, "volume_step", 0.01)

            # Snap down to nearest valid step
            snapped_volume = (int(volume / vol_step)) * vol_step if vol_step > 0 else volume

            if snapped_volume < vol_min:
                logger.info("sl_tp_min_distance_violation", extra={
                    "symbol": symbol,
                    "orig_volume": orig_volume,
                    "raw_volume_before_snap": volume,
                    "snapped_volume": snapped_volume,
                    "vol_min": vol_min,
                    "vol_step": vol_step,
                    "reason": "volume_below_min_lot_after_adjustment",
                })
                return ExecutionResult(success=False, error_message="Volume below broker minimum after SL/TP adjustment", payload=payload)

            # Use snapped volume for the order
            volume = snapped_volume

        # Map logical order type to MT5 constants
        if order_type == "BUY":
            mt5_type = mt5.ORDER_TYPE_BUY
        else:
            mt5_type = mt5.ORDER_TYPE_SELL

        # Normalize SL/TP to symbol digits to avoid rounding-related rejections
        digits = getattr(info, "digits", 5) if info is not None else 5
        sl = round(sl, digits)
        tp = round(tp, digits)
        entry = round(entry, digits)

        request: Dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": entry,
            "sl": sl,
            "tp": tp,
            "deviation": self.deviation_points,
            "magic": magic,
            "comment": comment,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        attempt = 0
        last_result = None
        max_attempts = max(1, self.max_requotes + 1)

        while attempt < max_attempts:
            attempt += 1
            result = mt5.order_send(request)
            last_result = result

            # MT5 result object exposes retcode and associated fields
            retcode = getattr(result, "retcode", None)
            ticket = getattr(result, "order", None) or getattr(result, "deal", None)
            # Best-effort description; mt5 provides a mapping helper in recent versions
            retcode_desc = getattr(result, "comment", "")

            success = retcode == mt5.TRADE_RETCODE_DONE

            # Enhanced logging: include broker response for ground truth comparison
            logger.info("order_send_result", extra={
                "symbol": symbol,
                "mode": self.mode.value,
                "ticket": ticket,
                "retcode": retcode,
                "retcode_description": retcode_desc,
                "volume": volume,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "success": success,
            })

            if success:
                return ExecutionResult(success=True, order_id=ticket, payload=payload)

            # Retry on requote if allowed
            if retcode == mt5.TRADE_RETCODE_REQUOTE and attempt < max_attempts:
                continue
            
            # Retry on invalid stops (10016) if allowed
            # CRITICAL: Use fresh tick and validate against bid/ask (not entry)
            if (
                retcode == 10016
                and attempt < max_attempts
                and self.enable_adaptive_retry_on_10016
            ):  # TRADE_RETCODE_INVALID_STOPS
                logger.warning("order_send_invalid_stops_retry", extra={
                    "symbol": symbol,
                    "attempt": attempt,
                    "reason": "refetching tick and adjusting stops relative to bid/ask",
                })
                try:
                    mt5.symbol_select(symbol, True)
                    info = mt5.symbol_info(symbol)
                    # CRITICAL: Get fresh tick for current bid/ask
                    tick = mt5.symbol_info_tick(symbol)
                    
                    if info is not None and info.point > 0 and tick is not None:
                        point = info.point
                        digits = getattr(info, "digits", 5)
                        bid = tick.bid
                        ask = tick.ask
                        
                        # Calculate spread from fresh tick
                        spread_pts = (ask - bid) / point
                        
                        symbol_floor = int(self.symbol_floor_points.get(symbol, self.default_symbol_floor_points))
                        
                        # Calculate minimum required distance with extra safety margin for retry
                        min_required_pts = max(
                            float(symbol_floor),
                            float(spread_pts) * float(self.retry_tick_spread_multiplier)
                            + float(self.retry_tick_spread_buffer_points),
                        )

                        min_required_pts = float(min_required_pts) + float(self.retry_safety_margin_points)
                        
                        min_offset_price = min_required_pts * point
                        original_sl = request["sl"]
                        
                        # CRITICAL: Adjust SL/TP relative to bid/ask, not entry
                        if order_type == "BUY":
                            # BUY: SL below ask, TP above ask
                            new_sl = round(ask - min_offset_price, digits)
                            new_tp = round(ask + min_offset_price, digits)
                        else:  # SELL
                            # SELL: SL above bid, TP below bid
                            new_sl = round(bid + min_offset_price, digits)
                            new_tp = round(bid - min_offset_price, digits)
                        
                        request["sl"] = new_sl
                        request["tp"] = new_tp

                        if order_type == "BUY":
                            reference_price = ask
                            sl_distance_from_ref_pts = (reference_price - float(new_sl)) / point
                            tp_distance_from_ref_pts = (float(new_tp) - reference_price) / point
                        else:
                            reference_price = bid
                            sl_distance_from_ref_pts = (float(new_sl) - reference_price) / point
                            tp_distance_from_ref_pts = (reference_price - float(new_tp)) / point
                        
                        # Rescale volume to maintain original risk
                        original_sl_distance = abs(float(original_sl) - float(entry))
                        new_sl_distance = abs(float(new_sl) - float(entry))
                        if new_sl_distance > 0 and original_sl_distance > 0:
                            scale_factor = original_sl_distance / new_sl_distance
                            new_volume = float(volume) * scale_factor
                            
                            # Snap to broker constraints
                            min_lot = getattr(info, "volume_min", 0.01)
                            max_lot = getattr(info, "volume_max", 100.0)
                            lot_step = getattr(info, "volume_step", 0.01)
                            new_volume = max(min_lot, min(new_volume, max_lot))
                            new_volume = round(new_volume / lot_step) * lot_step
                            request["volume"] = new_volume
                            
                            logger.info("order_send_volume_rescaled", extra={
                                "symbol": symbol,
                                "original_volume": volume,
                                "new_volume": new_volume,
                                "scale_factor": scale_factor,
                                "original_sl_distance_pts": original_sl_distance / point,
                                "new_sl_distance_pts": new_sl_distance / point,
                            })
                        
                        logger.info("order_send_stops_adjusted", extra={
                            "symbol": symbol,
                            "bid": bid,
                            "ask": ask,
                            "spread_pts": spread_pts,
                            "min_required_pts": min_required_pts,
                            "reference_price": reference_price,
                            "sl_distance_from_ref_pts": sl_distance_from_ref_pts,
                            "tp_distance_from_ref_pts": tp_distance_from_ref_pts,
                            "new_sl": new_sl,
                            "new_tp": new_tp,
                            "new_volume": request["volume"],
                        })
                        continue
                except Exception as e:
                    logger.warning("order_send_stop_adjustment_failed", extra={
                        "symbol": symbol,
                        "error": str(e),
                    })

            break

        # Last-resort fallback: if broker rejects stops (10016), place the market order without SL/TP
        # then immediately attach SL/TP via TRADE_ACTION_SLTP.
        try:
            if (
                last_result is not None
                and getattr(last_result, "retcode", None) == 10016
                and info is not None
                and info.point > 0
                and self.enable_naked_entry_fallback_on_10016
            ):
                naked_request = dict(request)
                naked_request["sl"] = 0.0
                naked_request["tp"] = 0.0

                logger.warning(
                    "order_send_invalid_stops_fallback_naked_entry",
                    extra={
                        "symbol": symbol,
                        "volume": naked_request.get("volume"),
                        "entry": naked_request.get("price"),
                        "sl_intended": request.get("sl"),
                        "tp_intended": request.get("tp"),
                    },
                )

                naked_result = mt5.order_send(naked_request)
                naked_retcode = getattr(naked_result, "retcode", None)
                naked_ticket = getattr(naked_result, "order", None) or getattr(naked_result, "deal", None)
                naked_desc = getattr(naked_result, "comment", "")

                try:
                    fallback_tick = mt5.symbol_info_tick(symbol)
                    if fallback_tick is not None and info is not None and info.point > 0:
                        fb_bid = float(fallback_tick.bid)
                        fb_ask = float(fallback_tick.ask)
                        fb_point = float(info.point)
                        fb_spread_pts = (fb_ask - fb_bid) / fb_point
                        if order_type == "BUY":
                            fb_ref = fb_ask
                            fb_sl_dist = (fb_ref - float(request.get("sl", 0.0))) / fb_point
                            fb_tp_dist = (float(request.get("tp", 0.0)) - fb_ref) / fb_point
                        else:
                            fb_ref = fb_bid
                            fb_sl_dist = (float(request.get("sl", 0.0)) - fb_ref) / fb_point
                            fb_tp_dist = (fb_ref - float(request.get("tp", 0.0))) / fb_point
                    else:
                        fb_bid = None
                        fb_ask = None
                        fb_ref = None
                        fb_spread_pts = None
                        fb_sl_dist = None
                        fb_tp_dist = None
                except Exception:
                    fb_bid = None
                    fb_ask = None
                    fb_ref = None
                    fb_spread_pts = None
                    fb_sl_dist = None
                    fb_tp_dist = None

                logger.info(
                    "order_send_fallback_naked_result",
                    extra={
                        "symbol": symbol,
                        "ticket": naked_ticket,
                        "retcode": naked_retcode,
                        "retcode_description": naked_desc,
                        "volume": naked_request.get("volume"),
                        "entry": naked_request.get("price"),
                        "bid": fb_bid,
                        "ask": fb_ask,
                        "reference_price": fb_ref,
                        "spread_pts": fb_spread_pts,
                        "sl_distance_from_ref_pts": fb_sl_dist,
                        "tp_distance_from_ref_pts": fb_tp_dist,
                    },
                )

                if naked_retcode == mt5.TRADE_RETCODE_DONE:
                    opened_position_ticket = None
                    opened_position = None
                    try:
                        positions = mt5.positions_get(symbol=symbol)
                        if positions:
                            desired_type = mt5.POSITION_TYPE_BUY if order_type == "BUY" else mt5.POSITION_TYPE_SELL
                            desired_magic = int(magic)
                            desired_volume = float(naked_request.get("volume", 0.0))

                            best = None
                            best_score = -1
                            for p in positions:
                                score = 0
                                if getattr(p, "type", None) == desired_type:
                                    score += 2
                                if int(getattr(p, "magic", -1)) == desired_magic:
                                    score += 2
                                if abs(float(getattr(p, "volume", 0.0)) - desired_volume) < 1e-6:
                                    score += 1
                                if score > best_score:
                                    best_score = score
                                    best = p

                            if best is None:
                                best = positions[-1]

                            opened_position_ticket = int(getattr(best, "ticket", 0)) or None
                            opened_position = best
                    except Exception as e:
                        logger.warning(
                            "order_send_fallback_position_lookup_failed",
                            extra={"symbol": symbol, "error": str(e)},
                        )

                    if opened_position_ticket is not None:
                        modify_request: Dict[str, Any] = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "symbol": symbol,
                            "position": opened_position_ticket,
                            "sl": request.get("sl", 0.0),
                            "tp": request.get("tp", 0.0),
                        }

                        modify_result = mt5.order_send(modify_request)
                        modify_retcode = getattr(modify_result, "retcode", None)
                        modify_desc = getattr(modify_result, "comment", "")

                        logger.info(
                            "order_send_fallback_sltp_modify_result",
                            extra={
                                "symbol": symbol,
                                "position": opened_position_ticket,
                                "retcode": modify_retcode,
                                "retcode_description": modify_desc,
                                "sl": modify_request.get("sl"),
                                "tp": modify_request.get("tp"),
                            },
                        )

                        if modify_retcode == mt5.TRADE_RETCODE_DONE:
                            return ExecutionResult(success=True, order_id=opened_position_ticket, payload=payload)

                        # Strict handling: loud error and optional auto-close
                        logger.error(
                            "order_send_fallback_sltp_modify_failed",
                            extra={
                                "symbol": symbol,
                                "position": opened_position_ticket,
                                "retcode": modify_retcode,
                                "retcode_description": modify_desc,
                                "close_on_modify_failure": self.close_on_modify_failure,
                            },
                        )

                        if self.close_on_modify_failure and opened_position is not None:
                            try:
                                close_tick = mt5.symbol_info_tick(symbol)
                                if close_tick is not None:
                                    if getattr(opened_position, "type", None) == mt5.POSITION_TYPE_BUY:
                                        close_type = mt5.ORDER_TYPE_SELL
                                        close_price = float(close_tick.bid)
                                    else:
                                        close_type = mt5.ORDER_TYPE_BUY
                                        close_price = float(close_tick.ask)

                                    close_request: Dict[str, Any] = {
                                        "action": mt5.TRADE_ACTION_DEAL,
                                        "symbol": symbol,
                                        "position": int(getattr(opened_position, "ticket", 0)),
                                        "type": close_type,
                                        "volume": float(getattr(opened_position, "volume", 0.0)),
                                        "price": close_price,
                                        "deviation": self.deviation_points,
                                        "magic": int(magic),
                                        "comment": "auto_close_modify_failed",
                                        "type_filling": mt5.ORDER_FILLING_FOK,
                                    }
                                    close_result = mt5.order_send(close_request)
                                    logger.error(
                                        "order_send_fallback_auto_close_result",
                                        extra={
                                            "symbol": symbol,
                                            "position": int(getattr(opened_position, "ticket", 0)),
                                            "retcode": getattr(close_result, "retcode", None),
                                            "retcode_description": getattr(close_result, "comment", ""),
                                        },
                                    )
                            except Exception as e:
                                logger.error(
                                    "order_send_fallback_auto_close_failed",
                                    extra={"symbol": symbol, "position": opened_position_ticket, "error": str(e)},
                                )

                    # If we couldn't find the position or modify failed, still return success for the entry
                    # (the position exists, but might be temporarily unprotected).
                    return ExecutionResult(
                        success=True,
                        order_id=int(naked_ticket) if naked_ticket is not None else None,
                        payload=payload,
                    )
        except Exception as e:
            logger.warning(
                "order_send_invalid_stops_fallback_failed",
                extra={"symbol": symbol, "error": str(e)},
            )

        # If we reach here, all attempts failed
        error_message = f"MT5 order_send failed after {attempt} attempt(s)"
        if last_result is not None:
            error_message += f" (retcode={getattr(last_result, 'retcode', None)}, comment={getattr(last_result, 'comment', '')})"

        logger.error("order_send_error", extra={
            "symbol": symbol,
            "mode": self.mode.value,
            "error": error_message,
        })

        return ExecutionResult(success=False, error_message=error_message, payload=payload)
