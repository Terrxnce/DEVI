import json
import glob

all_rejections = []
for f in glob.glob('logs/trade_journal/*.json'):
    try:
        trades = json.load(open(f))
        for t in trades:
            if t.get('structure_type') == 'rejection':
                all_rejections.append(t)
    except:
        pass

buy_wins = [t for t in all_rejections if t['outcome']=='win' and t['direction']=='BUY']
buy_losses = [t for t in all_rejections if t['outcome']=='loss' and t['direction']=='BUY']
sell_wins = [t for t in all_rejections if t['outcome']=='win' and t['direction']=='SELL']
sell_losses = [t for t in all_rejections if t['outcome']=='loss' and t['direction']=='SELL']

print('=== REJECTION TRADE ANALYSIS ===')
print(f'BUY WINS: {len(buy_wins)}, Total: ${sum(t.get("pnl_usd",0) for t in buy_wins):.0f}')
print(f'BUY LOSSES: {len(buy_losses)}, Total: ${sum(t.get("pnl_usd",0) for t in buy_losses):.0f}')
print(f'SELL WINS: {len(sell_wins)}, Total: ${sum(t.get("pnl_usd",0) for t in sell_wins):.0f}')
print(f'SELL LOSSES: {len(sell_losses)}, Total: ${sum(t.get("pnl_usd",0) for t in sell_losses):.0f}')
print()
print(f'BUY NET: ${sum(t.get("pnl_usd",0) for t in buy_wins) + sum(t.get("pnl_usd",0) for t in buy_losses):.0f}')
print(f'SELL NET: ${sum(t.get("pnl_usd",0) for t in sell_wins) + sum(t.get("pnl_usd",0) for t in sell_losses):.0f}')

print()
print('=== PROFIT IMPACT OF FIXES ===')
print()

# Fix 3: BUY rejection threshold raised to 0.85
# We don't have confidence in journal, but rejection scores are typically 0.60-0.95
# Estimate: ~50% of BUY rejections would be blocked (those below 0.85)
# Conservative estimate: block 50% of wins and 50% of losses
buy_win_total = sum(t.get("pnl_usd",0) for t in buy_wins)
buy_loss_total = sum(t.get("pnl_usd",0) for t in buy_losses)

print('Fix 3 (BUY threshold 0.85) - Estimated Impact:')
print(f'  If 50% of BUY trades blocked:')
print(f'    Lost profit: ${buy_win_total * 0.5:.0f}')
print(f'    Avoided losses: ${abs(buy_loss_total) * 0.5:.0f}')
print(f'    NET GAIN: ${(abs(buy_loss_total) * 0.5) - (buy_win_total * 0.5):.0f}')
print()

# Counter-trend rejection analysis (Fix 2 & 4)
counter_wins = [t for t in all_rejections if t.get('htf_alignment') == 'counter' and t['outcome'] == 'win']
counter_losses = [t for t in all_rejections if t.get('htf_alignment') == 'counter' and t['outcome'] == 'loss']

print('Fix 2 & 4 (Block counter-trend rejections) - Actual Data:')
print(f'  Counter-trend rejection WINS: {len(counter_wins)}, ${sum(t.get("pnl_usd",0) for t in counter_wins):.0f}')
print(f'  Counter-trend rejection LOSSES: {len(counter_losses)}, ${sum(t.get("pnl_usd",0) for t in counter_losses):.0f}')

# Note: Most historical data doesn't have htf_alignment field
trades_with_htf = [t for t in all_rejections if t.get('htf_alignment')]
print(f'  (Only {len(trades_with_htf)} trades have HTF alignment data)')
print()

print('=== OVERALL SUMMARY ===')
total_rejection_pnl = sum(t.get("pnl_usd",0) for t in all_rejections)
print(f'Total rejection P&L (all): ${total_rejection_pnl:.0f}')
print(f'If BUY rejections disabled entirely: ${sum(t.get("pnl_usd",0) for t in sell_wins) + sum(t.get("pnl_usd",0) for t in sell_losses):.0f}')
