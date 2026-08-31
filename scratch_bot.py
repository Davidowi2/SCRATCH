"""
SCRATCH - TradeLocker 5-Minute Breakout Scalping Bot

A fully automated scalping bot that trades EURUSD using a breakout strategy
on 5-minute candles with strict risk management and exit rules.

Author: Built with Kiro AI
Version: 1.0.0
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

try:
    from tradelocker import TLAPI
except ImportError:
    print("ERROR: tradelocker library not found. Install with: pip install tradelocker")
    exit(1)

# Add database directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database.db_manager import DatabaseManager
except ImportError:
    print("ERROR: Could not import DatabaseManager. Ensure database/db_manager.py exists.")
    exit(1)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scratch_bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class ScalpingBot:
    """
    TradeLocker scalping bot implementing a 5-minute breakout strategy.
    
    Strategy:
    - Monitors 5-minute candles on EURUSD
    - Enters BUY when price breaks above previous candle's high
    - Enters SELL when price breaks below previous candle's low
    - Uses 5-pip stop-loss and 10-pip take-profit
    - Implements stalling exit (5 seconds, <2 pips profit)
    - Maximum hold time of 15 seconds
    """
    
    def __init__(self):
        """Initialize the scalping bot with configuration."""
        self.tl: Optional[TLAPI] = None
        self.instrument_id: Optional[int] = None
        self.instrument_symbol: str = "EURUSD"
        
        # Database manager
        self.db = DatabaseManager()
        
        # Position state
        self.position_open: bool = False
        self.current_position: Optional[Dict[str, Any]] = None
        self.current_trade_id: Optional[int] = None  # Database trade ID
        self.entry_time: Optional[float] = None
        self.entry_price: Optional[float] = None
        self.position_type: Optional[str] = None  # "BUY" or "SELL"
        
        # Candle data
        self.previous_high: Optional[float] = None
        self.previous_low: Optional[float] = None
        self.current_candle_start: Optional[datetime] = None
        self.last_candle_time: Optional[datetime] = None
        
        # Configuration
        self.position_size: float = 0.06  # Exactly 0.06 lots
        self.stop_loss_pips: int = 5
        self.take_profit_pips: int = 10
        self.max_spread_pips: float = 2.0
        self.stalling_time_seconds: int = 5
        self.stalling_min_profit_pips: float = 2.0
        self.max_hold_time_seconds: int = 15
        self.pip_value: float = 0.0001  # For EURUSD
        
        # API settings
        self.api_retry_attempts: int = 3
        self.api_retry_delay: int = 5
        self.position_check_interval: float = 0.5
        self.api_call_delay: float = 0.1
        
        # State flags
        self.inside_range_after_gap: bool = False
        self.gap_direction: Optional[str] = None  # "UP" or "DOWN"
        
        logger.info("SCRATCH Bot initialized")
        logger.info(f"Database initialized at: {self.db.db_path}")
    
    def connect(self) -> bool:
        """
        Authenticate with TradeLocker API using environment variables.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        username = os.getenv('TL_USERNAME')
        password = os.getenv('TL_PASSWORD')
        server = os.getenv('TL_SERVER')
        
        if not all([username, password, server]):
            logger.error("Missing required environment variables: TL_USERNAME, TL_PASSWORD, TL_SERVER")
            return False
        
        logger.info(f"Attempting to connect to TradeLocker at {server}")
        
        for attempt in range(1, self.api_retry_attempts + 1):
            try:
                self.tl = TLAPI(
                    environment=server,
                    username=username,
                    password=password
                )
                logger.info(f"Successfully connected to TradeLocker (attempt {attempt})")
                return True
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {e}")
                if attempt < self.api_retry_attempts:
                    logger.info(f"Retrying in {self.api_retry_delay} seconds...")
                    time.sleep(self.api_retry_delay)
        
        logger.error("All connection attempts failed")
        return False
    
    def get_instrument(self) -> bool:
        """
        Retrieve the instrument ID for EURUSD.
        
        Returns:
            bool: True if instrument found, False otherwise
        """
        try:
            logger.info(f"Fetching instrument ID for {self.instrument_symbol}")
            time.sleep(self.api_call_delay)
            
            # Get instrument ID from symbol name
            self.instrument_id = self.tl.get_instrument_id_from_symbol_name(self.instrument_symbol)
            
            if self.instrument_id:
                logger.info(f"Instrument ID for {self.instrument_symbol}: {self.instrument_id}")
                return True
            else:
                logger.error(f"Could not find instrument ID for {self.instrument_symbol}")
                return False
        except Exception as e:
            logger.error(f"Error fetching instrument: {e}")
            return False
    
    def get_last_candle(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get the previous 5-minute candle's high and low prices.
        
        Returns:
            Tuple[Optional[float], Optional[float]]: (high, low) or (None, None) on error
        """
        try:
            time.sleep(self.api_call_delay)
            
            # Fetch recent 5-minute candles (get at least 2 candles)
            candles = self.tl.get_price_history(
                instrument_id=self.instrument_id,
                resolution="5m",
                lookback_period=10  # Get last 10 candles to be safe
            )
            
            if not candles or len(candles) < 2:
                logger.warning("Insufficient candle data received")
                return None, None
            
            # Get the previous candle (second to last)
            previous_candle = candles[-2]
            
            high = float(previous_candle['high'])
            low = float(previous_candle['low'])
            
            logger.info(f"Previous candle: High={high:.5f}, Low={low:.5f}")
            
            return high, low
        except Exception as e:
            logger.error(f"Error fetching candle data: {e}")
            return None, None
    
    def get_current_price(self) -> Optional[Dict[str, float]]:
        """
        Get the current bid and ask prices for EURUSD.
        
        Returns:
            Optional[Dict[str, float]]: {"bid": float, "ask": float} or None on error
        """
        try:
            time.sleep(self.api_call_delay)
            
            # Get current quote
            quote = self.tl.get_quote(instrument_id=self.instrument_id)
            
            if quote:
                bid = float(quote.get('bid', 0))
                ask = float(quote.get('ask', 0))
                return {"bid": bid, "ask": ask}
            else:
                logger.warning("No quote data received")
                return None
        except Exception as e:
            logger.error(f"Error fetching current price: {e}")
            return None
    
    def calculate_spread_pips(self, bid: float, ask: float) -> float:
        """
        Calculate the spread in pips.
        
        Args:
            bid: Current bid price
            ask: Current ask price
        
        Returns:
            float: Spread in pips
        """
        return (ask - bid) / self.pip_value
    
    def calculate_profit_pips(self, entry_price: float, current_price: float, position_type: str) -> float:
        """
        Calculate profit/loss in pips.
        
        Args:
            entry_price: Entry price of the position
            current_price: Current price
            position_type: "BUY" or "SELL"
        
        Returns:
            float: Profit/loss in pips (positive = profit, negative = loss)
        """
        if position_type == "BUY":
            return (current_price - entry_price) / self.pip_value
        else:  # SELL
            return (entry_price - current_price) / self.pip_value
    
    def check_spread(self) -> bool:
        """
        Check if the current spread is acceptable (<2 pips).
        
        Returns:
            bool: True if spread is acceptable, False otherwise
        """
        price_data = self.get_current_price()
        if not price_data:
            return False
        
        spread = self.calculate_spread_pips(price_data['bid'], price_data['ask'])
        
        if spread > self.max_spread_pips:
            logger.warning(f"Spread too wide: {spread:.2f} pips (max: {self.max_spread_pips})")
            return False
        
        return True
    
    def enter_buy(self, entry_price: float) -> bool:
        """
        Execute a BUY market order with stop-loss and take-profit.
        
        Args:
            entry_price: Current price to enter at
        
        Returns:
            bool: True if order placed successfully, False otherwise
        """
        try:
            logger.info(f"ENTERING BUY at {entry_price:.5f}")
            
            # Calculate SL and TP
            stop_loss = entry_price - (self.stop_loss_pips * self.pip_value)
            take_profit = entry_price + (self.take_profit_pips * self.pip_value)
            
            time.sleep(self.api_call_delay)
            
            # Place market order
            order = self.tl.create_market_order(
                instrument_id=self.instrument_id,
                quantity=self.position_size,
                side="buy",
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if order:
                self.position_open = True
                self.current_position = order
                self.entry_time = time.time()
                self.entry_price = entry_price
                self.position_type = "BUY"
                
                # Log trade to database
                self.current_trade_id = self.db.insert_trade(
                    entry_time=datetime.now(),
                    entry_price=entry_price,
                    side="BUY",
                    position_size=self.position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                logger.info(f"BUY ORDER PLACED: Entry={entry_price:.5f}, SL={stop_loss:.5f}, TP={take_profit:.5f}")
                logger.info(f"Trade ID: {self.current_trade_id}")
                return True
            else:
                logger.error("Failed to place BUY order - no response from API")
                return False
        except Exception as e:
            logger.error(f"Error placing BUY order: {e}")
            return False
    
    def enter_sell(self, entry_price: float) -> bool:
        """
        Execute a SELL market order with stop-loss and take-profit.
        
        Args:
            entry_price: Current price to enter at
        
        Returns:
            bool: True if order placed successfully, False otherwise
        """
        try:
            logger.info(f"ENTERING SELL at {entry_price:.5f}")
            
            # Calculate SL and TP
            stop_loss = entry_price + (self.stop_loss_pips * self.pip_value)
            take_profit = entry_price - (self.take_profit_pips * self.pip_value)
            
            time.sleep(self.api_call_delay)
            
            # Place market order
            order = self.tl.create_market_order(
                instrument_id=self.instrument_id,
                quantity=self.position_size,
                side="sell",
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if order:
                self.position_open = True
                self.current_position = order
                self.entry_time = time.time()
                self.entry_price = entry_price
                self.position_type = "SELL"
                
                # Log trade to database
                self.current_trade_id = self.db.insert_trade(
                    entry_time=datetime.now(),
                    entry_price=entry_price,
                    side="SELL",
                    position_size=self.position_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                logger.info(f"SELL ORDER PLACED: Entry={entry_price:.5f}, SL={stop_loss:.5f}, TP={take_profit:.5f}")
                logger.info(f"Trade ID: {self.current_trade_id}")
                return True
            else:
                logger.error("Failed to place SELL order - no response from API")
                return False
        except Exception as e:
            logger.error(f"Error placing SELL order: {e}")
            return False
    
    def close_position(self, reason: str) -> bool:
        """
        Close the current open position.
        
        Args:
            reason: Reason for closing the position
        
        Returns:
            bool: True if position closed successfully, False otherwise
        """
        try:
            if not self.position_open or not self.current_position:
                logger.warning("No position to close")
                return False
            
            time.sleep(self.api_call_delay)
            
            # Get current price for P&L calculation
            price_data = self.get_current_price()
            if price_data:
                exit_price = price_data['bid'] if self.position_type == "BUY" else price_data['ask']
                profit_pips = self.calculate_profit_pips(self.entry_price, exit_price, self.position_type)
                
                # Calculate profit in USD (approximate: $10 per pip for 0.06 lots)
                profit_usd = profit_pips * 10 * self.position_size / 0.01
            else:
                exit_price = None
                profit_pips = None
                profit_usd = None
            
            # Close the position
            position_id = self.current_position.get('id') or self.current_position.get('orderId')
            
            result = self.tl.close_position(position_id)
            
            # Calculate hold time
            hold_time = time.time() - self.entry_time if self.entry_time else 0
            
            # Update database
            if self.current_trade_id and exit_price is not None:
                self.db.update_trade(
                    trade_id=self.current_trade_id,
                    exit_time=datetime.now(),
                    exit_price=exit_price,
                    pips=profit_pips if profit_pips else 0,
                    profit_usd=profit_usd if profit_usd else 0,
                    exit_reason=reason,
                    hold_time_seconds=hold_time
                )
            
            # Log the trade result
            logger.info(f"=" * 60)
            logger.info(f"POSITION CLOSED - {reason}")
            logger.info(f"Type: {self.position_type}")
            logger.info(f"Entry: {self.entry_price:.5f}")
            logger.info(f"Exit: {exit_price:.5f if exit_price else 'N/A'}")
            logger.info(f"Profit/Loss: {profit_pips:.2f} pips" if profit_pips else "P&L: N/A")
            logger.info(f"Profit/Loss USD: ${profit_usd:.2f}" if profit_usd else "P&L USD: N/A")
            logger.info(f"Hold Time: {hold_time:.2f} seconds")
            logger.info(f"=" * 60)
            
            # Reset state
            self.position_open = False
            self.current_position = None
            self.current_trade_id = None
            self.entry_time = None
            self.entry_price = None
            self.position_type = None
            
            return True
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            # Reset state even on error to avoid stuck state
            self.position_open = False
            self.current_position = None
            self.current_trade_id = None
            self.entry_time = None
            self.entry_price = None
            self.position_type = None
            return False
    
    def check_exit_conditions(self) -> Optional[str]:
        """
        Check all exit conditions in priority order.
        
        Returns:
            Optional[str]: Exit reason if condition met, None otherwise
        """
        if not self.position_open or not self.entry_time:
            return None
        
        # Get current price
        price_data = self.get_current_price()
        if not price_data:
            logger.warning("Could not fetch price for exit check")
            return None
        
        current_price = price_data['bid'] if self.position_type == "BUY" else price_data['ask']
        profit_pips = self.calculate_profit_pips(self.entry_price, current_price, self.position_type)
        elapsed_time = time.time() - self.entry_time
        
        # PRIORITY 1: Check Stop-Loss (5 pips loss)
        if profit_pips <= -self.stop_loss_pips:
            return "STOP-LOSS HIT"
        
        # PRIORITY 2: Check Take-Profit (10 pips profit)
        if profit_pips >= self.take_profit_pips:
            return "TAKE-PROFIT HIT"
        
        # PRIORITY 3: Check Stalling Exit (5 seconds, <2 pips profit)
        if elapsed_time >= self.stalling_time_seconds and profit_pips < self.stalling_min_profit_pips:
            return f"STALLING EXIT (5s elapsed, only {profit_pips:.2f} pips profit)"
        
        # PRIORITY 4: Check Maximum Hold Time (15 seconds)
        if elapsed_time >= self.max_hold_time_seconds:
            return f"MAX HOLD TIME (15s elapsed, {profit_pips:.2f} pips profit)"
        
        return None
    
    def monitor_position(self) -> None:
        """
        Monitor the open position and check exit conditions continuously.
        """
        while self.position_open:
            try:
                exit_reason = self.check_exit_conditions()
                
                if exit_reason:
                    self.close_position(exit_reason)
                    break
                
                time.sleep(self.position_check_interval)
            except Exception as e:
                logger.error(f"Error monitoring position: {e}")
                time.sleep(1)
    
    def check_entry_conditions(self) -> Optional[str]:
        """
        Check if entry conditions are met (breakout detection).
        
        Returns:
            Optional[str]: "BUY" or "SELL" if entry condition met, None otherwise
        """
        if self.position_open:
            return None
        
        if self.previous_high is None or self.previous_low is None:
            return None
        
        # Get current price
        price_data = self.get_current_price()
        if not price_data:
            return None
        
        current_ask = price_data['ask']
        current_bid = price_data['bid']
        
        # Check if we're handling a gap
        if self.gap_direction:
            # For upward gap, wait for price to come back inside range
            if self.gap_direction == "UP":
                if current_bid <= self.previous_high:
                    self.inside_range_after_gap = True
                    logger.info("Price returned inside range after upward gap")
                
                # Now wait for breakout UP again
                if self.inside_range_after_gap and current_ask > self.previous_high:
                    logger.info(f"Breakout UP after gap: {current_ask:.5f} > {self.previous_high:.5f}")
                    self.gap_direction = None
                    self.inside_range_after_gap = False
                    return "BUY"
            
            # For downward gap, wait for price to come back inside range
            elif self.gap_direction == "DOWN":
                if current_ask >= self.previous_low:
                    self.inside_range_after_gap = True
                    logger.info("Price returned inside range after downward gap")
                
                # Now wait for breakout DOWN again
                if self.inside_range_after_gap and current_bid < self.previous_low:
                    logger.info(f"Breakout DOWN after gap: {current_bid:.5f} < {self.previous_low:.5f}")
                    self.gap_direction = None
                    self.inside_range_after_gap = False
                    return "SELL"
            
            return None
        
        # Check for breakout above previous high (BUY signal)
        if current_ask > self.previous_high:
            logger.info(f"Breakout UP detected: {current_ask:.5f} > {self.previous_high:.5f}")
            return "BUY"
        
        # Check for breakout below previous low (SELL signal)
        if current_bid < self.previous_low:
            logger.info(f"Breakout DOWN detected: {current_bid:.5f} < {self.previous_low:.5f}")
            return "SELL"
        
        return None
    
    def detect_new_candle(self) -> bool:
        """
        Detect if a new 5-minute candle has started.
        
        Returns:
            bool: True if new candle detected, False otherwise
        """
        current_time = datetime.utcnow()
        
        # Calculate the start of the current 5-minute candle
        minutes = (current_time.minute // 5) * 5
        candle_start = current_time.replace(minute=minutes, second=0, microsecond=0)
        
        # Check if this is a new candle
        if self.current_candle_start is None or candle_start > self.current_candle_start:
            if self.current_candle_start is not None:
                logger.info(f"NEW CANDLE DETECTED at {candle_start}")
            
            self.current_candle_start = candle_start
            return True
        
        return False
    
    def handle_new_candle(self) -> None:
        """
        Handle the start of a new candle: update reference high/low.
        """
        logger.info("Processing new candle...")
        
        # Get the previous candle's high and low
        high, low = self.get_last_candle()
        
        if high is not None and low is not None:
            self.previous_high = high
            self.previous_low = low
            
            # Check for gap
            price_data = self.get_current_price()
            if price_data:
                current_price = price_data['ask']
                
                # Check if opened above previous high (upward gap)
                if current_price > self.previous_high:
                    logger.warning(f"UPWARD GAP DETECTED: Price {current_price:.5f} > Previous High {self.previous_high:.5f}")
                    self.gap_direction = "UP"
                    self.inside_range_after_gap = False
                
                # Check if opened below previous low (downward gap)
                elif current_price < self.previous_low:
                    logger.warning(f"DOWNWARD GAP DETECTED: Price {current_price:.5f} < Previous Low {self.previous_low:.5f}")
                    self.gap_direction = "DOWN"
                    self.inside_range_after_gap = False
                
                else:
                    # No gap, normal operation
                    self.gap_direction = None
                    self.inside_range_after_gap = False
            
            logger.info(f"Reference set - High: {self.previous_high:.5f}, Low: {self.previous_low:.5f}")
        else:
            logger.error("Failed to get previous candle data")
    
    def run(self) -> None:
        """
        Main bot loop.
        """
        logger.info("=" * 60)
        logger.info("SCRATCH BOT STARTING")
        logger.info("=" * 60)
        
        # Connect to TradeLocker
        if not self.connect():
            logger.error("Failed to connect to TradeLocker. Exiting.")
            return
        
        # Get instrument
        if not self.get_instrument():
            logger.error("Failed to get instrument. Exiting.")
            return
        
        # Initialize with first candle
        logger.info("Initializing with current candle data...")
        self.detect_new_candle()
        self.handle_new_candle()
        
        logger.info("=" * 60)
        logger.info("BOT IS NOW LIVE - MONITORING EURUSD")
        logger.info("=" * 60)
        
        consecutive_errors = 0
        max_consecutive_errors = 3
        heartbeat_counter = 0
        
        # Main loop
        while True:
            try:
                # Update heartbeat every 10 iterations (~5 seconds)
                heartbeat_counter += 1
                if heartbeat_counter >= 10:
                    self.db.update_heartbeat()
                    heartbeat_counter = 0
                
                # Check for new candle
                if self.detect_new_candle() and not self.position_open:
                    self.handle_new_candle()
                
                # If position is open, monitor it
                if self.position_open:
                    self.monitor_position()
                    continue
                
                # Check entry conditions
                signal = self.check_entry_conditions()
                
                if signal:
                    # Check spread before entering
                    if not self.check_spread():
                        logger.warning("Spread too wide, skipping entry")
                        time.sleep(1)
                        continue
                    
                    # Get entry price
                    price_data = self.get_current_price()
                    if not price_data:
                        logger.warning("Could not get price for entry")
                        time.sleep(1)
                        continue
                    
                    # Enter trade
                    if signal == "BUY":
                        entry_price = price_data['ask']
                        success = self.enter_buy(entry_price)
                    else:  # SELL
                        entry_price = price_data['bid']
                        success = self.enter_sell(entry_price)
                    
                    if not success:
                        logger.error("Failed to enter trade, waiting for next candle")
                        # Wait for next candle after failed entry
                        time.sleep(60)
                
                # Reset error counter on successful iteration
                consecutive_errors = 0
                
                # Small delay between iterations
                time.sleep(0.5)
            
            except KeyboardInterrupt:
                logger.info("Bot stopped by user (KeyboardInterrupt)")
                break
            
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in main loop: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({max_consecutive_errors}). Stopping bot.")
                    break
                
                logger.info(f"Retrying in 5 seconds... (error {consecutive_errors}/{max_consecutive_errors})")
                time.sleep(5)
        
        logger.info("=" * 60)
        logger.info("SCRATCH BOT STOPPED")
        logger.info("=" * 60)


def main():
    """Entry point for the bot."""
    bot = ScalpingBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
