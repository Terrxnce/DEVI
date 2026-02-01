#!/usr/bin/env python3
"""
Rejection Breakdown Analysis

Generates a detailed breakdown of rejection trades to identify
the exact failure mode for rejection BUY underperformance.

Outputs:
  - reports/rejection_breakdown_YYYYMMDD.md (human readable)
  - reports/rejection_breakdown_YYYYMMDD.json (machine readable)

Usage:
  python tools/rejection_breakdown.py
  python tools/rejection_breakdown.py --start 2026-01-05 --end 2026-01-13
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from collections import defaultdict
import argparse

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def load_trades(journal_dir: str, start_date: str = None, end_date: str = None) -> List[Dict]:
    """Load all trades from journal files within date range."""
    all_trades = []
    
    files = sorted([f for f in os.listdir(journal_dir) 
                   if f.startswith("trade_journal_") and f.endswith(".json")])
    
    for filename in files:
        # Extract date from filename
        date_str = filename.replace("trade_journal_", "").replace(".json", "")
        
        # Filter by date range if specified
        if start_date and date_str < start_date.replace("-", ""):
            continue
        if end_date and date_str > end_date.replace("-", ""):
            continue
        
        filepath = os.path.join(journal_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                trades = json.load(f)
                all_trades.extend(trades)
        except Exception as e:
            print(f"Warning: Could not load {filename}: {e}")
    
    return all_trades


def filter_rejection_trades(trades: List[Dict]) -> List[Dict]:
    """Filter to only rejection trades with valid direction."""
    return [t for t in trades 
            if t.get("structure_type") == "rejection" 
            and t.get("direction") in ["BUY", "SELL"]]


def compute_metrics(trades: List[Dict]) -> Dict[str, Any]:
    """Compute aggregate metrics for a set of trades."""
    if not trades:
        return {
            "n": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "avg_pnl": 0, "profit_factor": 0,
            "total_r": 0, "avg_r": 0, "avg_r_win": 0, "avg_r_loss": 0
        }
    
    n = len(trades)
    wins = [t for t in trades if t.get("outcome") == "win"]
    losses = [t for t in trades if t.get("outcome") == "loss"]
    
    total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
    avg_pnl = total_pnl / n
    
    # R-multiples (using achieved_rr)
    r_values = [t.get("achieved_rr", 0) for t in trades if t.get("achieved_rr") is not None]
    total_r = sum(r_values)
    avg_r = total_r / len(r_values) if r_values else 0
    
    win_r = [t.get("achieved_rr", 0) for t in wins if t.get("achieved_rr") is not None]
    loss_r = [t.get("achieved_rr", 0) for t in losses if t.get("achieved_rr") is not None]
    
    avg_r_win = sum(win_r) / len(win_r) if win_r else 0
    avg_r_loss = sum(loss_r) / len(loss_r) if loss_r else 0
    
    # Profit factor
    gross_profit = sum(t.get("pnl_usd", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl_usd", 0) for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    
    return {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n if n > 0 else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "total_r": round(total_r, 2),
        "avg_r": round(avg_r, 3),
        "avg_r_win": round(avg_r_win, 2),
        "avg_r_loss": round(avg_r_loss, 2)
    }


def direction_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by BUY vs SELL."""
    buy_trades = [t for t in trades if t.get("direction") == "BUY"]
    sell_trades = [t for t in trades if t.get("direction") == "SELL"]
    
    return {
        "BUY": compute_metrics(buy_trades),
        "SELL": compute_metrics(sell_trades)
    }


def session_relevance_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by session relevance (ideal/acceptable/avoid)."""
    result = {}
    for relevance in ["ideal", "acceptable", "avoid", "unknown", ""]:
        subset = [t for t in trades if t.get("session_relevance", "") == relevance]
        if subset:
            key = relevance if relevance else "unknown"
            result[key] = compute_metrics(subset)
    return result


def session_name_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by session name."""
    result = {}
    sessions = set(t.get("session_name", "unknown") for t in trades)
    for session in sessions:
        subset = [t for t in trades if t.get("session_name", "unknown") == session]
        if subset:
            result[session if session else "unknown"] = compute_metrics(subset)
    return result


