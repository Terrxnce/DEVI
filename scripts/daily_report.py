#!/usr/bin/env python3
"""
DEVI 2.0 Daily Trade Report Generator

Analyzes trade journal data and generates performance summaries.
Outputs: win rate, profit factor, avg R, max DD, breakdown by symbol + structure.

Usage:
    python scripts/daily_report.py                    # Today's report
    python scripts/daily_report.py --date 2025-12-18 # Specific date
    python scripts/daily_report.py --all             # All available data
"""

import argparse
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict


def load_journal_file(filepath: Path) -> List[Dict[str, Any]]:
    """Load a single trade journal JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []


def load_journals(journal_dir: Path, target_date: Optional[date] = None, load_all: bool = False) -> List[Dict[str, Any]]:
    """Load trade journal entries from files."""
    all_trades = []
    
    if not journal_dir.exists():
        print(f"Journal directory not found: {journal_dir}")
        return []
    
    # Find matching journal files
    for filepath in sorted(journal_dir.glob("trade_journal_*.json")):
        filename = filepath.name
        # Extract date from filename: trade_journal_YYYYMMDD.json
        try:
            date_str = filename.replace("trade_journal_", "").replace(".json", "")
            file_date = datetime.strptime(date_str, "%Y%m%d").date()
        except ValueError:
            continue
        
        if load_all:
            all_trades.extend(load_journal_file(filepath))
        elif target_date and file_date == target_date:
            all_trades.extend(load_journal_file(filepath))
        elif not target_date and not load_all:
            # Default to today
            if file_date == date.today():
                all_trades.extend(load_journal_file(filepath))
    
    return all_trades


def calculate_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate performance metrics from trades."""
    if not trades:
        return {"error": "No trades found"}
    
    total_trades = len(trades)
    wins = [t for t in trades if t.get("outcome") == "win"]
    losses = [t for t in trades if t.get("outcome") == "loss"]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    
    # P&L calculations
    total_pnl = sum(t.get("pnl_usd", 0) or 0 for t in trades)
    gross_profit = sum(t.get("pnl_usd", 0) or 0 for t in wins)
    gross_loss = abs(sum(t.get("pnl_usd", 0) or 0 for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    
    # R calculations
    achieved_rrs = [t.get("achieved_rr", 0) or 0 for t in trades]
    avg_r = sum(achieved_rrs) / len(achieved_rrs) if achieved_rrs else 0
    avg_winner_r = sum(t.get("achieved_rr", 0) or 0 for t in wins) / win_count if win_count > 0 else 0
    avg_loser_r = sum(t.get("achieved_rr", 0) or 0 for t in losses) / loss_count if loss_count > 0 else 0
    
    # Drawdown (simple: largest consecutive loss sequence)
    running_pnl = 0
    peak_pnl = 0
    max_dd = 0
    for t in sorted(trades, key=lambda x: x.get("exit_time", "")):
        running_pnl += t.get("pnl_usd", 0) or 0
        if running_pnl > peak_pnl:
            peak_pnl = running_pnl
        dd = peak_pnl - running_pnl
        if dd > max_dd:
            max_dd = dd
    
    return {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": loss_count,
        "win_rate_pct": round(win_rate, 1),
        "total_pnl_usd": round(total_pnl, 2),
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
        "avg_r": round(avg_r, 2),
        "avg_winner_r": round(avg_winner_r, 2),
        "avg_loser_r": round(avg_loser_r, 2),
        "max_drawdown_usd": round(max_dd, 2)
    }


def breakdown_by_symbol(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Break down performance by symbol."""
    by_symbol = defaultdict(list)
    for t in trades:
        symbol = t.get("symbol", "UNKNOWN")
        by_symbol[symbol].append(t)
    
    results = {}
    for symbol, symbol_trades in sorted(by_symbol.items()):
        metrics = calculate_metrics(symbol_trades)
        results[symbol] = {
            "trades": metrics["total_trades"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate_pct": metrics["win_rate_pct"],
            "pnl_usd": metrics["total_pnl_usd"]
        }
    return results


def breakdown_by_structure(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Break down performance by structure type."""
    by_structure = defaultdict(list)
    for t in trades:
        structure = t.get("structure_type", "unknown")
        by_structure[structure].append(t)
    
    results = {}
    for structure, struct_trades in sorted(by_structure.items()):
        metrics = calculate_metrics(struct_trades)
        results[structure] = {
            "trades": metrics["total_trades"],
            "wins": metrics["wins"],
            "losses": metrics["losses"],
            "win_rate_pct": metrics["win_rate_pct"],
            "pnl_usd": metrics["total_pnl_usd"]
        }
    return results


def breakdown_by_exit_reason(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Break down performance by exit reason."""
    by_exit = defaultdict(list)
    for t in trades:
        exit_reason = t.get("exit_reason", "unknown")
        by_exit[exit_reason].append(t)
    
    results = {}
    for reason, exit_trades in sorted(by_exit.items()):
        metrics = calculate_metrics(exit_trades)
        results[reason] = {
            "trades": metrics["total_trades"],
            "pnl_usd": metrics["total_pnl_usd"]
        }
    return results


def count_stacked_trades(trades: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count trades that were potentially stacked (same symbol, overlapping time)."""
    # Group by symbol
    by_symbol = defaultdict(list)
    for t in trades:
        symbol = t.get("symbol", "UNKNOWN")
        by_symbol[symbol].append(t)
    
    stacked_count = 0
    conflict_count = 0
    
    for symbol, symbol_trades in by_symbol.items():
        # Sort by entry time
        sorted_trades = sorted(symbol_trades, key=lambda x: x.get("entry_time", ""))
        
        for i, trade in enumerate(sorted_trades):
            entry_time = trade.get("entry_time", "")
            exit_time = trade.get("exit_time", "")
            direction = trade.get("direction", "")
            
            # Check if any previous trade was still open when this one entered
            for prev_trade in sorted_trades[:i]:
                prev_exit = prev_trade.get("exit_time", "")
                if prev_exit > entry_time:
                    stacked_count += 1
                    # Check if opposite direction (conflict)
                    if prev_trade.get("direction") != direction:
                        conflict_count += 1
                    break
    
    return {
        "stacked_trades": stacked_count,
        "conflicting_trades": conflict_count
    }


def print_report(
    metrics: Dict[str, Any],
    by_symbol: Dict[str, Dict[str, Any]],
    by_structure: Dict[str, Dict[str, Any]],
    by_exit: Dict[str, Dict[str, Any]],
    stacking: Dict[str, int],
    report_date: str
):
    """Print formatted report to console."""
    print("\n" + "=" * 60)
    print(f"  DEVI 2.0 DAILY TRADE REPORT - {report_date}")
    print("=" * 60)
    
    if "error" in metrics:
        print(f"\n{metrics['error']}")
        return
    
    # Overall metrics
    print("\n## OVERALL PERFORMANCE")
    print(f"  Total Trades:    {metrics['total_trades']}")
    print(f"  Wins/Losses:     {metrics['wins']} / {metrics['losses']}")
    print(f"  Win Rate:        {metrics['win_rate_pct']}%")
    print(f"  Total P&L:       ${metrics['total_pnl_usd']:,.2f}")
    print(f"  Profit Factor:   {metrics['profit_factor']}")
    print(f"  Avg R:           {metrics['avg_r']}")
    print(f"  Avg Winner R:    {metrics['avg_winner_r']}")
    print(f"  Avg Loser R:     {metrics['avg_loser_r']}")
    print(f"  Max Drawdown:    ${metrics['max_drawdown_usd']:,.2f}")
    
    # Stacking info
    print("\n## POSITION CLUSTERING")
    print(f"  Stacked Trades:     {stacking['stacked_trades']}")
    print(f"  Conflicting Trades: {stacking['conflicting_trades']}")
    
    # By symbol
    print("\n## BY SYMBOL")
    print(f"  {'Symbol':<10} {'Trades':>7} {'W/L':>8} {'WR%':>6} {'P&L':>12}")
    print("  " + "-" * 45)
    for symbol, data in by_symbol.items():
        wl = f"{data['wins']}/{data['losses']}"
        print(f"  {symbol:<10} {data['trades']:>7} {wl:>8} {data['win_rate_pct']:>5.1f}% ${data['pnl_usd']:>10,.2f}")
    
    # By structure
    print("\n## BY STRUCTURE TYPE")
    print(f"  {'Structure':<15} {'Trades':>7} {'W/L':>8} {'WR%':>6} {'P&L':>12}")
    print("  " + "-" * 50)
    for structure, data in by_structure.items():
        wl = f"{data['wins']}/{data['losses']}"
        print(f"  {structure:<15} {data['trades']:>7} {wl:>8} {data['win_rate_pct']:>5.1f}% ${data['pnl_usd']:>10,.2f}")
    
    # By exit reason
    print("\n## BY EXIT REASON")
    print(f"  {'Reason':<20} {'Trades':>7} {'P&L':>12}")
    print("  " + "-" * 40)
    for reason, data in by_exit.items():
        print(f"  {reason:<20} {data['trades']:>7} ${data['pnl_usd']:>10,.2f}")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="DEVI 2.0 Daily Trade Report")
    parser.add_argument("--date", type=str, help="Report date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Report on all available data")
    parser.add_argument("--journal-dir", type=str, default="logs/trade_journal", 
                       help="Path to trade journal directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    # Determine report date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            report_date = args.date
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            return
    elif args.all:
        target_date = None
        report_date = "ALL TIME"
    else:
        target_date = date.today()
        report_date = target_date.isoformat()
    
    # Load trades
    journal_dir = Path(args.journal_dir)
    trades = load_journals(journal_dir, target_date, args.all)
    
    if not trades:
        print(f"No trades found for {report_date}")
        # Try to find available dates
        available = list(journal_dir.glob("trade_journal_*.json"))
        if available:
            print(f"\nAvailable journal files:")
            for f in sorted(available)[-5:]:
                print(f"  {f.name}")
        return
    
    # Calculate metrics
    metrics = calculate_metrics(trades)
    by_symbol = breakdown_by_symbol(trades)
    by_structure = breakdown_by_structure(trades)
    by_exit = breakdown_by_exit_reason(trades)
    stacking = count_stacked_trades(trades)
    
    if args.json:
        output = {
            "date": report_date,
            "overall": metrics,
            "by_symbol": by_symbol,
            "by_structure": by_structure,
            "by_exit_reason": by_exit,
            "clustering": stacking
        }
        print(json.dumps(output, indent=2))
    else:
        print_report(metrics, by_symbol, by_structure, by_exit, stacking, report_date)


if __name__ == "__main__":
    main()
