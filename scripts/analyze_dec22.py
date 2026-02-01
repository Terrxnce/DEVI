import json

# Load trade journal
trades = json.load(open('logs/trade_journal/trade_journal_20251222.json'))

# Load log file (JSONL format)
lines = open('logs/live_mt5_20251222_005147.json', 'r').readlines()
data = [json.loads(l) for l in lines]

# HTF bias data
htf = [x for x in data if x.get('message') == 'htf_bias_applied']

# Position limit blocks
pos_blocks = [x for x in data if x.get('message') == 'position_limit_blocked']

# Conflict detections
conflicts = [x for x in data if x.get('message') == 'signal_conflict_detected']

# SL/TP validation failures
sl_tp_fails = [x for x in data if x.get('message') == 'order_validation_failed']

print('=' * 60)
print('  DECEMBER 22 DEEP ANALYSIS')
print('=' * 60)

print('\n## SESSION STATISTICS')
wins = [t for t in trades if t['outcome'] == 'win']
losses = [t for t in trades if t['outcome'] == 'loss']
print(f'  Total trades executed: {len(trades)}')
print(f'  Wins: {len(wins)}')
print(f'  Losses: {len(losses)}')
print(f'  Win Rate: {len(wins)/len(trades)*100:.1f}%')

print('\n## GUARD ACTIVATIONS')
print(f'  HTF bias applications: {len(htf)}')
print(f'  Position limit blocks: {len(pos_blocks)}')
print(f'  Conflict detections: {len(conflicts)}')
print(f'  SL/TP validation failures: {len(sl_tp_fails)}')

print('\n## HTF BIAS BREAKDOWN')
aligned = [x for x in htf if x.get('alignment') == 'aligned']
counter = [x for x in htf if x.get('alignment') == 'counter']
neutral = [x for x in htf if x.get('alignment') == 'neutral']
print(f'  Aligned: {len(aligned)} ({len(aligned)/len(htf)*100:.1f}%)')
print(f'  Counter: {len(counter)} ({len(counter)/len(htf)*100:.1f}%)')
print(f'  Neutral: {len(neutral)} ({len(neutral)/len(htf)*100:.1f}%)')

print('\n## P&L SUMMARY')
total_pnl = sum(t['pnl_usd'] for t in trades)
wins_pnl = sum(t['pnl_usd'] for t in wins)
losses_pnl = sum(t['pnl_usd'] for t in losses)
print(f'  Total P&L: ${total_pnl:.2f}')
print(f'  Wins P&L: ${wins_pnl:.2f}')
print(f'  Losses P&L: ${losses_pnl:.2f}')

print('\n## STRUCTURE PERFORMANCE')
structures = {}
for t in trades:
    s = t['structure_type']
    if s not in structures:
        structures[s] = {'wins': 0, 'losses': 0, 'pnl': 0}
    if t['outcome'] == 'win':
        structures[s]['wins'] += 1
    else:
        structures[s]['losses'] += 1
    structures[s]['pnl'] += t['pnl_usd']
for s, d in sorted(structures.items(), key=lambda x: x[1]['pnl'], reverse=True):
    total = d['wins'] + d['losses']
    wr = d['wins']/total*100 if total > 0 else 0
    print(f'  {s}: {d["wins"]}W/{d["losses"]}L ({wr:.0f}%) = ${d["pnl"]:.2f}')

print('\n## SYMBOL PERFORMANCE')
symbols = {}
for t in trades:
    s = t['symbol']
    if s not in symbols:
        symbols[s] = {'wins': 0, 'losses': 0, 'pnl': 0}
    if t['outcome'] == 'win':
        symbols[s]['wins'] += 1
    else:
        symbols[s]['losses'] += 1
    symbols[s]['pnl'] += t['pnl_usd']
for s, d in sorted(symbols.items(), key=lambda x: x[1]['pnl'], reverse=True):
    total = d['wins'] + d['losses']
    wr = d['wins']/total*100 if total > 0 else 0
    print(f'  {s}: {d["wins"]}W/{d["losses"]}L ({wr:.0f}%) = ${d["pnl"]:.2f}')