def symbol_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by symbol."""
    result = {}
    symbols = set(t.get("symbol", "UNKNOWN") for t in trades)
    for symbol in symbols:
        subset = [t for t in trades if t.get("symbol") == symbol]
        if subset:
            result[symbol] = compute_metrics(subset)
    return result


def direction_session_relevance_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by direction x session_relevance."""
    result = {}
    for direction in ["BUY", "SELL"]:
        for relevance in ["ideal", "acceptable", "avoid", "unknown"]:
            subset = [t for t in trades 
                     if t.get("direction") == direction 
                     and (t.get("session_relevance", "") == relevance or 
                          (relevance == "unknown" and not t.get("session_relevance")))]
            if subset:
                key = f"{direction}_{relevance}"
                result[key] = compute_metrics(subset)
    return result


def htf_alignment_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by HTF alignment (aligned/counter/neutral/unknown)."""
    result = {}
    for alignment in ["aligned", "counter", "neutral", "unknown", ""]:
        subset = [t for t in trades if (t.get("htf_alignment", "") or "unknown") == (alignment or "unknown")]
        if subset:
            key = alignment if alignment else "unknown"
            result[key] = compute_metrics(subset)
    return result


def direction_htf_split(trades: List[Dict]) -> Dict[str, Dict]:
    """Split by direction x htf_alignment."""
    result = {}
    for direction in ["BUY", "SELL"]:
        for alignment in ["aligned", "counter", "neutral", "unknown"]:
            subset = [t for t in trades 
                     if t.get("direction") == direction 
                     and (t.get("htf_alignment", "") or "unknown") == alignment]
            if subset:
                key = f"{direction}_{alignment}"
                result[key] = compute_metrics(subset)
    return result


def intersection_table(trades: List[Dict]) -> List[Dict]:
    """
    Build intersection table: symbol x direction x htf_alignment x session_relevance
    Ranked by worst avg_r (expectancy).
    """
    combos = defaultdict(list)
    
    for t in trades:
        symbol = t.get("symbol", "UNKNOWN")
        direction = t.get("direction", "UNKNOWN")
        htf_align = t.get("htf_alignment", "") or "unknown"
        session_rel = t.get("session_relevance", "") or "unknown"
        
        key = f"{symbol}|{direction}|{htf_align}|{session_rel}"
        combos[key].append(t)
    
    results = []
    for key, subset in combos.items():
        parts = key.split("|")
        metrics = compute_metrics(subset)
        results.append({
            "symbol": parts[0],
            "direction": parts[1],
            "htf_alignment": parts[2],
            "session_relevance": parts[3],
            **metrics
        })
    
    # Sort by avg_r (worst first)
    results.sort(key=lambda x: x["avg_r"])
    
    return results


def generate_markdown_report(
    all_rejection: List[Dict],
    direction_data: Dict,
    session_rel_data: Dict,
    session_name_data: Dict,
    symbol_data: Dict,
    dir_session_data: Dict,
    htf_data: Dict,
    dir_htf_data: Dict,
    intersection_data: List[Dict],
    date_range: str
) -> str:
    """Generate human-readable markdown report."""
    
    overall = compute_metrics(all_rejection)
    
    lines = [
        f"# Rejection Breakdown Report",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC*",
        f"*Date Range: {date_range}*",
        "",
        "## Executive Summary",
        "",
        f"Total rejection trades: **{overall['n']}** ({overall['wins']}W/{overall['losses']}L)",
        f"Win Rate: **{overall['win_rate']:.1%}**",
        f"Total PnL: **${overall['total_pnl']:,.2f}**",
        f"Avg R: **{overall['avg_r']:.3f}** (Win: {overall['avg_r_win']:.2f}R, Loss: {overall['avg_r_loss']:.2f}R)",
        f"Profit Factor: **{overall['profit_factor']:.2f}**",
        "",
        "---",
        "",
        "## 1. Direction Split (BUY vs SELL)",
        "",
        "| Direction | N | W/L | Win Rate | PnL | Avg R | PF |",
        "|-----------|---|-----|----------|-----|-------|-----|",
    ]
    
    for direction, m in direction_data.items():
        lines.append(
            f"| {direction} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} | {m['profit_factor']:.2f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 2. Session Relevance Split",
        "",
        "| Relevance | N | W/L | Win Rate | PnL | Avg R |",
        "|-----------|---|-----|----------|-----|-------|",
    ])
    
    for relevance, m in sorted(session_rel_data.items()):
        lines.append(
            f"| {relevance} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 3. Direction x Session Relevance",
        "",
        "| Combo | N | W/L | Win Rate | PnL | Avg R |",
        "|-------|---|-----|----------|-----|-------|",
    ])
    
    for combo, m in sorted(dir_session_data.items(), key=lambda x: x[1]['avg_r']):
        lines.append(
            f"| {combo} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 4. Symbol Split",
        "",
        "| Symbol | N | W/L | Win Rate | PnL | Avg R |",
        "|--------|---|-----|----------|-----|-------|",
    ])
    
    for symbol, m in sorted(symbol_data.items(), key=lambda x: x[1]['avg_r']):
        lines.append(
            f"| {symbol} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 5. Session Name Split",
        "",
        "| Session | N | W/L | Win Rate | PnL | Avg R |",
        "|---------|---|-----|----------|-----|-------|",
    ])
    
    for session, m in sorted(session_name_data.items(), key=lambda x: x[1]['avg_r']):
        lines.append(
            f"| {session} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    # HTF Alignment section
    lines.extend([
        "",
        "---",
        "",
        "## 6. HTF Alignment Split",
        "",
        "| HTF Alignment | N | W/L | Win Rate | PnL | Avg R |",
        "|---------------|---|-----|----------|-----|-------|",
    ])
    
    for alignment, m in sorted(htf_data.items(), key=lambda x: x[1]['avg_r']):
        lines.append(
            f"| {alignment} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 7. Direction x HTF Alignment",
        "",
        "| Combo | N | W/L | Win Rate | PnL | Avg R |",
        "|-------|---|-----|----------|-----|-------|",
    ])
    
    for combo, m in sorted(dir_htf_data.items(), key=lambda x: x[1]['avg_r']):
        lines.append(
            f"| {combo} | {m['n']} | {m['wins']}/{m['losses']} | "
            f"{m['win_rate']:.1%} | ${m['total_pnl']:,.0f} | {m['avg_r']:.3f} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 8. Intersection Table (Worst Combos First)",
        "",
        "*Ranked by Avg R (expectancy). Includes HTF alignment.*",
        "",
        "| Symbol | Dir | HTF | Session | N | W/L | WR | PnL | Avg R |",
        "|--------|-----|-----|---------|---|-----|-----|-----|-------|",
    ])
    
    for row in intersection_data[:20]:  # Top 20 worst
        if row['n'] >= 2:  # Only show combos with 2+ trades
            lines.append(
                f"| {row['symbol']} | {row['direction']} | {row['htf_alignment']} | "
                f"{row['session_relevance']} | {row['n']} | {row['wins']}/{row['losses']} | "
                f"{row['win_rate']:.0%} | ${row['total_pnl']:,.0f} | {row['avg_r']:.3f} |"
            )
    
    lines.extend([
        "",
        "---",
        "",
        "## 9. Key Findings",
        "",
    ])
    
    # Auto-generate key findings
    buy_data = direction_data.get("BUY", {})
    sell_data = direction_data.get("SELL", {})
    
    if buy_data.get("avg_r", 0) < sell_data.get("avg_r", 0):
        diff = sell_data.get("avg_r", 0) - buy_data.get("avg_r", 0)
        lines.append(f"- **BUY underperforms SELL by {diff:.3f}R per trade**")
    
    # Find worst symbol for BUY
    buy_by_symbol = {}
    for row in intersection_data:
        if row['direction'] == 'BUY' and row['n'] >= 3:
            sym = row['symbol']
            if sym not in buy_by_symbol:
                buy_by_symbol[sym] = {'n': 0, 'total_r': 0}
            buy_by_symbol[sym]['n'] += row['n']
            buy_by_symbol[sym]['total_r'] += row['total_r']
    
    if buy_by_symbol:
        worst_sym = min(buy_by_symbol.items(), key=lambda x: x[1]['total_r'] / x[1]['n'] if x[1]['n'] > 0 else 0)
        avg_r = worst_sym[1]['total_r'] / worst_sym[1]['n'] if worst_sym[1]['n'] > 0 else 0
        lines.append(f"- **Worst BUY symbol: {worst_sym[0]}** (avg R = {avg_r:.3f}, n = {worst_sym[1]['n']})")
    
    # Find worst session relevance for BUY
    for combo, m in dir_session_data.items():
        if combo.startswith("BUY_") and m['n'] >= 3 and m['avg_r'] < -0.3:
            lines.append(f"- **{combo}**: {m['n']} trades, avg R = {m['avg_r']:.3f}")
    
    # Add HTF-specific findings
    buy_counter = dir_htf_data.get("BUY_counter", {})
    buy_aligned = dir_htf_data.get("BUY_aligned", {})
    if buy_counter.get("n", 0) >= 3 and buy_aligned.get("n", 0) >= 3:
        if buy_counter.get("avg_r", 0) < buy_aligned.get("avg_r", 0):
            diff = buy_aligned.get("avg_r", 0) - buy_counter.get("avg_r", 0)
            lines.append(f"- **BUY_counter underperforms BUY_aligned by {diff:.3f}R per trade**")
    
    lines.extend([
        "",
        "---",
        "",
        "## 10. Data Notes",
        "",
    ])
    
    # Check if HTF data is present
    has_htf = any(t.get("htf_alignment") for t in all_rejection)
    if has_htf:
        lines.append("**HTF alignment data is available.** Analysis includes HTF-based breakdowns.")
    else:
        lines.append("**HTF alignment data not yet available for these trades.**")
        lines.append("New trades will include HTF data. Re-run after collecting more trades.")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Rejection breakdown analysis")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()
    
    # Paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    journal_dir = os.path.join(base_dir, "logs", "trade_journal")
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    # Load trades
    all_trades = load_trades(journal_dir, args.start, args.end)
    rejection_trades = filter_rejection_trades(all_trades)
    
    if not rejection_trades:
        print("No rejection trades found in the specified date range.")
        return
    
    # Date range for report
    if args.start and args.end:
        date_range = f"{args.start} to {args.end}"
    else:
        date_range = "All available data"
    
    # Compute all breakdowns
    direction_data = direction_split(rejection_trades)
    session_rel_data = session_relevance_split(rejection_trades)
    session_name_data = session_name_split(rejection_trades)
    symbol_data = symbol_split(rejection_trades)
    dir_session_data = direction_session_relevance_split(rejection_trades)
    htf_data = htf_alignment_split(rejection_trades)
    dir_htf_data = direction_htf_split(rejection_trades)
    intersection_data = intersection_table(rejection_trades)
    
    # Generate reports
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    
    # Markdown report
    md_content = generate_markdown_report(
        rejection_trades,
        direction_data,
        session_rel_data,
        session_name_data,
        symbol_data,
        dir_session_data,
        htf_data,
        dir_htf_data,
        intersection_data,
        date_range
    )
    
    md_path = os.path.join(reports_dir, f"rejection_breakdown_{today}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    # JSON report
    json_data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "date_range": date_range,
        "overall": compute_metrics(rejection_trades),
        "by_direction": direction_data,
        "by_session_relevance": session_rel_data,
        "by_session_name": session_name_data,
        "by_symbol": symbol_data,
        "direction_x_session_relevance": dir_session_data,
        "by_htf_alignment": htf_data,
        "direction_x_htf_alignment": dir_htf_data,
        "intersection_table": intersection_data
    }
    
    json_path = os.path.join(reports_dir, f"rejection_breakdown_{today}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    
    # Print summary to console
    print(md_content)
    print()
    print(f"Reports saved to:")
    print(f"  - {md_path}")
    print(f"  - {json_path}")


if __name__ == "__main__":
    main()
