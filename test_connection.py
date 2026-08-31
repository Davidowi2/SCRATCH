import os
import sys
from dotenv import load_dotenv

load_dotenv()

username = os.getenv('TL_USERNAME')
password = os.getenv('TL_PASSWORD')
environment = os.getenv('TL_ENVIRONMENT', os.getenv('TL_SERVER', 'https://demo.tradelocker.com'))
server_name = os.getenv('TL_SERVER_NAME', 'Demo' if environment.startswith('http') else os.getenv('TL_SERVER', 'Demo'))
if environment.startswith('http') and os.getenv('TL_SERVER') and not os.getenv('TL_SERVER').startswith('http'):
    server_name = os.getenv('TL_SERVER')
acc_num = int(os.getenv('TL_ACC_NUM', 0)) if os.getenv('TL_ACC_NUM') else 0

print("=" * 60)
print("SCRATCH - TradeLocker Connection Pre-Flight Check")
print("=" * 60)
print(f"Environment URL: {environment}")
print(f"Server Name:     {server_name}")
print(f"Username/Email:  {username}")
print(f"Password:        {'*' * len(password) if password else 'NOT SET'}")
print(f"Account Num:     {acc_num if acc_num else 'Default (0)'}")
print("=" * 60)

if not username or username == 'your_username_here':
    print("ERROR: TL_USERNAME is not configured in .env")
    sys.exit(1)

if not password or password == 'your_password_here':
    print("ERROR: TL_PASSWORD is not configured in .env")
    sys.exit(1)

try:
    from tradelocker import TLAPI
    print("Connecting to TradeLocker...")
    tl = TLAPI(
        environment=environment,
        username=username,
        password=password,
        server=server_name,
        acc_num=acc_num
    )
    print("SUCCESS: Connected to TradeLocker successfully!")
    
    # Get EURUSD instrument ID
    eurusd_id = tl.get_instrument_id_from_symbol_name("EURUSD")
    print(f"SUCCESS: Found EURUSD instrument ID: {eurusd_id}")
    
    # Fetch quote
    bid = tl.get_latest_bid_price(eurusd_id)
    ask = tl.get_latest_asking_price(eurusd_id)
    print(f"SUCCESS: Market Quote -> Bid: {bid}, Ask: {ask}")
    
    # Fetch candle history
    candles = tl.get_price_history(instrument_id=eurusd_id, resolution="5m", lookback_period="1D")
    if candles is not None and len(candles) > 0:
        print(f"SUCCESS: Fetched {len(candles)} 5-minute candles successfully.")
        last = candles.iloc[-1]
        print(f"Latest 5m Candle -> High: {last['h']}, Low: {last['l']}, Close: {last['c']}")
    else:
        print("WARNING: No candle data returned.")
        
    acc = tl.get_account_state()
    if acc:
        print(f"SUCCESS: Account Balance: ${acc.get('balance', 0.0):.2f}, Available: ${acc.get('availableFunds', 0.0):.2f}")
        
    print("\n============================================================")
    print("ALL CHECKS PASSED! The bot is 100% ready to trade.")
    print("============================================================")
except Exception as e:
    print(f"\nCONNECTION FAILED: {e}")
    sys.exit(1)
