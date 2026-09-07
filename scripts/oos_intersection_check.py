import csv, os, sys
from datetime import datetime

sys.path.insert(0, 'research/backtest')
import run_h1

bars = run_h1.load_dataset('research/data/eurusd_1h.csv')
start = datetime(2024, 1, 1)
end = datetime(2025, 5, 13, 23, 59, 59)
oos_bars = [b for b in bars if start <= b['time'] <= end]
print(f'OOS bars: {len(oos_bars)}')

trades = run_h1.run_backtest(oos_bars)
print(f'Trades: {len(trades)}')

oos_dir = 'research/data/raw/OOS_FROZEN'
zero_vol_times = set()
for fname in sorted(os.listdir(oos_dir)):
    if not fname.endswith('.csv'):
        continue
    with open(os.path.join(oos_dir, fname), newline='') as f:
        for row in csv.DictReader(f):
            if float(row['volume']) == 0:
                d = datetime.strptime(row['timestamp_utc'], '%Y-%m-%d %H:%M:%S')
                if d.weekday() == 5:
                    continue
                if d.weekday() == 6 and d.hour < 22:
                    continue
                zero_vol_times.add(row['timestamp_utc'])

print(f'Zero-vol bars (post-strip): {len(zero_vol_times)}')

entry_times = set()
exit_times = set()
for t in trades:
    entry_times.add(oos_bars[t.entry_idx]['time'].strftime('%Y-%m-%d %H:%M:%S'))
    exit_times.add(oos_bars[t.exit_idx]['time'].strftime('%Y-%m-%d %H:%M:%S'))

entry_intersection = entry_times & zero_vol_times
exit_intersection = exit_times & zero_vol_times

print(f'Entry timestamps in zero-vol: {len(entry_intersection)}')
print(f'Exit timestamps in zero-vol: {len(exit_intersection)}')
if entry_intersection:
    print(f'  Entry times: {sorted(entry_intersection)[:5]}...')
if exit_intersection:
    print(f'  Exit times: {sorted(exit_intersection)[:5]}...')

asian_entries = [t for t in trades if oos_bars[t.entry_idx]['time'].hour in {22,23,0,1,2,3,4,5,6}]
print(f'Trade entries during Asian session (22-07): {len(asian_entries)} out of {len(trades)}')

# Print all trade entry/exit times for verification
print()
print('All OOS trades (entry -> exit):')
for i, t in enumerate(trades, 1):
    entry_t = oos_bars[t.entry_idx]['time'].strftime('%Y-%m-%d %H:%M')
    exit_t = oos_bars[t.exit_idx]['time'].strftime('%Y-%m-%d %H:%M')
    is_zero_entry = oos_bars[t.entry_idx]['time'].strftime('%Y-%m-%d %H:%M:%S') in zero_vol_times
    is_zero_exit = oos_bars[t.exit_idx]['time'].strftime('%Y-%m-%d %H:%M:%S') in zero_vol_times
    zero_flag = ' [ZERO-VOL]' if (is_zero_entry or is_zero_exit) else ''
    print(f'  {i:2d}. {entry_t} -> {exit_t}  {t.side:5s} {t.exit_reason:8s} {t.pips:+6.1f}p{zero_flag}')
