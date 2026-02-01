"""Symbol onboarding management for per-symbol execution gates.

Minimal version for PR4:
- Loads per-symbol onboarding config from configs/symbol_onboarding.json
- Loads/saves runtime state from state/symbol_onboarding_state.json
- Exposes a small API used by the pipeline to decide whether to execute.

Probation fields are parsed and exposed in state but automatic promotion logic
will be added in a follow-up.
"""

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..models.decision import DecisionType

logger = logging.getLogger(__name__)


class SymbolOnboardingManager:
    """Manage per-symbol onboarding state and execution gates."""

    def __init__(self, config_path: Optional[str] = None, state_path: Optional[str] = None) -> None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.config_path = config_path or os.path.join(base_dir, "configs", "symbol_onboarding.json")
        state_dir = os.path.join(base_dir, "state")
        os.makedirs(state_dir, exist_ok=True)
        self.state_path = state_path or os.path.join(state_dir, "symbol_onboarding_state.json")

        self._config = self._load_json_safe(self.config_path) or {}
        self._state = self._load_json_safe(self.state_path) or {}

    @staticmethod
    def _load_json_safe(path: str) -> Dict[str, Any]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception as e:
            logger.warning("symbol_onboarding_load_failed", extra={"path": path, "error": str(e)})
        return {}

    def _save_state(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.warning("symbol_onboarding_save_failed", extra={"path": self.state_path, "error": str(e)})

    def _get_symbol_config(self, symbol: str) -> Dict[str, Any]:
        symbols_cfg = (self._config or {}).get("symbols", {}) or {}
        return deepcopy(symbols_cfg.get(symbol, {}))

    def get_state(self, symbol: str) -> Dict[str, Any]:
        """Return merged onboarding state for a symbol.

        Precedence: runtime state overrides config, which overrides defaults.
        """
        sym = symbol.upper()
        cfg = self._get_symbol_config(sym)
        state_entry = deepcopy((self._state or {}).get(sym, {}))

        # Defaults
        defaults = {
            "state": "promoted",  # observe_only | promoted
            "execute_when_promoted": True,
            "probation_min_sessions": 0,
            "probation_min_trades": 0,
            "max_validation_errors": 0,
            "min_rr_during_probation": None,
            "risk_cap_multiplier_during_probation": 1.0,
            "sessions_seen": 0,
            "trades_seen": 0,
            "validation_errors": 0,
            "last_promotion_ts": None,
        }

        # Map config -> state keys
        mapped_cfg = {
            "state": cfg.get("initial_state"),
            "execute_when_promoted": cfg.get("execute_when_promoted"),
            "probation_min_sessions": cfg.get("probation_min_sessions"),
            "probation_min_trades": cfg.get("probation_min_trades"),
            "max_validation_errors": cfg.get("max_validation_errors"),
            "min_rr_during_probation": cfg.get("min_rr_during_probation"),
            "risk_cap_multiplier_during_probation": cfg.get("risk_cap_multiplier_during_probation"),
        }

        merged = deepcopy(defaults)
        for k, v in mapped_cfg.items():
            if v is not None:
                merged[k] = v
        for k, v in state_entry.items():
            if v is not None:
                merged[k] = v

        merged["symbol"] = sym
        return merged

    def record_decisions(
        self,
        symbol: str,
        decisions: List[Any],
        session_id: Optional[str],
        validation_errors: int = 0,
    ) -> None:
        """Update counters for a symbol and persist state.

        Counters:
        - sessions_seen: number of distinct sessions where the symbol produced at least one decision
        - trades_seen: number of entry decisions (BUY/SELL) for the symbol
        - validation_errors: accumulated validation error count

        Also applies automatic promotion when thresholds are satisfied.
        """
        sym = symbol.upper()
        current = self.get_state(sym)

        # Ensure symbol entry exists in raw state for auxiliary data such as seen_sessions
        state_entry = self._state.setdefault(sym, {})

        # Track distinct sessions where at least one decision was produced
        seen_sessions = state_entry.get("seen_sessions", []) or []
        if decisions and session_id:
            if session_id not in seen_sessions:
                seen_sessions.append(session_id)
                current["sessions_seen"] = int(current.get("sessions_seen", 0)) + 1
        # Persist seen_sessions list
        state_entry["seen_sessions"] = seen_sessions

        # Count entry trades (BUY/SELL decisions)
        trade_increments = 0
        for d in decisions or []:
            dt = getattr(d, "decision_type", None)
            if dt in (DecisionType.BUY, DecisionType.SELL):
                trade_increments += 1

        current["trades_seen"] = int(current.get("trades_seen", 0)) + trade_increments
        current["validation_errors"] = int(current.get("validation_errors", 0)) + int(validation_errors or 0)

        # Write merged state back to backing store
        for key in [
            "state",
            "execute_when_promoted",
            "probation_min_sessions",
            "probation_min_trades",
            "max_validation_errors",
            "min_rr_during_probation",
            "risk_cap_multiplier_during_probation",
            "sessions_seen",
            "trades_seen",
            "validation_errors",
            "last_promotion_ts",
        ]:
            state_entry[key] = current.get(key)

        # Automatic promotion based on thresholds
        try:
            from_state = state_entry.get("state", current.get("state", "promoted"))
            to_state = from_state

            sessions_seen = int(current.get("sessions_seen", 0))
            trades_seen = int(current.get("trades_seen", 0))
            err_count = int(current.get("validation_errors", 0))

            min_sessions = int(current.get("probation_min_sessions", 0))
            min_trades = int(current.get("probation_min_trades", 0))
            max_errs = int(current.get("max_validation_errors", 0))

            eligible = (
                from_state != "promoted"
                and sessions_seen >= min_sessions
                and trades_seen >= min_trades
                and err_count <= max_errs
            )

            if eligible:
                to_state = "promoted"
                ts = datetime.now(timezone.utc).isoformat()
                state_entry["state"] = to_state
                state_entry["last_promotion_ts"] = ts

                logger.info(
                    "symbol_onboarding_promotion",
                    extra={
                        "symbol": sym,
                        "from_state": from_state,
                        "to_state": to_state,
                        "sessions_seen": sessions_seen,
                        "trades_seen": trades_seen,
                        "validation_errors": err_count,
                        "probation_min_sessions": min_sessions,
                        "probation_min_trades": min_trades,
                        "max_validation_errors": max_errs,
                        "timestamp": ts,
                    },
                )
        except Exception:
            # Promotion failures should not break pipeline execution
            pass

        self._save_state()

    def should_execute(self, symbol: str) -> bool:
        """Return True if trades for a symbol should be executed.

        Minimal rule for this PR:
        - If state != "promoted": do not execute.
        - If execute_when_promoted is False: do not execute.
        - Otherwise: execute.
        """
        st = self.get_state(symbol)
        if st.get("state") != "promoted":
            return False
        if not bool(st.get("execute_when_promoted", True)):
            return False
        return True

    def apply_probation_overrides(self, symbol: str, risk_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Return a derived risk config with probation overrides applied.

        Current behavior:
        - For non-promoted symbols, if risk_cap_multiplier_during_probation < 1.0,
          tighten per_symbol_open_risk_cap_pct by that multiplier.
        - per_trade_pct remains unchanged.
        - For promoted symbols, the base config is returned unchanged.

        A new dict is always returned; the input is never mutated.
        """
        base = deepcopy(risk_cfg or {})
        st = self.get_state(symbol)

        # If promoted, do not alter caps
        if st.get("state") == "promoted":
            return base

        # Apply cap tightening only when a multiplier < 1.0 is configured
        try:
            mult = float(st.get("risk_cap_multiplier_during_probation", 1.0))
        except Exception:
            mult = 1.0

        if mult < 1.0:
            if "per_symbol_open_risk_cap_pct" in base:
                try:
                    base_cap = float(base["per_symbol_open_risk_cap_pct"])
                    base["per_symbol_open_risk_cap_pct"] = base_cap * mult
                except Exception:
                    # If parsing fails, leave base config unchanged
                    pass

        return base
