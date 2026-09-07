"""
Test kill switch and verify TLAPI acc_num requirements.
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from live_h1 import H001LiveAdapter

print("=" * 60)
print("KILL SWITCH TEST")
print("=" * 60)

adapter = H001LiveAdapter()

# Create a test bar that would normally trigger a signal
# Use a bar from the last signal we saw
test_bar = {
    "time": datetime(2025, 5, 12, 1, 0, 0),
    "open": 1.12000,
    "high": 1.12100,
    "low": 1.11900,
    "close": 1.11800,
    "volume": 60000000000,
}

print(f"Adapter created. is_killed = {adapter.is_killed}")

# Try to check signal — should work
signal = adapter.check_signal(test_bar)
print(f"Signal before kill: {signal}")

# Activate kill switch
adapter.kill_switch()
print(f"Kill switch activated. is_killed = {adapter.is_killed}")

# Try to check signal — should still check but log kill
signal_after = adapter.check_signal(test_bar)
print(f"Signal after kill: {signal_after}")

print()
print("=" * 60)
print("TLAPI acc_num REQUIREMENT CHECK")
print("=" * 60)

# Check TradeLocker TLAPI constructor to see if acc_num is required
try:
    from tradelocker import TLAPI
    import inspect
    sig = inspect.signature(TLAPI.__init__)
    print(f"TLAPI.__init__ signature: {sig}")
    for name, param in sig.parameters.items():
        print(f"  {name}: default={param.default}, kind={param.kind}")
except Exception as e:
    print(f"Could not inspect TLAPI: {e}")

print()
print("=" * 60)
print("KILL SWITCH TEST COMPLETE")
print("=" * 60)
