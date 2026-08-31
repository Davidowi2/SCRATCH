"""
SCRATCH Bot Monitoring API

Flask backend that serves bot status, trade data, and metrics
for the monitoring dashboard.
"""

import os
import sys
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import logging

# Add parent directory to path to import database manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for all routes (allow dashboard to connect)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/api.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize database
db = DatabaseManager()

# API Key for authentication (load from environment)
API_KEY = os.getenv('API_KEY', 'your-secret-api-key-change-this')


def require_api_key(f):
    """Decorator to require API key authentication."""
    def decorated_function(*args, **kwargs):
        # Get API key from header or query parameter
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if api_key != API_KEY:
            return jsonify({'error': 'Unauthorized - Invalid API key'}), 401
        
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function


@app.route('/')
def index():
    """Root endpoint - API information."""
    return jsonify({
        'name': 'SCRATCH Bot Monitoring API',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            '/health': 'Health check',
            '/status': 'Bot status',
            '/position': 'Current open position',
            '/trades': 'Recent closed trades',
            '/trades/last': 'Last closed trade',
            '/metrics': 'Trading metrics',
            '/account': 'Account balance info'
        }
    })


@app.route('/health')
def health():
    """Health check endpoint."""
    try:
        # Check database connectivity
        bot_status = db.get_bot_status()
        
        # Check if bot heartbeat is recent (within last 60 seconds)
        if bot_status and bot_status.get('last_heartbeat'):
            last_heartbeat = datetime.fromisoformat(bot_status['last_heartbeat'])
            time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()
            bot_alive = time_since_heartbeat < 60
        else:
            bot_alive = False
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'bot_alive': bot_alive,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/status')
@require_api_key
def get_status():
    """Get bot status and current state."""
    try:
        bot_status = db.get_bot_status()
        open_trade = db.get_open_trade()
        metrics = db.get_metrics()
        account = db.get_latest_account_snapshot()
        
        # Check if bot is alive
        bot_alive = False
        if bot_status and bot_status.get('last_heartbeat'):
            last_heartbeat = datetime.fromisoformat(bot_status['last_heartbeat'])
            time_since_heartbeat = (datetime.now() - last_heartbeat).total_seconds()
            bot_alive = time_since_heartbeat < 60
        
        return jsonify({
            'bot_running': bot_alive,
            'session_start': bot_status.get('session_start') if bot_status else None,
            'last_heartbeat': bot_status.get('last_heartbeat') if bot_status else None,
            'total_trades': bot_status.get('total_trades', 0) if bot_status else 0,
            'position_open': open_trade is not None,
            'current_position': open_trade,
            'win_rate': metrics.get('win_rate', 0),
            'total_pips': metrics.get('total_pips', 0),
            'total_profit_usd': metrics.get('total_profit_usd', 0),
            'account_balance': account.get('balance') if account else None,
            'account_equity': account.get('equity') if account else None,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/position')
@require_api_key
def get_position():
    """Get current open position if any."""
    try:
        open_trade = db.get_open_trade()
        
        if open_trade:
            # Calculate time in position
            entry_time = datetime.fromisoformat(open_trade['entry_time'])
            time_in_position = (datetime.now() - entry_time).total_seconds()
            open_trade['time_in_position_seconds'] = round(time_in_position, 2)
        
        return jsonify({
            'position_open': open_trade is not None,
            'position': open_trade,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/trades')
@require_api_key
def get_trades():
    """Get recent closed trades."""
    try:
        # Get limit from query parameter (default 50, max 200)
        limit = min(int(request.args.get('limit', 50)), 200)
        
        trades = db.get_recent_trades(limit=limit)
        
        return jsonify({
            'count': len(trades),
            'trades': trades,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/trades/last')
@require_api_key
def get_last_trade():
    """Get the last closed trade."""
    try:
        last_trade = db.get_last_closed_trade()
        
        return jsonify({
            'trade': last_trade,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching last trade: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/metrics')
@require_api_key
def get_metrics():
    """Get trading performance metrics."""
    try:
        metrics = db.get_metrics()
        
        return jsonify({
            'metrics': metrics,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/account')
@require_api_key
def get_account():
    """Get account balance information."""
    try:
        account = db.get_latest_account_snapshot()
        
        return jsonify({
            'account': account,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching account info: {e}")
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("SCRATCH Monitoring API Starting")
    logger.info("=" * 60)
    
    # Get port from environment variable (default 5000)
    port = int(os.getenv('API_PORT', 5000))
    
    # Run Flask app
    app.run(
        host='0.0.0.0',  # Listen on all interfaces
        port=port,
        debug=False  # Set to False in production
    )