# Map tickets to HTF bias info
print('\n## TRADE-BY-TRADE HTF ANALYSIS')
print('-' * 80)

# Build a lookup of HTF bias by symbol+direction+approximate time
for t in trades:
    ticket = t['ticket']
    symbol = t['symbol']
    direction = t['direction']
    outcome = t['outcome']
    pnl = t['pnl_usd']
    structure = t['structure_type']
    
    # Find matching HTF bias entry (closest before trade)
    entry_time = t['entry_time']
    matching_htf = None
    for h in htf:
        if h['symbol'] == symbol and h['direction'] == direction:
            # Check if timestamp is close
            if h['timestamp'] <= entry_time:
                matching_htf = h
    
    if matching_htf:
        alignment = matching_htf.get('alignment', 'unknown')
        bias = matching_htf.get('htf_bias', 'unknown')
        orig_score = matching_htf.get('original_score', 0)
        adj_score = matching_htf.get('adjusted_score', 0)
        modifier = matching_htf.get('score_modifier', 0)
    else:
        alignment = 'unknown'
        bias = 'unknown'
        orig_score = 0
        adj_score = 0
        modifier = 0
    
    outcome_str = 'WIN ' if outcome == 'win' else 'LOSS'
    align_str = alignment.upper()
    print(f'{outcome_str} | {symbol:6} {direction:4} | {structure:20} | HTF:{bias:8} | Align:{align_str:8} | {orig_score:.2f}->{adj_score:.2f} | ${pnl:>8.2f}')

print('-' * 80)

# Analyze counter-trend performance
print('\n## COUNTER-TREND ANALYSIS')
counter_trades = []
for t in trades:
    symbol = t['symbol']
    direction = t['direction']
    for h in htf:
        if h['symbol'] == symbol and h['direction'] == direction:
            if h.get('alignment') == 'counter':
                counter_trades.append((t, h))
                break

if counter_trades:
    counter_wins = [ct for ct in counter_trades if ct[0]['outcome'] == 'win']
    counter_losses = [ct for ct in counter_trades if ct[0]['outcome'] == 'loss']
    counter_pnl = sum(ct[0]['pnl_usd'] for ct in counter_trades)
    print(f'  Counter-trend trades: {len(counter_trades)}')
    print(f'  Counter wins: {len(counter_wins)}')
    print(f'  Counter losses: {len(counter_losses)}')
    print(f'  Counter P&L: ${counter_pnl:.2f}')
    print(f'  Counter win rate: {len(counter_wins)/len(counter_trades)*100:.1f}%')
    print('\n  Counter-trend trade details:')
    for ct, h in counter_trades:
        print(f'    {ct["symbol"]} {ct["direction"]} | {ct["outcome"]} | ${ct["pnl_usd"]:.2f} | HTF was {h["htf_bias"]}')
else:
    print('  No counter-trend trades found in executed trades')

# Analyze aligned performance
print('\n## ALIGNED TRADE ANALYSIS')
aligned_trades = []
for t in trades:
    symbol = t['symbol']
    direction = t['direction']
    for h in htf:
        if h['symbol'] == symbol and h['direction'] == direction:
            if h.get('alignment') == 'aligned':
                aligned_trades.append((t, h))
                break

if aligned_trades:
    aligned_wins = [at for at in aligned_trades if at[0]['outcome'] == 'win']
    aligned_losses = [at for at in aligned_trades if at[0]['outcome'] == 'loss']
    aligned_pnl = sum(at[0]['pnl_usd'] for at in aligned_trades)
    print(f'  Aligned trades: {len(aligned_trades)}')
    print(f'  Aligned wins: {len(aligned_wins)}')
    print(f'  Aligned losses: {len(aligned_losses)}')
    print(f'  Aligned P&L: ${aligned_pnl:.2f}')
    print(f'  Aligned win rate: {len(aligned_wins)/len(aligned_trades)*100:.1f}%')

print('\n' + '=' * 60)
