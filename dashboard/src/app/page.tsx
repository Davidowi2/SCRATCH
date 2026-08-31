'use client';

import { useState, useEffect } from 'react';

const API_URL = process.env.API_URL || 'http://localhost:5000';
const API_KEY = process.env.API_KEY || 'your-secret-api-key-change-this';

interface BotStatus {
  bot_running: boolean;
  session_start: string | null;
  last_heartbeat: string | null;
  total_trades: number;
  position_open: boolean;
  current_position: any;
  win_rate: number;
  total_pips: number;
  total_profit_usd: number;
  account_balance: number | null;
  account_equity: number | null;
}

interface Trade {
  id: number;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  side: string;
  pips: number;
  profit_usd: number;
  exit_reason: string;
  hold_time_seconds: number;
}

interface Metrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pips: number;
  total_profit_usd: number;
  avg_win_pips: number;
  avg_loss_pips: number;
  avg_hold_time_seconds: number;
  exit_reasons: Record<string, number>;
}

export default function Home() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      // Fetch status
      const statusRes = await fetch(`${API_URL}/status?api_key=${API_KEY}`);
      if (!statusRes.ok) throw new Error('Failed to fetch status');
      const statusData = await statusRes.json();
      setStatus(statusData);

      // Fetch recent trades
      const tradesRes = await fetch(`${API_URL}/trades?limit=10&api_key=${API_KEY}`);
      if (!tradesRes.ok) throw new Error('Failed to fetch trades');
      const tradesData = await tradesRes.json();
      setTrades(tradesData.trades || []);

      // Fetch metrics
      const metricsRes = await fetch(`${API_URL}/metrics?api_key=${API_KEY}`);
      if (!metricsRes.ok) throw new Error('Failed to fetch metrics');
      const metricsData = await metricsRes.json();
      setMetrics(metricsData.metrics);

      setLastUpdate(new Date());
      setError(null);
    } catch (err: any) {
      setError(err.message);
      console.error('Error fetching data:', err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const formatNumber = (num: number | null | undefined) => {
    if (num === null || num === undefined) return 'N/A';
    return num.toFixed(2);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">SCRATCH Bot Monitor</h1>

        {error && (
          <div className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded mb-6">
            <strong>Error:</strong> {error}
          </div>
        )}

        <div className="text-sm text-gray-400 mb-6">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>

        {/* Bot Status Card */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h2 className="text-2xl font-semibold mb-4">Bot Status</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <div className="text-gray-400 text-sm">Status</div>
              <div className={`text-2xl font-bold ${status?.bot_running ? 'text-green-500' : 'text-red-500'}`}>
                {status?.bot_running ? '● RUNNING' : '● STOPPED'}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Total Trades</div>
              <div className="text-2xl font-bold">{status?.total_trades || 0}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Position</div>
              <div className={`text-2xl font-bold ${status?.position_open ? 'text-yellow-500' : 'text-gray-500'}`}>
                {status?.position_open ? 'OPEN' : 'CLOSED'}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Win Rate</div>
              <div className="text-2xl font-bold">{formatNumber(status?.win_rate)}%</div>
            </div>
          </div>
        </div>

        {/* Current Position Card */}
        {status?.position_open && status?.current_position && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6 border-2 border-yellow-500">
            <h2 className="text-2xl font-semibold mb-4">Current Position</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <div>
                <div className="text-gray-400 text-sm">Side</div>
                <div className={`text-xl font-bold ${status.current_position.side === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>
                  {status.current_position.side}
                </div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">Entry Price</div>
                <div className="text-xl font-bold">{formatNumber(status.current_position.entry_price)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">Stop Loss</div>
                <div className="text-xl font-bold">{formatNumber(status.current_position.stop_loss)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">Take Profit</div>
                <div className="text-xl font-bold">{formatNumber(status.current_position.take_profit)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">Entry Time</div>
                <div className="text-xl font-bold">{formatDate(status.current_position.entry_time)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Performance Metrics Card */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h2 className="text-2xl font-semibold mb-4">Performance Metrics</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <div className="text-gray-400 text-sm">Total P&L (Pips)</div>
              <div className={`text-2xl font-bold ${(metrics?.total_pips || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatNumber(metrics?.total_pips)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Total P&L (USD)</div>
              <div className={`text-2xl font-bold ${(metrics?.total_profit_usd || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                ${formatNumber(metrics?.total_profit_usd)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Avg Win (Pips)</div>
              <div className="text-2xl font-bold text-green-500">{formatNumber(metrics?.avg_win_pips)}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Avg Loss (Pips)</div>
              <div className="text-2xl font-bold text-red-500">{formatNumber(metrics?.avg_loss_pips)}</div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-gray-400 text-sm">Winning Trades</div>
              <div className="text-2xl font-bold text-green-500">{metrics?.winning_trades || 0}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Losing Trades</div>
              <div className="text-2xl font-bold text-red-500">{metrics?.losing_trades || 0}</div>
            </div>
            <div>
              <div className="text-gray-400 text-sm">Avg Hold Time</div>
              <div className="text-2xl font-bold">{formatNumber(metrics?.avg_hold_time_seconds)}s</div>
            </div>
          </div>
        </div>

        {/* Account Info Card */}
        {(status?.account_balance || status?.account_equity) && (
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <h2 className="text-2xl font-semibold mb-4">Account</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="text-gray-400 text-sm">Balance</div>
                <div className="text-2xl font-bold">${formatNumber(status.account_balance)}</div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">Equity</div>
                <div className="text-2xl font-bold">${formatNumber(status.account_equity)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Recent Trades Table */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-2xl font-semibold mb-4">Recent Trades</h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left py-2 px-4">ID</th>
                  <th className="text-left py-2 px-4">Side</th>
                  <th className="text-left py-2 px-4">Entry</th>
                  <th className="text-left py-2 px-4">Exit</th>
                  <th className="text-left py-2 px-4">Pips</th>
                  <th className="text-left py-2 px-4">P&L (USD)</th>
                  <th className="text-left py-2 px-4">Exit Reason</th>
                  <th className="text-left py-2 px-4">Hold Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-4 text-gray-500">
                      No trades yet
                    </td>
                  </tr>
                ) : (
                  trades.map((trade) => (
                    <tr key={trade.id} className="border-b border-gray-700 hover:bg-gray-750">
                      <td className="py-2 px-4">{trade.id}</td>
                      <td className="py-2 px-4">
                        <span className={`font-bold ${trade.side === 'BUY' ? 'text-green-500' : 'text-red-500'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-2 px-4">{formatNumber(trade.entry_price)}</td>
                      <td className="py-2 px-4">{formatNumber(trade.exit_price)}</td>
                      <td className="py-2 px-4">
                        <span className={`font-bold ${trade.pips >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {formatNumber(trade.pips)}
                        </span>
                      </td>
                      <td className="py-2 px-4">
                        <span className={`font-bold ${trade.profit_usd >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          ${formatNumber(trade.profit_usd)}
                        </span>
                      </td>
                      <td className="py-2 px-4 text-sm">{trade.exit_reason}</td>
                      <td className="py-2 px-4">{formatNumber(trade.hold_time_seconds)}s</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
