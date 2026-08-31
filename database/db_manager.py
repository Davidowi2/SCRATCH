"""
Database Manager for SCRATCH Trading Bot

Handles all database operations including trade logging,
account balance tracking, and metrics calculation.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class DatabaseManager:
    """Manages SQLite database operations for trade logging and metrics."""
    
    def __init__(self, db_path: str = "database/trades.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize database schema
        self._initialize_schema()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _initialize_schema(self):
        """Create database tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_time TEXT,
                    exit_price REAL,
                    side TEXT CHECK(side IN ('BUY', 'SELL')) NOT NULL,
                    pips REAL,
                    profit_usd REAL,
                    exit_reason TEXT,
                    status TEXT CHECK(status IN ('open', 'closed', 'stopped')) NOT NULL,
                    position_size REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    hold_time_seconds REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Account balance snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    balance REAL NOT NULL,
                    equity REAL NOT NULL,
                    margin_used REAL,
                    margin_free REAL
                )
            """)
            
            # Bot status table (single row)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_running INTEGER DEFAULT 1,
                    last_heartbeat TEXT,
                    current_position_id INTEGER,
                    total_trades INTEGER DEFAULT 0,
                    session_start TEXT
                )
            """)
            
            # Initialize bot status if not exists
            cursor.execute("""
                INSERT OR IGNORE INTO bot_status (id, session_start, last_heartbeat)
                VALUES (1, datetime('now'), datetime('now'))
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_status 
                ON trades(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_entry_time 
                ON trades(entry_time DESC)
            """)
            
            conn.commit()
    
    def insert_trade(
        self,
        entry_time: datetime,
        entry_price: float,
        side: str,
        position_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> int:
        """
        Insert a new trade record when position is opened.
        
        Args:
            entry_time: Time of entry
            entry_price: Entry price
            side: "BUY" or "SELL"
            position_size: Position size in lots
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            int: Trade ID of inserted record
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trades (
                    entry_time, entry_price, side, position_size,
                    stop_loss, take_profit, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'open')
            """, (
                entry_time.isoformat(),
                entry_price,
                side,
                position_size,
                stop_loss,
                take_profit
            ))
            
            trade_id = cursor.lastrowid
            
            # Update bot status
            cursor.execute("""
                UPDATE bot_status 
                SET current_position_id = ?, total_trades = total_trades + 1
                WHERE id = 1
            """, (trade_id,))
            
            conn.commit()
            return trade_id
    
    def update_trade(
        self,
        trade_id: int,
        exit_time: datetime,
        exit_price: float,
        pips: float,
        profit_usd: float,
        exit_reason: str,
        hold_time_seconds: float
    ):
        """
        Update trade record when position is closed.
        
        Args:
            trade_id: ID of the trade to update
            exit_time: Time of exit
            exit_price: Exit price
            pips: Profit/loss in pips
            profit_usd: Profit/loss in USD
            exit_reason: Reason for exit (SL, TP, Stalling, MaxHold, Manual)
            hold_time_seconds: How long the position was held
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE trades
                SET exit_time = ?,
                    exit_price = ?,
                    pips = ?,
                    profit_usd = ?,
                    exit_reason = ?,
                    status = 'closed',
                    hold_time_seconds = ?
                WHERE id = ?
            """, (
                exit_time.isoformat(),
                exit_price,
                pips,
                profit_usd,
                exit_reason,
                hold_time_seconds,
                trade_id
            ))
            
            # Clear current position in bot status
            cursor.execute("""
                UPDATE bot_status 
                SET current_position_id = NULL
                WHERE id = 1
            """)
            
            conn.commit()
    
    def get_open_trade(self) -> Optional[Dict[str, Any]]:
        """
        Get the currently open trade if any.
        
        Returns:
            Optional[Dict]: Trade data or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM trades
                WHERE status = 'open'
                ORDER BY entry_time DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_last_closed_trade(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent closed trade.
        
        Returns:
            Optional[Dict]: Trade data or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM trades
                WHERE status = 'closed'
                ORDER BY exit_time DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent closed trades.
        
        Args:
            limit: Maximum number of trades to return
        
        Returns:
            List[Dict]: List of trade records
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM trades
                WHERE status = 'closed'
                ORDER BY exit_time DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Calculate trading metrics.
        
        Returns:
            Dict: Metrics including win rate, total P&L, etc.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total trades
            cursor.execute("""
                SELECT COUNT(*) as total_trades FROM trades WHERE status = 'closed'
            """)
            total_trades = cursor.fetchone()['total_trades']
            
            # Winning trades
            cursor.execute("""
                SELECT COUNT(*) as winning_trades FROM trades 
                WHERE status = 'closed' AND pips > 0
            """)
            winning_trades = cursor.fetchone()['winning_trades']
            
            # Losing trades
            cursor.execute("""
                SELECT COUNT(*) as losing_trades FROM trades 
                WHERE status = 'closed' AND pips <= 0
            """)
            losing_trades = cursor.fetchone()['losing_trades']
            
            # Total P&L
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(pips), 0) as total_pips,
                    COALESCE(SUM(profit_usd), 0) as total_profit_usd
                FROM trades WHERE status = 'closed'
            """)
            pnl_row = cursor.fetchone()
            
            # Average winning/losing trade
            cursor.execute("""
                SELECT AVG(pips) as avg_win_pips FROM trades 
                WHERE status = 'closed' AND pips > 0
            """)
            avg_win = cursor.fetchone()['avg_win_pips']
            
            cursor.execute("""
                SELECT AVG(pips) as avg_loss_pips FROM trades 
                WHERE status = 'closed' AND pips <= 0
            """)
            avg_loss = cursor.fetchone()['avg_loss_pips']
            
            # Average hold time
            cursor.execute("""
                SELECT AVG(hold_time_seconds) as avg_hold_time FROM trades 
                WHERE status = 'closed'
            """)
            avg_hold_time = cursor.fetchone()['avg_hold_time']
            
            # Exit reason breakdown
            cursor.execute("""
                SELECT exit_reason, COUNT(*) as count FROM trades 
                WHERE status = 'closed'
                GROUP BY exit_reason
            """)
            exit_reasons = {row['exit_reason']: row['count'] for row in cursor.fetchall()}
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 2),
                'total_pips': round(pnl_row['total_pips'], 2) if pnl_row['total_pips'] else 0,
                'total_profit_usd': round(pnl_row['total_profit_usd'], 2) if pnl_row['total_profit_usd'] else 0,
                'avg_win_pips': round(avg_win, 2) if avg_win else 0,
                'avg_loss_pips': round(avg_loss, 2) if avg_loss else 0,
                'avg_hold_time_seconds': round(avg_hold_time, 2) if avg_hold_time else 0,
                'exit_reasons': exit_reasons
            }
    
    def update_heartbeat(self):
        """Update bot heartbeat timestamp."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE bot_status 
                SET last_heartbeat = datetime('now')
                WHERE id = 1
            """)
            conn.commit()
    
    def get_bot_status(self) -> Dict[str, Any]:
        """
        Get current bot status.
        
        Returns:
            Dict: Bot status information
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bot_status WHERE id = 1")
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def save_account_snapshot(
        self,
        balance: float,
        equity: float,
        margin_used: Optional[float] = None,
        margin_free: Optional[float] = None
    ):
        """
        Save account balance snapshot.
        
        Args:
            balance: Account balance
            equity: Account equity
            margin_used: Margin used
            margin_free: Free margin
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO account_snapshots (timestamp, balance, equity, margin_used, margin_free)
                VALUES (datetime('now'), ?, ?, ?, ?)
            """, (balance, equity, margin_used, margin_free))
            conn.commit()
    
    def get_latest_account_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent account snapshot.
        
        Returns:
            Optional[Dict]: Account data or None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM account_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
