"""
Session Filter - Classifies trades by trading session and symbol relevance.

Phase 1: Logging only (no blocking)
- Classifies current UTC time into session buckets
- Determines session relevance per symbol (ideal/acceptable/avoid)
- Logs evaluation for every trade attempt
- Writes session context to trade journal entries

Future phases will add:
- Phase 2: Performance analysis by symbol x session
- Phase 3: Data-driven enforcement (blocking/threshold bumps)
"""

import logging
import json
import os
from datetime import datetime, timezone, time
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SessionFilter:
    """
    Classifies trades by trading session and determines symbol relevance.
    
    Session definitions (UTC, no DST adjustment):
    - Asia: 00:00 - 08:00
    - London: 07:00 - 16:00
    - New York: 13:00 - 21:00
    - London_NY (overlap): 13:00 - 16:00
    
    Usage:
        filter = SessionFilter()
        session_name, relevance, details = filter.evaluate(symbol="EURUSD", utc_time=datetime.now(timezone.utc))
    """
    
    # Default session times (UTC)
    DEFAULT_SESSION_TIMES = {
        "Asia": {"start": time(0, 0), "end": time(8, 0)},
        "London": {"start": time(7, 0), "end": time(16, 0)},
        "NY": {"start": time(13, 0), "end": time(21, 0)},
        "London_NY": {"start": time(13, 0), "end": time(16, 0)},  # Overlap
    }
    
    # Default symbol rules
    DEFAULT_SYMBOL_RULES = {
        "EURUSD": {"ideal": ["London", "NY", "London_NY"], "acceptable": ["Asia"], "avoid": []},
        "GBPUSD": {"ideal": ["London", "NY", "London_NY"], "acceptable": [], "avoid": ["Asia"]},
        "USDJPY": {"ideal": ["Asia", "NY", "London_NY"], "acceptable": ["London"], "avoid": []},
        "AUDUSD": {"ideal": ["Asia", "London"], "acceptable": ["NY"], "avoid": []},
        "NZDUSD": {"ideal": ["Asia", "London"], "acceptable": ["NY"], "avoid": []},
        "AUDJPY": {"ideal": ["Asia"], "acceptable": ["London"], "avoid": ["NY"]},
        "XAUUSD": {"ideal": ["London", "NY", "London_NY"], "acceptable": [], "avoid": ["Asia"]},
    }
    
    def __init__(self, config_path: str = None):
        """
        Initialize session filter.
        
        Args:
            config_path: Optional path to session_filter.json config file.
                        If not provided, uses defaults.
        """
        self.enabled = True
        self.mode = "log_only"  # log_only, enforce
        self.session_times = dict(self.DEFAULT_SESSION_TIMES)
        self.symbol_rules = dict(self.DEFAULT_SYMBOL_RULES)
        
        # Load config if provided
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)
        else:
            # Try default location
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            default_path = os.path.join(base_dir, "configs", "session_filter.json")
            if os.path.exists(default_path):
                self._load_config(default_path)
        
        logger.info("session_filter_initialized", extra={
            "enabled": self.enabled,
            "mode": self.mode,
            "symbols_configured": list(self.symbol_rules.keys())
        })
    
    def _load_config(self, config_path: str) -> None:
        """Load configuration from JSON file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            self.enabled = config.get("enabled", True)
            self.mode = config.get("mode", "log_only")
            
            # Load session times if provided
            if "session_times" in config:
                for session_name, times in config["session_times"].items():
                    start_parts = times.get("start", "00:00").split(":")
                    end_parts = times.get("end", "00:00").split(":")
                    self.session_times[session_name] = {
                        "start": time(int(start_parts[0]), int(start_parts[1])),
                        "end": time(int(end_parts[0]), int(end_parts[1]))
                    }
            
            # Load symbol rules if provided
            if "symbol_rules" in config:
                self.symbol_rules.update(config["symbol_rules"])
            
            logger.debug("session_filter_config_loaded", extra={"path": config_path})
            
        except Exception as e:
            logger.warning("session_filter_config_load_failed", extra={
                "path": config_path,
                "error": str(e)
            })
    
    def get_current_session(self, utc_time: datetime = None) -> str:
        """
        Determine which trading session is currently active.
        
        Priority: London_NY overlap > London > NY > Asia
        
        Args:
            utc_time: UTC datetime. If None, uses current time.
            
        Returns:
            Session name: "Asia", "London", "NY", "London_NY", or "Off_Hours"
        """
        if utc_time is None:
            utc_time = datetime.now(timezone.utc)
        
        current_time = utc_time.time()
        
        # Check overlap first (highest priority)
        if self._time_in_range(current_time, 
                               self.session_times["London_NY"]["start"],
                               self.session_times["London_NY"]["end"]):
            return "London_NY"
        
        # Check London
        if self._time_in_range(current_time,
                               self.session_times["London"]["start"],
                               self.session_times["London"]["end"]):
            return "London"
        
        # Check NY
        if self._time_in_range(current_time,
                               self.session_times["NY"]["start"],
                               self.session_times["NY"]["end"]):
            return "NY"
        
        # Check Asia
        if self._time_in_range(current_time,
                               self.session_times["Asia"]["start"],
                               self.session_times["Asia"]["end"]):
            return "Asia"
        
        return "Off_Hours"
    
    def _time_in_range(self, check_time: time, start: time, end: time) -> bool:
        """Check if a time falls within a range (handles midnight crossing)."""
        if start <= end:
            return start <= check_time < end
        else:
            # Range crosses midnight
            return check_time >= start or check_time < end
    
    def get_session_relevance(self, symbol: str, session_name: str) -> str:
        """
        Determine how relevant a session is for a given symbol.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            session_name: Current session name
            
        Returns:
            "ideal", "acceptable", "avoid", or "unknown"
        """
        rules = self.symbol_rules.get(symbol.upper())
        
        if rules is None:
            return "unknown"
        
        if session_name in rules.get("ideal", []):
            return "ideal"
        elif session_name in rules.get("acceptable", []):
            return "acceptable"
        elif session_name in rules.get("avoid", []):
            return "avoid"
        else:
            return "unknown"
    
    def evaluate(
        self,
        symbol: str,
        direction: str = None,
        structure_type: str = None,
        confidence: float = None,
        utc_time: datetime = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Evaluate a trade attempt and return session classification.
        
        Args:
            symbol: Trading symbol
            direction: BUY or SELL (optional, for logging)
            structure_type: Structure type (optional, for logging)
            confidence: Confidence score (optional, for logging)
            utc_time: UTC datetime. If None, uses current time.
            
        Returns:
            Tuple of (session_name, session_relevance, details_dict)
        """
        if utc_time is None:
            utc_time = datetime.now(timezone.utc)
        
        session_name = self.get_current_session(utc_time)
        relevance = self.get_session_relevance(symbol, session_name)
        
        # Determine if this would be blocked in enforce mode
        would_block = relevance == "avoid" and self.mode == "enforce"
        
        details = {
            "symbol": symbol,
            "direction": direction,
            "structure_type": structure_type,
            "confidence": confidence,
            "utc_time": utc_time.isoformat(),
            "session_name": session_name,
            "session_relevance": relevance,
            "would_block_if_enabled": relevance == "avoid",
            "mode": self.mode,
            "enabled": self.enabled
        }
        
        # Log the evaluation
        if self.enabled:
            logger.info("session_filter_evaluated", extra=details)
        
        return session_name, relevance, details
    
    def should_block(self, symbol: str, utc_time: datetime = None) -> Tuple[bool, str, str]:
        """
        Check if a trade should be blocked based on session rules.
        
        Note: In Phase 1 (log_only mode), this always returns False.
        
        Args:
            symbol: Trading symbol
            utc_time: UTC datetime
            
        Returns:
            Tuple of (should_block, session_name, relevance)
        """
        session_name, relevance, _ = self.evaluate(symbol, utc_time=utc_time)
        
        # Phase 1: Never block, only log
        if self.mode == "log_only":
            return False, session_name, relevance
        
        # Phase 3 (future): Block avoid combos
        if self.mode == "enforce" and relevance == "avoid":
            return True, session_name, relevance
        
        return False, session_name, relevance
    
    def get_session_context_for_journal(self, symbol: str, utc_time: datetime = None) -> Dict[str, str]:
        """
        Get session context to include in trade journal entries.
        
        Args:
            symbol: Trading symbol
            utc_time: UTC datetime
            
        Returns:
            Dict with session_name and session_relevance
        """
        if utc_time is None:
            utc_time = datetime.now(timezone.utc)
        
        session_name = self.get_current_session(utc_time)
        relevance = self.get_session_relevance(symbol, session_name)
        
        return {
            "session_name": session_name,
            "session_relevance": relevance
        }
