"""
Trade Journal - Tracks trade outcomes for strategy analysis.

This module provides:
1. Entry caching - stores entry details when trades are executed
2. Outcome logging - calculates P&L, RR achieved, win/loss when positions close
3. JSON persistence - appends trade records to daily journal files
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class TradeEntry:
    """Cached entry details for linking to exit."""
    ticket: int
    symbol: str
    direction: str  # BUY or SELL
    structure_type: str
    entry_time: str  # ISO format
    entry_price: float
    sl: float
    tp: float
    volume: float
    intended_rr: float
    magic: int = 0
    comment: str = ""
    session_name: str = ""  # Trading session at entry (Asia/London/NY/London_NY)
    session_relevance: str = ""  # ideal/acceptable/avoid/unknown
    htf_bias: str = ""  # bullish/bearish/neutral/unknown
    htf_alignment: str = ""  # aligned/counter/neutral/unknown
    htf_distance_atr: Optional[float] = None  # abs(close-ema)/atr at entry
    htf_clear_trend: Optional[bool] = None  # met hard-block threshold at entry


@dataclass
class TradeOutcome:
    """Complete trade record with entry and exit details."""
    ticket: int
    symbol: str
    direction: str
    structure_type: str
    entry_time: str
    entry_price: float
    sl: float
    tp: float
    volume: float
    intended_rr: float
    exit_time: str
    exit_price: float
    exit_reason: str  # sl_hit, tp_hit, manual, unknown
    pnl_pips: float
    pnl_usd: float
    achieved_rr: float
    hold_time_minutes: float
    outcome: str  # win, loss, breakeven
    magic: int = 0
    comment: str = ""
    session_name: str = ""  # Trading session at entry
    session_relevance: str = ""  # ideal/acceptable/avoid/unknown
    htf_bias: str = ""  # bullish/bearish/neutral/unknown (snapshot at entry)
    htf_alignment: str = ""  # aligned/counter/neutral/unknown (snapshot at entry)
    htf_distance_atr: Optional[float] = None  # abs(close-ema)/atr at entry
    htf_clear_trend: Optional[bool] = None  # met hard-block threshold at entry


class TradeJournal:
    """
    Manages trade entry caching and outcome logging.
    
    Usage:
        journal = TradeJournal(journal_dir="logs/trade_journal")
        
        # On successful trade execution:
        journal.cache_entry(ticket=123, symbol="EURUSD", ...)
        
        # On position close:
        journal.record_outcome(ticket=123, exit_price=1.0450, ...)
    """
    
    def __init__(self, journal_dir: str = None, enabled: bool = True):
        self.enabled = enabled
        
        if journal_dir is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            journal_dir = os.path.join(base_dir, "logs", "trade_journal")
        
        self.journal_dir = journal_dir
        self._entry_cache: Dict[int, TradeEntry] = {}  # ticket -> TradeEntry
        self._recorded_tickets: set = set()  # tickets already written to journal
        
        # Ensure journal directory exists
        if self.enabled:
            os.makedirs(self.journal_dir, exist_ok=True)
            logger.info("trade_journal_initialized", extra={
                "journal_dir": self.journal_dir,
                "enabled": self.enabled
            })
    
    def cache_entry(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        structure_type: str,
        entry_price: float,
        sl: float,
        tp: float,
        volume: float,
        intended_rr: float,
        magic: int = 0,
        comment: str = "",
        entry_time: datetime = None,
        session_name: str = "",
        session_relevance: str = "",
        htf_bias: str = "",
        htf_alignment: str = "",
        htf_distance_atr: Optional[float] = None,
        htf_clear_trend: Optional[bool] = None
    ) -> None:
        """
        Cache entry details for later linking to exit.
        Called when a trade is successfully executed.
        """
        if not self.enabled:
            return
        
        if entry_time is None:
            entry_time = datetime.now(timezone.utc)
        
        entry = TradeEntry(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            structure_type=structure_type,
            entry_time=entry_time.isoformat(),
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            volume=volume,
            intended_rr=intended_rr,
            magic=magic,
            comment=comment,
            session_name=session_name,
            session_relevance=session_relevance,
            htf_bias=htf_bias,
            htf_alignment=htf_alignment,
            htf_distance_atr=htf_distance_atr,
            htf_clear_trend=htf_clear_trend
        )
        
        self._entry_cache[ticket] = entry
        
        logger.info("trade_entry_cached", extra={
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "structure_type": structure_type,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "volume": volume,
            "intended_rr": intended_rr
        })
    
    def get_cached_entry(self, ticket: int) -> Optional[TradeEntry]:
        """Retrieve cached entry by ticket."""
        return self._entry_cache.get(ticket)
    
    def record_outcome(
        self,
        ticket: int,
        exit_price: float,
        exit_reason: str,
        pnl_usd: float,
        exit_time: datetime = None,
        symbol: str = None,
        volume: float = None,
        point: float = None
    ) -> Optional[TradeOutcome]:
        """
        Record trade outcome when position closes.
        Links to cached entry if available, otherwise uses provided details.
        """
        if not self.enabled:
            return None
        
        # Skip if already recorded (prevents duplicate entries)
        if ticket in self._recorded_tickets:
            logger.debug("trade_outcome_already_recorded", extra={"ticket": ticket})
            return None
        
        if exit_time is None:
            exit_time = datetime.now(timezone.utc)
        
        # Try to get cached entry
        entry = self._entry_cache.get(ticket)
        
        if entry is None:
            # No cached entry - log warning but still record what we can
            logger.warning("trade_outcome_no_cached_entry", extra={
                "ticket": ticket,
                "symbol": symbol,
                "exit_price": exit_price,
                "pnl_usd": pnl_usd,
                "exit_reason": exit_reason
            })
            
            # Create minimal outcome record
            outcome = TradeOutcome(
                ticket=ticket,
                symbol=symbol or "UNKNOWN",
                direction="UNKNOWN",
                structure_type="unknown",
                entry_time="",
                entry_price=0.0,
                sl=0.0,
                tp=0.0,
                volume=volume or 0.0,
                intended_rr=0.0,
                exit_time=exit_time.isoformat(),
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_pips=0.0,
                pnl_usd=pnl_usd,
                achieved_rr=0.0,
                hold_time_minutes=0.0,
                outcome="win" if pnl_usd > 0 else ("loss" if pnl_usd < 0 else "breakeven")
            )
        else:
            # Calculate metrics from cached entry
            direction_mult = 1 if entry.direction == "BUY" else -1
            
            # P&L in pips
            if point and point > 0:
                pnl_pips = (exit_price - entry.entry_price) * direction_mult / point
            else:
                # Estimate point based on symbol
                estimated_point = 0.0001 if "JPY" not in entry.symbol else 0.01
                if "XAU" in entry.symbol:
                    estimated_point = 0.01
                pnl_pips = (exit_price - entry.entry_price) * direction_mult / estimated_point
            
            # Achieved RR
            risk_distance = abs(entry.entry_price - entry.sl)
            if risk_distance > 0:
                reward_distance = (exit_price - entry.entry_price) * direction_mult
                achieved_rr = reward_distance / risk_distance
            else:
                achieved_rr = 0.0
            
            # Hold time
            try:
                entry_dt = datetime.fromisoformat(entry.entry_time.replace('Z', '+00:00'))
                hold_seconds = (exit_time - entry_dt).total_seconds()
                hold_time_minutes = hold_seconds / 60.0
            except Exception:
                hold_time_minutes = 0.0
            
            # Outcome classification
            if pnl_usd > 0:
                outcome_str = "win"
            elif pnl_usd < 0:
                outcome_str = "loss"
            else:
                outcome_str = "breakeven"
            
            outcome = TradeOutcome(
                ticket=entry.ticket,
                symbol=entry.symbol,
                direction=entry.direction,
                structure_type=entry.structure_type,
                entry_time=entry.entry_time,
                entry_price=entry.entry_price,
                sl=entry.sl,
                tp=entry.tp,
                volume=entry.volume,
                intended_rr=entry.intended_rr,
                exit_time=exit_time.isoformat(),
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_pips=round(pnl_pips, 1),
                pnl_usd=round(pnl_usd, 2),
                achieved_rr=round(achieved_rr, 2),
                hold_time_minutes=round(hold_time_minutes, 1),
                outcome=outcome_str,
                magic=entry.magic,
                comment=entry.comment,
                session_name=entry.session_name,
                session_relevance=entry.session_relevance,
                htf_bias=entry.htf_bias,
                htf_alignment=entry.htf_alignment,
                htf_distance_atr=entry.htf_distance_atr,
                htf_clear_trend=entry.htf_clear_trend
            )
            
            # Remove from cache after recording
            del self._entry_cache[ticket]
        
        # Persist to journal file
        self._write_to_journal(outcome)
        
        # Mark as recorded to prevent duplicates
        self._recorded_tickets.add(ticket)
        
        # Log the outcome
        logger.info("trade_outcome_recorded", extra={
            "ticket": outcome.ticket,
            "symbol": outcome.symbol,
            "direction": outcome.direction,
            "structure_type": outcome.structure_type,
            "entry_price": outcome.entry_price,
            "exit_price": outcome.exit_price,
            "exit_reason": outcome.exit_reason,
            "pnl_pips": outcome.pnl_pips,
            "pnl_usd": outcome.pnl_usd,
            "intended_rr": outcome.intended_rr,
            "achieved_rr": outcome.achieved_rr,
            "hold_time_minutes": outcome.hold_time_minutes,
            "outcome": outcome.outcome
        })
        
        return outcome
    
    def _write_to_journal(self, outcome: TradeOutcome) -> None:
        """Append outcome to daily journal file."""
        try:
            # Daily file: trade_journal_YYYYMMDD.json
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            filename = f"trade_journal_{date_str}.json"
            filepath = os.path.join(self.journal_dir, filename)
            
            # Load existing records or start fresh
            records = []
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except (json.JSONDecodeError, IOError):
                    records = []
            
            # Append new outcome
            records.append(asdict(outcome))
            
            # Write back
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            
            logger.debug("trade_journal_written", extra={
                "filepath": filepath,
                "total_records": len(records)
            })
            
        except Exception as e:
            logger.error("trade_journal_write_failed", extra={
                "error": str(e),
                "ticket": outcome.ticket
            })
    
    def get_summary(self, date_str: str = None) -> Dict[str, Any]:
        """
        Get summary statistics for a given day (or today if not specified).
        
        Returns:
            Dict with win_rate, total_pnl, avg_rr, trades_by_structure, etc.
        """
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        
        filename = f"trade_journal_{date_str}.json"
        filepath = os.path.join(self.journal_dir, filename)
        
        if not os.path.exists(filepath):
            return {"error": "no_journal_for_date", "date": date_str}
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as e:
            return {"error": str(e), "date": date_str}
        
        if not records:
            return {"error": "empty_journal", "date": date_str}
        
        # Calculate summary
        total_trades = len(records)
        wins = sum(1 for r in records if r.get("outcome") == "win")
        losses = sum(1 for r in records if r.get("outcome") == "loss")
        breakevens = sum(1 for r in records if r.get("outcome") == "breakeven")
        
        total_pnl = sum(r.get("pnl_usd", 0) for r in records)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        achieved_rrs = [r.get("achieved_rr", 0) for r in records if r.get("achieved_rr") is not None]
        avg_achieved_rr = sum(achieved_rrs) / len(achieved_rrs) if achieved_rrs else 0
        
        # By structure type
        by_structure = {}
        for r in records:
            st = r.get("structure_type", "unknown")
            if st not in by_structure:
                by_structure[st] = {"count": 0, "wins": 0, "pnl": 0}
            by_structure[st]["count"] += 1
            by_structure[st]["pnl"] += r.get("pnl_usd", 0)
            if r.get("outcome") == "win":
                by_structure[st]["wins"] += 1
        
        # By symbol
        by_symbol = {}
        for r in records:
            sym = r.get("symbol", "UNKNOWN")
            if sym not in by_symbol:
                by_symbol[sym] = {"count": 0, "wins": 0, "pnl": 0}
            by_symbol[sym]["count"] += 1
            by_symbol[sym]["pnl"] += r.get("pnl_usd", 0)
            if r.get("outcome") == "win":
                by_symbol[sym]["wins"] += 1
        
        return {
            "date": date_str,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_rate": round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
            "total_pnl_usd": round(total_pnl, 2),
            "avg_pnl_usd": round(avg_pnl, 2),
            "avg_achieved_rr": round(avg_achieved_rr, 2),
            "by_structure": by_structure,
            "by_symbol": by_symbol
        }
    
    def get_cached_entry_count(self) -> int:
        """Return number of entries currently cached (open positions)."""
        return len(self._entry_cache)
