"""
Analyze trade validation logs to reverse-engineer broker's exact stop-distance formula.
Extracts all trade_validation_detail and order_send_result events from both log files.
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

def parse_log_file(log_path: Path) -> List[Dict]:
    """Parse JSONL log file and extract trade validation + order result pairs."""
    trades = []
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find all trade_validation_detail events
    for i, line in enumerate(lines):
        try:
            event = json.loads(line.strip())
            
            if event.get('message') == 'trade_validation_detail':
                # Extract validation data
                validation = {
                    'timestamp': event['timestamp'],
                    'symbol': event['symbol'],
                    'order_type': event['order_type'],
                    'entry': event['entry'],
                    'sl': event['sl'],
                    'tp': event['tp'],
                    'volume': event['volume'],
                    'sl_distance_pts': event['sl_distance_pts'],
                    'tp_distance_pts': event['tp_distance_pts'],
                    'broker_stops_level': event['broker_stops_level'],
                    'broker_spread': event['broker_spread'],
                    'broker_point': event['broker_point'],
                    'our_min_sl_pts': event['our_min_sl_pts'],
                }
                
                # Look ahead for the corresponding order_send_result
                result = None
                for j in range(i+1, min(i+10, len(lines))):
                    try:
                        next_event = json.loads(lines[j].strip())
                        if next_event.get('message') == 'order_send_result':
                            if next_event.get('symbol') == validation['symbol']:
                                result = {
                                    'retcode': next_event['retcode'],
                                    'retcode_description': next_event['retcode_description'],
                                    'success': next_event['success'],
                                    'ticket': next_event.get('ticket', 0),
                                    'attempt': next_event.get('attempt', 1),
                                }
                                break
                    except:
                        continue
                
                if result:
                    trades.append({**validation, **result})
        except:
            continue
    
    return trades

def analyze_trades(trades: List[Dict]) -> None:
    """Analyze trades to find broker's exact stop-distance requirements."""
    
    print("=" * 80)
    print("BROKER STOP-DISTANCE ANALYSIS")
    print("=" * 80)
    print(f"\nTotal trade attempts analyzed: {len(trades)}\n")
    
    # Group by symbol
    by_symbol = {}
    for trade in trades:
        symbol = trade['symbol']
        if symbol not in by_symbol:
            by_symbol[symbol] = {'accepted': [], 'rejected': []}
        
        if trade['success']:
            by_symbol[symbol]['accepted'].append(trade)
        else:
            by_symbol[symbol]['rejected'].append(trade)
    
    # Analyze each symbol
    for symbol in sorted(by_symbol.keys()):
        data = by_symbol[symbol]
        accepted = data['accepted']
        rejected = data['rejected']
        
        print(f"\n{'='*80}")
        print(f"SYMBOL: {symbol}")
        print(f"{'='*80}")
        print(f"Accepted: {len(accepted)} | Rejected: {len(rejected)}")
        
        if rejected:
            print(f"\n--- REJECTED TRADES (10016 Invalid Stops) ---")
            for trade in rejected:
                print(f"  SL distance: {trade['sl_distance_pts']:.1f} pts | "
                      f"Spread: {trade['broker_spread']} | "
                      f"Stops_level: {trade['broker_stops_level']} | "
                      f"Our min: {trade['our_min_sl_pts']:.1f}")
        
        if accepted:
            print(f"\n--- ACCEPTED TRADES (10009 Success) ---")
            for trade in accepted:
                print(f"  SL distance: {trade['sl_distance_pts']:.1f} pts | "
                      f"Spread: {trade['broker_spread']} | "
                      f"Stops_level: {trade['broker_stops_level']} | "
                      f"Our min: {trade['our_min_sl_pts']:.1f}")
        
        # Calculate minimum accepted and maximum rejected
        if accepted:
            min_accepted = min(t['sl_distance_pts'] for t in accepted)
            print(f"\n[OK] MINIMUM ACCEPTED: {min_accepted:.1f} pts")
        
        if rejected:
            max_rejected = max(t['sl_distance_pts'] for t in rejected)
            print(f"\n[REJECT] MAXIMUM REJECTED: {max_rejected:.1f} pts")
        
        # Derive broker's minimum requirement
        if accepted and rejected:
            print(f"\n[ANALYSIS] BROKER MINIMUM REQUIREMENT: Between {max_rejected:.1f} and {min_accepted:.1f} pts")
            recommended = min_accepted + 5  # Add 5pt safety buffer
            print(f"[RECOMMEND] PRE-CHECK MINIMUM: {recommended:.1f} pts")
        elif accepted:
            recommended = min_accepted
            print(f"\n[RECOMMEND] PRE-CHECK MINIMUM: {recommended:.1f} pts (based on accepted trades)")
        elif rejected:
            recommended = max_rejected + 10
            print(f"\n[RECOMMEND] PRE-CHECK MINIMUM: {recommended:.1f} pts (rejected + 10pt buffer)")
    
    # Summary table
    print(f"\n\n{'='*80}")
    print("RECOMMENDED SYMBOL-SPECIFIC MINIMUMS")
    print(f"{'='*80}")
    print(f"{'Symbol':<10} {'Min Accepted':<15} {'Max Rejected':<15} {'Recommended':<15}")
    print("-" * 80)
    
    for symbol in sorted(by_symbol.keys()):
        data = by_symbol[symbol]
        accepted = data['accepted']
        rejected = data['rejected']
        
        min_acc = min((t['sl_distance_pts'] for t in accepted), default=None)
        max_rej = max((t['sl_distance_pts'] for t in rejected), default=None)
        
        if min_acc and max_rej:
            recommended = min_acc + 5
        elif min_acc:
            recommended = min_acc
        elif max_rej:
            recommended = max_rej + 10
        else:
            recommended = None
        
        min_acc_str = f"{min_acc:.1f}" if min_acc else "N/A"
        max_rej_str = f"{max_rej:.1f}" if max_rej else "N/A"
        rec_str = f"{recommended:.1f}" if recommended else "N/A"
        
        print(f"{symbol:<10} {min_acc_str:<15} {max_rej_str:<15} {rec_str:<15}")

if __name__ == "__main__":
    # Parse both log files
    log_dir = Path(r"c:\Users\Index\DEVI\logs")
    
    asia_log = log_dir / "live_mt5_20251212_020047.json"
    london_log = log_dir / "live_mt5_20251212_075600.json"
    
    all_trades = []
    
    if asia_log.exists():
        print(f"Parsing Asia session log: {asia_log.name}")
        all_trades.extend(parse_log_file(asia_log))
    
    if london_log.exists():
        print(f"Parsing London/NY session log: {london_log.name}")
        all_trades.extend(parse_log_file(london_log))
    
    print(f"\nTotal trades extracted: {len(all_trades)}\n")
    
    # Analyze
    analyze_trades(all_trades)
