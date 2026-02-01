#!/usr/bin/env python3
"""Analyze a live MT5 session log file."""
import json
import sys
from collections import defaultdict

def analyze_log(log_path):
    with open(log_path, 'r') as f:
        lines = f.readlines()
    
    executed = []
    blocked = defaultdict(int)
    blocked_details = []
    
    for line in lines:
        try:
            data = json.loads(line.strip())
            msg = data.get('message', '')
            
            if msg == 'trade_executed_enhanced':
                executed.append(data)
            elif msg.startswith('trade_blocked_by'):
                blocked[msg] += 1
                blocked_details.append(data)
        except:
            continue
    
    print("=" * 70)
    print("SESSION ANALYSIS")
    print("=" * 70)
    
    # Executed trades breakdown
    print(f"\n## EXECUTED TRADES: {len(executed)}")
    
    # By structure type
    by_structure = defaultdict(int)
    by_symbol = defaultdict(int)
    by_direction = defaultdict(int)
    by_session = defaultdict(int)
    by_exit_method = defaultdict(int)
    
    for t in executed:
        by_structure[t.get('structure_type', 'unknown')] += 1
        by_symbol[t.get('symbol', 'unknown')] += 1
        by_direction[t.get('order_type', 'unknown')] += 1
        by_session[t.get('session', 'unknown')] += 1
        by_exit_method[t.get('exit_method', 'unknown')] += 1
    
    print("\n### By Structure Type:")
    for k, v in sorted(by_structure.items(), key=lambda x: -x[1]):
        pct = v / len(executed) * 100 if executed else 0
        print(f"  {k}: {v} ({pct:.1f}%)")
    
    print("\n### By Symbol:")
    for k, v in sorted(by_symbol.items(), key=lambda x: -x[1]):
        pct = v / len(executed) * 100 if executed else 0
        print(f"  {k}: {v} ({pct:.1f}%)")
    
    print("\n### By Direction:")
    for k, v in sorted(by_direction.items(), key=lambda x: -x[1]):
        pct = v / len(executed) * 100 if executed else 0
        print(f"  {k}: {v} ({pct:.1f}%)")
    
    print("\n### By Exit Method:")
    for k, v in sorted(by_exit_method.items(), key=lambda x: -x[1]):
        pct = v / len(executed) * 100 if executed else 0
        print(f"  {k}: {v} ({pct:.1f}%)")
    
    # Blocked trades breakdown
    print(f"\n## BLOCKED TRADES: {sum(blocked.values())}")
    print("\n### By Block Reason:")
    for k, v in sorted(blocked.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    
    # Structure threshold blocks detail
    threshold_blocks = [d for d in blocked_details if d.get('message') == 'trade_blocked_by_structure_threshold']
    if threshold_blocks:
        print("\n### Structure Threshold Blocks by Type:")
        by_type = defaultdict(list)
        for b in threshold_blocks:
            st = b.get('structure_type', 'unknown')
            conf = b.get('confidence', 0)
            thresh = b.get('required_threshold', 0)
            by_type[st].append((conf, thresh))
        
        for st, vals in sorted(by_type.items(), key=lambda x: -len(x[1])):
            avg_conf = sum(v[0] for v in vals) / len(vals)
            avg_thresh = sum(v[1] for v in vals) / len(vals)
            print(f"  {st}: {len(vals)} blocks (avg conf: {avg_conf:.3f}, threshold: {avg_thresh:.2f})")
    
    return executed, blocked

if __name__ == '__main__':
    log_path = sys.argv[1] if len(sys.argv) > 1 else 'logs/live_mt5_20260125_230538.json'
    analyze_log(log_path)
