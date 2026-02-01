from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, Tuple


class StructureExitPlanner:
    def __init__(self, cfg: Dict[str, Any], broker_meta: Dict[str, Any], guards_config: Dict[str, Any] = None):
        self.cfg = cfg.get("sltp_planning", cfg)
        self.broker = broker_meta or {}
        self.guards_config = guards_config or {}
        
        # Legacy exit fallback configuration
        legacy_cfg = self.guards_config.get('legacy_exit_fallback', {})
        self.enable_legacy_fallback = legacy_cfg.get('enabled', True)
        self.fallback_to_atr = legacy_cfg.get('fallback_to_atr', True)
        self.reject_signal_if_no_fallback = legacy_cfg.get('reject_signal_if_no_fallback', False)

    def plan(
        self,
        side: str,
        entry: Decimal,
        atr: Decimal,
        structures: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Returns dict { 'sl': Decimal, 'tp': Decimal, 'method': 'structure|atr',
                       'expected_rr': Decimal } or None if rejected by RR gate.
        """
        priority = self.cfg.get("exit_priority", ["atr"]) or ["atr"]
        for method in priority:
            if method in ("order_block", "fair_value_gap"):
                planned = self._plan_from_structure(method, side, entry, atr, structures)
                if planned:
                    return self._apply_rr_gate_and_return(planned, side, entry)
                # If this structure type is unavailable or invalid, try next priority
                continue
            if method == "rejection":
                planned = self._plan_from_rejection(side, entry, atr, structures)
                if planned:
                    return self._apply_rr_gate_and_return(planned, side, entry)
                continue
            if method == "atr":
                planned = self._plan_from_atr(side, entry, atr)
                if planned:
                    return self._apply_rr_gate_and_return(planned, side, entry)
        return None

    def _plan_from_structure(
        self,
        method: str,
        side: str,
        entry: Decimal,
        atr: Decimal,
        structures: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        nearest = (structures or {}).get(method, {}).get("nearest")
        if not nearest:
            # Do not ATR-fallback here; allow next priority to attempt first.
            return None

        sl_buf = self._compute_sl_buffer(atr)
        if sl_buf is None:
            return None

        clamped = False
        sl = None
        tp = None

        if method == "order_block":
            lower_edge = Decimal(str(nearest.get("lower_edge")))
            upper_edge = Decimal(str(nearest.get("upper_edge")))
            if side.upper() == "BUY":
                sl = lower_edge - sl_buf
                tp = self._select_opposing_target("order_block", side, structures)
                if tp is None:
                    tp = self._select_opposing_target("fair_value_gap", side, structures)
                if tp is None:
                    # Use ATR-based TP extension but keep method as 'order_block'
                    tp_ext = Decimal(str(self.cfg.get("buffers", {}).get("tp_extension_atr", 1.0))) * atr
                    tp = entry + tp_ext
            else:
                sl = upper_edge + sl_buf
                tp = self._select_opposing_target("order_block", side, structures)
                if tp is None:
                    tp = self._select_opposing_target("fair_value_gap", side, structures)
                if tp is None:
                    tp_ext = Decimal(str(self.cfg.get("buffers", {}).get("tp_extension_atr", 1.0))) * atr
                    tp = entry - tp_ext

        elif method == "fair_value_gap":
            gap_low = Decimal(str(nearest.get("gap_low")))
            gap_high = Decimal(str(nearest.get("gap_high")))
            if side.upper() == "BUY":
                sl = gap_low - sl_buf
                tp = gap_high
            else:
                sl = gap_high + sl_buf
                tp = gap_low
        else:
            return None

        # Ensure TP is on correct side of entry; if not, use ATR-based extension but keep method
        tp_ext = Decimal(str(self.cfg.get("buffers", {}).get("tp_extension_atr", 1.0))) * atr
        if side.upper() == "BUY" and tp <= entry:
            tp = entry + tp_ext
        elif side.upper() == "SELL" and tp >= entry:
            tp = entry - tp_ext

        # Store pre-clamp values
        sl_requested = sl
        tp_requested = tp

        sl, tp, clamped = self._apply_broker_clamps(entry, sl, tp, side)
        if sl is None or tp is None:
            return None

        return {
            "sl": sl,
            "tp": tp,
            "method": method,
            "buffers_used": {"sl_buf": sl_buf, "tp_ext_atr": None},
            "clamped": clamped,
            "sl_requested": sl_requested,
            "tp_requested": tp_requested,
        }

    def _plan_from_atr(self, side: str, entry: Decimal, atr: Decimal) -> Optional[Dict[str, Any]]:
        sl_buf = self._compute_sl_buffer(atr)
        if sl_buf is None:
            return None
        tp_ext = Decimal(str(self.cfg.get("buffers", {}).get("tp_extension_atr", 1.0))) * atr
        if side.upper() == "BUY":
            sl_requested = entry - sl_buf
            tp_requested = entry + tp_ext
        else:
            sl_requested = entry + sl_buf
            tp_requested = entry - tp_ext
        sl, tp, clamped = self._apply_broker_clamps(entry, sl_requested, tp_requested, side)
        if sl is None or tp is None:
            return None
        return {
            "sl": sl,
            "tp": tp,
            "method": "atr",
            "buffers_used": {"sl_buf": sl_buf, "tp_ext_atr": tp_ext},
            "clamped": clamped,
            "sl_requested": sl_requested,
            "tp_requested": tp_requested,
        }

    def _plan_from_rejection(
        self, side: str, entry: Decimal, atr: Decimal, structures: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Plan SL/TP based on rejection (UZR) structure.
        SL is placed beyond the rejection zone boundary.
        TP uses ATR-based extension.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        rejection_data = structures.get("rejection")
        if not rejection_data:
            if self.enable_legacy_fallback:
                logger.warning("exit_planner_rejection_unavailable", extra={
                    "reason": "no_rejection_data_in_structures",
                    "side": side,
                    "entry": float(entry)
                })
            return None
        
        nearest = rejection_data.get("nearest")
        if not nearest:
            if self.enable_legacy_fallback:
                logger.warning("exit_planner_rejection_unavailable", extra={
                    "reason": "no_nearest_rejection_zone",
                    "side": side,
                    "entry": float(entry)
                })
            return None
        
        # Get rejection zone boundaries
        try:
            zone_low = Decimal(str(nearest.get("zone_low")))
            zone_high = Decimal(str(nearest.get("zone_high")))
        except Exception as e:
            if self.enable_legacy_fallback:
                logger.warning("exit_planner_rejection_invalid", extra={
                    "reason": "zone_boundaries_invalid",
                    "side": side,
                    "entry": float(entry),
                    "error": str(e)
                })
            return None
        
        # Validate zone is on correct side of entry
        if side.upper() == "BUY" and entry < zone_low:
            if self.enable_legacy_fallback:
                logger.warning("exit_planner_rejection_wrong_side", extra={
                    "reason": "buy_entry_below_rejection_zone",
                    "side": side,
                    "entry": float(entry),
                    "zone_low": float(zone_low),
                    "zone_high": float(zone_high)
                })
            return None
        
        if side.upper() == "SELL" and entry > zone_high:
            if self.enable_legacy_fallback:
                logger.warning("exit_planner_rejection_wrong_side", extra={
                    "reason": "sell_entry_above_rejection_zone",
                    "side": side,
                    "entry": float(entry),
                    "zone_low": float(zone_low),
                    "zone_high": float(zone_high)
                })
            return None
        
        # Compute SL buffer
        sl_buf = self._compute_sl_buffer(atr)
        if sl_buf is None:
            return None
        
        # Compute TP extension
        tp_ext = Decimal(str(self.cfg.get("buffers", {}).get("tp_extension_atr", 1.0))) * atr
        
        # Place SL beyond rejection zone, TP using ATR extension
        if side.upper() == "BUY":
            # For BUY, rejection zone is support, SL below it
            sl_requested = zone_low - sl_buf
            tp_requested = entry + tp_ext
        else:
            # For SELL, rejection zone is resistance, SL above it
            sl_requested = zone_high + sl_buf
            tp_requested = entry - tp_ext
        
        # Apply broker clamps
        sl, tp, clamped = self._apply_broker_clamps(entry, sl_requested, tp_requested, side)
        if sl is None or tp is None:
            return None
        
        return {
            "sl": sl,
            "tp": tp,
            "method": "rejection",
            "buffers_used": {"sl_buf": sl_buf, "tp_ext_atr": tp_ext},
            "clamped": clamped,
            "sl_requested": sl_requested,
            "tp_requested": tp_requested,
        }

    def _apply_rr_gate_and_return(
        self, planned: Dict[str, Any], side: str, entry: Decimal
    ) -> Optional[Dict[str, Any]]:
        try:
            sl = Decimal(planned["sl"])
            tp = Decimal(planned["tp"])
        except Exception:
            return None
        if side.upper() == "BUY":
            risk = entry - sl
            reward = tp - entry
        else:
            risk = sl - entry
            reward = entry - tp
        if risk <= 0 or reward <= 0:
            return None
        rr = reward / risk
        min_rr = Decimal(str(self.cfg.get("min_rr_gate", 1.5)))
        if rr < min_rr:
            # Attempt to extend TP to meet min_rr if allowed, but only for structure methods
            method = planned.get("method")
            if method != "atr" and self.cfg.get("atr_fallback_enabled", True):
                needed_reward = (min_rr * risk)
                if side.upper() == "BUY":
                    new_tp = entry + needed_reward
                else:
                    new_tp = entry - needed_reward
                # Re-apply rounding and broker distance clamps
                tp_saved = planned.get("tp")
                planned["tp"] = new_tp
                sl = Decimal(planned["sl"])  # unchanged
                # Re-clamp with broker rules
                sl2, tp2, _ = self._apply_broker_clamps(entry, sl, new_tp, side)
                if sl2 is not None and tp2 is not None:
                    planned["sl"], planned["tp"] = sl2, tp2
                    # Recompute RR
                    if side.upper() == "BUY":
                        risk2 = entry - sl2
                        reward2 = tp2 - entry
                    else:
                        risk2 = sl2 - entry
                        reward2 = entry - tp2
                    if risk2 > 0 and reward2 > 0:
                        rr2 = reward2 / risk2
                        if rr2 >= min_rr:
                            planned["expected_rr"] = rr2
                            return planned
                # restore original tp if extension failed to meet constraints
                planned["tp"] = tp_saved
            elif method == "atr":
                # For ATR plans, extend TP to meet min_rr requirement
                needed_reward = (min_rr * risk)
                if side.upper() == "BUY":
                    new_tp = entry + needed_reward
                else:
                    new_tp = entry - needed_reward
                # Re-apply broker clamps
                sl2, tp2, _ = self._apply_broker_clamps(entry, sl, new_tp, side)
                if sl2 is not None and tp2 is not None:
                    planned["sl"], planned["tp"] = sl2, tp2
                    # Recompute RR
                    if side.upper() == "BUY":
                        risk2 = entry - sl2
                        reward2 = tp2 - entry
                    else:
                        risk2 = sl2 - entry
                        reward2 = entry - tp2
                    if risk2 > 0 and reward2 > 0:
                        rr2 = reward2 / risk2
                        if rr2 >= min_rr:
                            planned["expected_rr"] = rr2
                            return planned
                # If extension failed, reject the plan
                return None
            return None
        planned["expected_rr"] = rr
        return planned

    def _compute_sl_buffer(self, atr: Decimal) -> Optional[Decimal]:
        try:
            sl_mult = Decimal(str(self.cfg.get("buffers", {}).get("sl_atr_buffer", 0.15)))
            min_pips = Decimal(str(self.cfg.get("buffers", {}).get("min_buffer_pips", 1.0)))
            max_pips = Decimal(str(self.cfg.get("buffers", {}).get("max_buffer_pips", 10.0)))
            p2 = self._pip_to_price
            min_buf_price = p2(min_pips)
            max_buf_price = p2(max_pips)
            atr_buf = (sl_mult * atr)
            return max(min_buf_price, min(max_buf_price, atr_buf))
        except Exception:
            return None

    def _select_opposing_target(self, method: str, side: str, structures: Dict[str, Any]) -> Optional[Decimal]:
        opp_side = "SELL" if side.upper() == "BUY" else "BUY"
        nearest = (structures or {}).get(method, {}).get("nearest")
        if not nearest:
            return None
        if method == "order_block":
            if opp_side == "BUY":
                return Decimal(str(nearest.get("upper_edge")))
            else:
                return Decimal(str(nearest.get("lower_edge")))
        if method == "fair_value_gap":
            if opp_side == "BUY":
                return Decimal(str(nearest.get("gap_high")))
            else:
                return Decimal(str(nearest.get("gap_low")))
        return None

    def _apply_broker_clamps(self, entry: Decimal, sl: Decimal, tp: Decimal, side: str) -> Tuple[Optional[Decimal], Optional[Decimal], bool]:
        digits = int(self.broker.get("digits", 5))
        point = Decimal(str(self.broker.get("point", "0.00001")))
        min_stop = Decimal(str(self.broker.get("min_stop_distance", "0")))
        max_stop = self.broker.get("max_stop_distance")
        max_stop = Decimal(str(max_stop)) if max_stop is not None else None

        sl_r = self._round_to_point(sl, point)
        tp_r = self._round_to_point(tp, point)
        clamped = (sl_r != sl) or (tp_r != tp)
        sl = sl_r
        tp = tp_r

        def ensure_distance(p: Decimal, away_from: Decimal, minimum: Decimal, direction: int) -> Decimal:
            d = abs(p - away_from)
            if d >= minimum:
                return p
            delta = minimum - d
            return p + (delta * (Decimal(1) if direction > 0 else Decimal(-1)))

        if side.upper() == "BUY":
            sl = ensure_distance(sl, entry, min_stop, -1)
            tp = ensure_distance(tp, entry, min_stop, +1)
        else:
            sl = ensure_distance(sl, entry, min_stop, +1)
            tp = ensure_distance(tp, entry, min_stop, -1)
        sl2 = self._round_to_point(sl, point)
        tp2 = self._round_to_point(tp, point)
        clamped = clamped or (sl2 != sl) or (tp2 != tp)
        sl, tp = sl2, tp2

        if max_stop is not None:
            d_sl = abs(entry - sl)
            d_tp = abs(tp - entry)
            if d_sl > max_stop:
                if side.upper() == "BUY":
                    sl = entry - max_stop
                else:
                    sl = entry + max_stop
            if d_tp > max_stop:
                if side.upper() == "BUY":
                    tp = entry + max_stop
                else:
                    tp = entry - max_stop
            sl3 = self._round_to_point(sl, point)
            tp3 = self._round_to_point(tp, point)
            clamped = clamped or (sl3 != sl) or (tp3 != tp)
            sl, tp = sl3, tp3

            if side.upper() == "BUY" and not (sl < entry < tp):
                return None, None, clamped
            if side.upper() == "SELL" and not (tp < entry < sl):
                return None, None, clamped

        return sl, tp, clamped

    def _pip_to_price(self, pips: Decimal) -> Decimal:
        point = Decimal(str(self.broker.get("point", "0.00001")))
        digits = int(self.broker.get("digits", 5))
        mul = Decimal(10) if digits in (3, 5) else Decimal(1)
        return Decimal(str(pips)) * point * mul

    def _round_to_point(self, price: Decimal, point: Decimal) -> Decimal:
        if point == 0:
            return price
        units = (price / point).quantize(Decimal(0), rounding=ROUND_HALF_UP)
        return units * point
