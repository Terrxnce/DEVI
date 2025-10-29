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
    
    def __init__(self, success, order_id=None, error_message=None, payload=None, timestamp=None, rr=None, validation_errors=None):
        self.success = success
        self.order_id = order_id
        self.error_message = error_message
        self.payload = payload
        self.timestamp = timestamp if timestamp else datetime.now(timezone.utc)
        self.rr = rr
        self.validation_errors = validation_errors or []
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class MT5Executor:
    """Executes orders in dry-run or live mode."""
    
    def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN, config: Dict[str, Any] = None):
        self.mode = mode
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.min_rr = Decimal(str(self.config.get('min_rr', 1.5)))
        self.dry_run_orders = []
        logger.info(f"MT5Executor initialized in {mode.value} mode")
        # Broker symbol registry placeholder (populated elsewhere in pipeline)
        self._symbol_meta: Dict[str, Any] = {}
        # Open risk ledger for dry-run
        self._open_risk_by_symbol: Dict[str, float] = {}
    
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
        error = self._validate_order(symbol, order_type, volume, entry_price, stop_loss, take_profit)
        if error:
            logger.warning("order_validation_failed", extra={"error": error, "symbol": symbol})
            return ExecutionResult(success=False, error_message=error)
        
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
        
        if self.mode == ExecutionMode.DRY_RUN:
            self.dry_run_orders.append(payload)
            logger.info("order_validation_passed", extra={"symbol": symbol, "type": order_type})
            return ExecutionResult(success=True, payload=payload, order_id=len(self.dry_run_orders))
        
        # For paper/live, would call MT5 API here
        logger.info("order_validation_passed", extra={"symbol": symbol, "type": order_type})
        return ExecutionResult(success=True, payload=payload)
    
    def _validate_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> Optional[str]:
        """Validate order parameters."""
        if order_type not in ['BUY', 'SELL']:
            return f"Invalid order type: {order_type}"
        
        if volume <= 0:
            return "Volume must be positive"
        
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return "Prices must be positive"
        
        # Validate SL/TP logic
        if order_type == 'BUY':
            if stop_loss >= entry_price:
                return f"For BUY: SL ({stop_loss}) must be < entry ({entry_price})"
            if take_profit <= entry_price:
                return f"For BUY: TP ({take_profit}) must be > entry ({entry_price})"
        
        elif order_type == 'SELL':
            if stop_loss <= entry_price:
                return f"For SELL: SL ({stop_loss}) must be > entry ({entry_price})"
            if take_profit >= entry_price:
                return f"For SELL: TP ({take_profit}) must be < entry ({entry_price})"
        
        # Validate RR
        if order_type == 'BUY':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        
        if risk <= 0:
            return "Risk must be positive"
        
        rr = reward / risk
        if rr < float(self.min_rr):
            return f"RR ({rr:.2f}) must be >= {float(self.min_rr)}"
        
        return None
    
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
        """Stub: account equity for risk sizing in dry-run."""
        return float(self.config.get('equity', 10000.0))

    def get_open_risk_by_symbol(self, symbol: str) -> float:
        return float(self._open_risk_by_symbol.get(symbol, 0.0))

    def add_open_risk(self, symbol: str, amount: float) -> None:
        self._open_risk_by_symbol[symbol] = float(self._open_risk_by_symbol.get(symbol, 0.0) + float(amount))
