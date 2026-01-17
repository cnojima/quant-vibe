import { useState } from 'react';
import { useLiveStatus, useLivePositions, useLiveOrders, useLiveEvents, useClearEvents, useLiveStats, useDailyReport, useRecentDailyReports, useActiveStrategies, useLiveTradesVisualization, useToggleDataFeedMode, useReconcilePositions } from '../api/queries';
// import { useWebSocket } from '../hooks/useWebSocket';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { LiveTradesChart } from '../components/charts/LiveTradesChart';
import { AccountSelector } from '../components/AccountSelector';
import { AccountBalancePanel } from '../components/AccountBalancePanel';
import { formatDistanceToNow } from 'date-fns';
import { useToast } from '../contexts/ToastContext';

export function LiveTradingMonitor() {
  const [tradingMode, setTradingMode] = useState<'real' | 'paper'>('paper');
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<'positions' | 'orders' | 'events' | 'reports' | 'trades'>('positions');
  const [orderStatusFilter, setOrderStatusFilter] = useState<'open' | 'filled' | 'rejected' | 'cancelled' | 'all'>('all');
  const [tradesDays, setTradesDays] = useState<number>(7);
  const { addToast } = useToast();

  // Fetch data for current trading mode and account
  const { data: status, isLoading: statusLoading } = useLiveStatus(tradingMode);
  const { data: positions } = useLivePositions('open', 100, tradingMode, selectedAccount || undefined);
  const { data: orders } = useLiveOrders(50, orderStatusFilter, tradingMode, selectedAccount || undefined);
  const { data: events } = useLiveEvents(50, undefined, undefined, tradingMode);
  const clearEventsMutation = useClearEvents();
  const toggleDataFeedMode = useToggleDataFeedMode();
  const reconcilePositions = useReconcilePositions();
  const { data: stats} = useLiveStats(undefined, undefined, tradingMode);
  const { data: todayReport } = useDailyReport(undefined, selectedAccount || undefined, tradingMode);
  const { data: recentReports } = useRecentDailyReports(7, selectedAccount || undefined, tradingMode);
  const { data: activeStrategies } = useActiveStrategies();
  const { data: tradesViz, isLoading: tradesLoading } = useLiveTradesVisualization(tradesDays);

  const handleClearEvents = () => {
    if (window.confirm('Are you sure you want to clear all events? This action cannot be undone.')) {
      clearEventsMutation.mutate();
    }
  };

  const handleToggleDataFeedMode = () => {
    const currentMode = status?.data_feed_mode || 'live';
    const newMode = currentMode === 'live' ? 'replay' : 'live';

    if (window.confirm(`Switch data feed mode from "${currentMode}" to "${newMode}"?\n\n⚠️ IMPORTANT: You must restart the ${tradingMode} trading engine for this change to take effect.\n\nProceed with config update?`)) {
      toggleDataFeedMode.mutate(tradingMode, {
        onSuccess: (data) => {
          addToast({
            type: 'success',
            title: 'Data Feed Mode Updated',
            message: `${data.message}. ${data.note || 'Please restart the trading engine for changes to take effect.'}`,
            duration: 8000
          });
        },
        onError: (error: any) => {
          addToast({
            type: 'error',
            title: 'Failed to Toggle Data Feed Mode',
            message: error.response?.data?.detail || error.message || 'An unknown error occurred',
            duration: 6000
          });
        }
      });
    }
  };

  const handleReconcile = () => {
    // Debug logging
    console.log('Reconciling with selectedAccount:', selectedAccount);

    if (!selectedAccount) {
      addToast({
        type: 'warning',
        title: 'Account Required',
        message: 'Please wait for accounts to load or select an account first',
        duration: 5000
      });
      return;
    }

      reconcilePositions.mutate({
        tradingMode,
        accountHash: selectedAccount
      }, {
        onSuccess: (data) => {
          addToast({
            type: 'success',
            title: 'Reconciliation Complete',
            message: data.message || 'Positions successfully synchronized with broker',
            duration: 6000
          });
        },
        onError: (error: any) => {
          addToast({
            type: 'error',
            title: 'Reconciliation Failed',
            message: error.response?.data?.detail || error.message || 'Failed to synchronize positions',
            duration: 6000
          });
        }
      });
  };

  // WebSocket disabled - using REST API polling instead
  // WebSocket has issues with React StrictMode + Docker networking
  // See: https://github.com/facebook/react/issues/24502
  // TODO: Re-enable in production build or when StrictMode is disabled
  // const { isConnected } = useWebSocket('/ws/events', {
  //   onMessage: (data) => {
  //     const topic = data?.topic || '';
  //     if (!topic.includes('heartbeat')) {
  //       console.log('[LiveMonitor] WS Event:', topic, data);
  //     }
  //   },
  //   onConnect: () => console.log('[LiveMonitor] WebSocket connected'),
  //   onDisconnect: () => console.log('[LiveMonitor] WebSocket disconnected'),
  //   reconnectInterval: 5000,
  //   maxReconnectAttempts: 10,
  // });
  const isConnected = false;

  if (statusLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-600">Loading live trading status...</div>
      </div>
    );
  }

  const getStatusBadge = () => {
    if (!status?.running) {
      return <Badge variant="default">Stopped</Badge>;
    }
    // Badge color matches the selected trading mode
    if (tradingMode === 'real') {
      return <Badge variant="error">LIVE TRADING</Badge>;
    }
    return <Badge variant="warning">PAPER TRADING</Badge>;
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Live Trading Monitor</h1>
            <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
              Real-time monitoring of live trading engine
            </p>
          </div>
          <div className="flex items-center gap-2 md:gap-3">
            {/* Trading Mode Selector */}
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => setTradingMode('paper')}
                className={`px-3 py-1.5 text-sm font-medium rounded transition-colors ${
                  tradingMode === 'paper'
                    ? 'bg-white text-blue-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Paper Trading
              </button>
              <button
                onClick={() => setTradingMode('real')}
                className={`px-3 py-1.5 text-sm font-medium rounded transition-colors ${
                  tradingMode === 'real'
                    ? 'bg-white text-red-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Real Trading
              </button>
            </div>

            {isConnected && (
              <Badge variant="success">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                  Live
                </span>
              </Badge>
            )}
            {getStatusBadge()}
          </div>
        </div>
      </div>

      {/* Account Selector */}
      <div className="mb-4 bg-white border border-gray-200 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <h2 className="text-lg font-semibold text-gray-900">Account</h2>
            <AccountSelector
              tradingMode={tradingMode}
              selectedAccount={selectedAccount}
              onAccountChange={setSelectedAccount}
            />
          </div>
        </div>
      </div>

      {/* Account Balance Panel */}
      <div className="mb-6">
        <AccountBalancePanel
          accountHash={selectedAccount}
          tradingMode={tradingMode}
          realtime={tradingMode === 'real'}
        />
      </div>

      {/* Real Trading Warning Banner */}
      {tradingMode === 'real' && (
        <div className="mb-4 md:mb-6 bg-red-50 border-2 border-red-500 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-bold text-red-900">⚠️ REAL MONEY TRADING</h3>
              <p className="text-sm text-red-800 mt-1">
                You are viewing the LIVE TRADING engine. All positions and orders involve real money.
                Exercise extreme caution when making changes.
              </p>
            </div>
            <div className="flex-shrink-0">
              <button
                onClick={handleReconcile}
                disabled={reconcilePositions.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
                title="Reconcile positions with Schwab broker"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {reconcilePositions.isPending ? 'Syncing...' : 'Reconcile'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Engine Status Overview */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 md:gap-4 mb-4 md:mb-6">
        <Card>
          <div className="text-sm text-gray-600 mb-1">Engine Status</div>
          <div className="text-2xl font-bold">
            {status?.running ? (
              <span className="text-green-600">Running</span>
            ) : (
              <span className="text-gray-600">Stopped</span>
            )}
          </div>
        </Card>

        <Card>
          <div className="text-sm text-gray-600 mb-1">Data Feed Mode</div>
          <div className="flex items-center gap-2">
            <div className="text-lg font-bold capitalize">
              {status?.data_feed_mode === 'replay' ? (
                <span className="text-orange-600">Replay</span>
              ) : (
                <span className="text-blue-600">Live</span>
              )}
            </div>
            <button
              onClick={handleToggleDataFeedMode}
              disabled={toggleDataFeedMode.isPending}
              className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded transition-colors disabled:opacity-50"
              title="Toggle between live and replay mode"
            >
              Switch
            </button>
          </div>
        </Card>

        <Card>
          <div className="text-sm text-gray-600 mb-1">Active Positions</div>
          <div className="text-2xl font-bold">{positions?.length || 0}</div>
        </Card>

        <Card>
          <div className="text-sm text-gray-600 mb-1">Total P&L</div>
          <div className={`text-2xl font-bold ${
            (stats?.total_pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'
          }`}>
            {formatCurrency(stats?.total_pnl || 0)}
          </div>
        </Card>

        <Card>
          <div className="text-sm text-gray-600 mb-1">Win Rate</div>
          <div className="text-2xl font-bold">
            {stats?.win_rate ? `${(stats.win_rate * 100).toFixed(1)}%` : 'N/A'}
          </div>
        </Card>
      </div>

      {/* Trading Statistics */}
      {stats && (
        <Card className="mb-6">
          <h3 className="text-lg font-semibold mb-4">Trading Statistics</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Total Trades</div>
              <div className="text-xl font-semibold">{stats.total_trades}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Wins / Losses</div>
              <div className="text-xl font-semibold">
                <span className="text-green-600">{stats.winning_trades}</span>
                {' / '}
                <span className="text-red-600">{stats.losing_trades}</span>
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Avg Win / Loss</div>
              <div className="text-xl font-semibold">
                <span className="text-green-600">{formatCurrency(stats.avg_win || 0)}</span>
                {' / '}
                <span className="text-red-600">{formatCurrency(stats.avg_loss || 0)}</span>
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Sharpe Ratio</div>
              <div className="text-xl font-semibold">
                {stats.sharpe_ratio ? stats.sharpe_ratio.toFixed(2) : 'N/A'}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Active Strategies */}
      {activeStrategies && activeStrategies.strategies.length > 0 && (
        <Card className="mb-6">
          <h3 className="text-lg font-semibold mb-4">Active Trading Strategies ({activeStrategies.count})</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeStrategies.strategies.map((strategy) => (
              <div key={strategy.name} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <h4 className="font-semibold text-base text-gray-900 capitalize">
                      {strategy.name.replace(/_/g, ' ')}
                    </h4>
                    <Badge variant="success" className="mt-1">Active</Badge>
                  </div>
                </div>

                {/* Strategy Stats */}
                {strategy.stats.total_trades > 0 && (
                  <div className="mb-3 pb-3 border-b border-gray-200">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <div className="text-gray-600">Trades</div>
                        <div className="font-semibold">{strategy.stats.total_trades}</div>
                      </div>
                      <div>
                        <div className="text-gray-600">Win Rate</div>
                        <div className="font-semibold">
                          {(strategy.stats.win_rate * 100).toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-600">P&L</div>
                        <div className={`font-semibold ${strategy.stats.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(strategy.stats.total_pnl)}
                        </div>
                      </div>
                      <div>
                        <div className="text-gray-600">W / L</div>
                        <div className="font-semibold text-xs">
                          <span className="text-green-600">{strategy.stats.winning_trades}</span>
                          {' / '}
                          <span className="text-red-600">{strategy.stats.losing_trades}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Key Parameters */}
                <div className="text-xs text-gray-600">
                  <div className="font-medium text-gray-700 mb-1">Key Parameters:</div>
                  <div className="space-y-0.5">
                    {strategy.params.max_trades_daily && (
                      <div className="flex justify-between">
                        <span>Max Daily Trades:</span>
                        <span className="font-mono text-gray-900">{strategy.params.max_trades_daily}</span>
                      </div>
                    )}
                    {strategy.params.spread_width && (
                      <div className="flex justify-between">
                        <span>Spread Width:</span>
                        <span className="font-mono text-gray-900">{strategy.params.spread_width}</span>
                      </div>
                    )}
                    {strategy.params.profit_target_min !== undefined && (
                      <div className="flex justify-between">
                        <span>Profit Target:</span>
                        <span className="font-mono text-gray-900">
                          {(strategy.params.profit_target_min * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                    {strategy.params.min_dte !== undefined && strategy.params.max_dte !== undefined && (
                      <div className="flex justify-between">
                        <span>DTE Range:</span>
                        <span className="font-mono text-gray-900">
                          {strategy.params.min_dte}-{strategy.params.max_dte}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Tabs */}
      <div className="mb-4 border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setSelectedTab('trades')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'trades'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Trades ({tradesViz?.total_trades || 0})
          </button>
          <button
            onClick={() => setSelectedTab('positions')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'positions'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Positions ({positions?.length || 0})
          </button>
          <button
            onClick={() => setSelectedTab('orders')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'orders'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Orders ({orders?.length || 0})
          </button>
          <button
            onClick={() => setSelectedTab('events')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'events'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Events ({events?.length || 0})
          </button>
          <button
            onClick={() => setSelectedTab('reports')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'reports'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Reports
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      {selectedTab === 'trades' && (
        <div className="space-y-4">
          {/* Time Range Selector */}
          <Card>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Trades Visualization</h3>
              <div className="flex items-center gap-2">
                <label htmlFor="trades-days" className="text-sm text-gray-600">Time Range:</label>
                <select
                  id="trades-days"
                  value={tradesDays}
                  onChange={(e) => setTradesDays(Number(e.target.value))}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value={1}>Last 24 Hours</option>
                  <option value={3}>Last 3 Days</option>
                  <option value={7}>Last 7 Days</option>
                  <option value={14}>Last 14 Days</option>
                  <option value={30}>Last 30 Days</option>
                  <option value={60}>Last 60 Days</option>
                  <option value={90}>Last 90 Days</option>
                </select>
              </div>
            </div>
          </Card>

          {/* Trades Chart */}
          <Card>
            {tradesLoading ? (
              <div className="flex justify-center items-center h-64">
                <div className="text-gray-600">Loading trades data...</div>
              </div>
            ) : tradesViz && tradesViz.total_trades > 0 ? (
              <>
                <div className="mb-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-sm text-gray-600">Total Trades</div>
                    <div className="text-xl font-semibold">{tradesViz.total_trades}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Initial Capital</div>
                    <div className="text-xl font-semibold">{formatCurrency(tradesViz.initial_capital)}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Current Equity</div>
                    <div className="text-xl font-semibold">
                      {tradesViz.equity_curve.length > 0
                        ? formatCurrency(tradesViz.equity_curve[tradesViz.equity_curve.length - 1].value)
                        : formatCurrency(tradesViz.initial_capital)
                      }
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Total P&L</div>
                    <div className={`text-xl font-semibold ${
                      (tradesViz.equity_curve.length > 0
                        ? tradesViz.equity_curve[tradesViz.equity_curve.length - 1].value - tradesViz.initial_capital
                        : 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {formatCurrency(
                        tradesViz.equity_curve.length > 0
                          ? tradesViz.equity_curve[tradesViz.equity_curve.length - 1].value - tradesViz.initial_capital
                          : 0
                      )}
                    </div>
                  </div>
                </div>

                <LiveTradesChart
                  data={tradesViz.equity_curve}
                  underlyingData={tradesViz.underlying_data}
                  trades={tradesViz.trades}
                  initialCapital={tradesViz.initial_capital}
                />
              </>
            ) : (
              <div className="text-center text-gray-600 py-8">
                No trades found in the selected time range
              </div>
            )}
          </Card>

          {/* Trade Details Table */}
          {tradesViz && tradesViz.trades && tradesViz.trades.length > 0 && (
            <Card>
              <h3 className="text-lg font-semibold mb-4">Recent Trades</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Time</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Strategy</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Spread</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Entry</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Exit</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">P&L</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Exit Reason</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {tradesViz.trades.slice().reverse().map((trade: any) => (
                      <tr key={trade.position_id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 whitespace-nowrap text-sm">
                          {new Date(trade.exit_time).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm">{trade.strategy}</td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm">{trade.spread_type || 'N/A'}</td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-right">
                          {formatCurrency(trade.entry_cost)}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-right">
                          {formatCurrency(trade.exit_value)}
                        </td>
                        <td className={`px-3 py-2 whitespace-nowrap text-sm text-right font-medium ${
                          trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {formatCurrency(trade.pnl)}
                        </td>
                        <td className="px-3 py-2 text-sm">{trade.exit_reason || 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {selectedTab === 'positions' && (
        <div className="space-y-4">
          {positions && positions.length > 0 ? (
            positions.map((position) => (
              <Card key={position.position_id}>
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-lg">{position.position_id}</h4>
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-sm text-gray-600">{position.strategy_name}</p>
                      {position.spread_type && (
                        <Badge variant="default" className="text-xs">
                          {position.spread_type}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Badge variant={(position.unrealized_pnl ?? 0) >= 0 ? 'success' : 'error'}>
                    {formatCurrency(position.unrealized_pnl ?? 0)}
                  </Badge>
                </div>

                <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <div className="text-gray-600">Entry Time</div>
                    <div className="font-medium">
                      {formatDistanceToNow(new Date(position.entry_time), { addSuffix: true })}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-600">Quantity</div>
                    <div className="font-medium">{position.legs?.[0]?.quantity ?? 0}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Entry Cost</div>
                    <div className="font-medium">{formatCurrency(position.entry_cost ?? 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Current Value</div>
                    <div className="font-medium">{formatCurrency(position.current_value ?? 0)}</div>
                  </div>
                </div>

                {position.legs && position.legs.length > 0 && (
                  <div className="mt-4 border-t pt-4">
                    <div className="text-sm font-medium text-gray-700 mb-2">Spread Legs:</div>
                    <div className="space-y-2">
                      {position.legs.map((leg, idx) => (
                        <div key={idx} className="flex justify-between text-sm">
                          <span>
                            {(leg.quantity ?? 0) > 0 ? '🟢 BUY' : '🔴 SELL'} {leg.contract_symbol}
                          </span>
                          <span className="font-mono">{formatCurrency(leg.price ?? leg.entry_price)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            ))
          ) : (
            <Card>
              <div className="text-center text-gray-600 py-8">
                No active positions
              </div>
            </Card>
          )}
        </div>
      )}

      {selectedTab === 'orders' && (
        <div className="space-y-4">
          {/* Order Status Filter */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setOrderStatusFilter('all')}
              className={`px-3 py-1 rounded text-sm ${
                orderStatusFilter === 'all'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setOrderStatusFilter('open')}
              className={`px-3 py-1 rounded text-sm ${
                orderStatusFilter === 'open'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Open
            </button>
            <button
              onClick={() => setOrderStatusFilter('filled')}
              className={`px-3 py-1 rounded text-sm ${
                orderStatusFilter === 'filled'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Filled
            </button>
            <button
              onClick={() => setOrderStatusFilter('rejected')}
              className={`px-3 py-1 rounded text-sm ${
                orderStatusFilter === 'rejected'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              Rejected
            </button>
          </div>

          {orders && orders.length > 0 ? (
            orders.map((order) => (
              <Card key={order.order_id}>
                <div className="flex justify-between items-start">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-semibold text-lg">{order.symbol}</h4>
                      {order.action_type && (
                        <Badge variant={order.action_type === 'opening' ? 'success' : 'default'}>
                          {order.action_type.toUpperCase()}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-gray-600">
                      {(order.action ?? order.side ?? '').toUpperCase()} {order.quantity} @ {formatCurrency(order.price ?? order.limit_price ?? 0)}
                    </p>
                    {order.strategy_name && (
                      <p className="text-xs text-gray-500 mt-1">
                        Strategy: <span className="font-medium">{order.strategy_name}</span>
                      </p>
                    )}
                  </div>
                  <Badge
                    variant={
                      order.status === 'filled' ? 'success' :
                      order.status === 'rejected' ? 'error' :
                      'warning'
                    }
                  >
                    {order.status}
                  </Badge>
                </div>

                <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <div className="text-gray-600">Order Time</div>
                    <div className="font-medium">
                      {formatDistanceToNow(new Date(order.timestamp ?? order.submitted_time ?? ''), { addSuffix: true })}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-600">Order Type</div>
                    <div className="font-medium">{order.order_type.toUpperCase()}</div>
                  </div>
                  {order.filled_price && (
                    <div>
                      <div className="text-gray-600">Filled Price</div>
                      <div className="font-medium">{formatCurrency(order.filled_price)}</div>
                    </div>
                  )}
                </div>
              </Card>
            ))
          ) : (
            <Card>
              <div className="text-center text-gray-600 py-8">
                No {orderStatusFilter !== 'all' ? orderStatusFilter : ''} orders found
              </div>
            </Card>
          )}
        </div>
      )}

      {selectedTab === 'events' && (
        <div className="space-y-4">
          <div className="flex justify-end mb-4">
            <button
              onClick={handleClearEvents}
              disabled={clearEventsMutation.isPending || !events || events.length === 0}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {clearEventsMutation.isPending ? 'Clearing...' : 'Clear Events'}
            </button>
          </div>
          {events && events.length > 0 ? (
            events.map((event, idx) => (
              <Card key={idx}>
                <div className="flex items-start gap-3">
                  <Badge
                    variant={
                      event.severity === 'error' ? 'error' :
                      event.severity === 'warning' ? 'warning' :
                      'default'
                    }
                  >
                    {event.event_type}
                  </Badge>
                  <div className="flex-1">
                    <p className="text-sm">{event.message}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                    </p>
                  </div>
                </div>
              </Card>
            ))
          ) : (
            <Card>
              <div className="text-center text-gray-600 py-8">
                No events found
              </div>
            </Card>
          )}
        </div>
      )}

      {selectedTab === 'reports' && (
        <div className="space-y-6">
          {/* Today's Report */}
          {todayReport && (
            <Card>
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-semibold">Today's Performance</h3>
                  <p className="text-sm text-gray-600">{todayReport.date}</p>
                </div>
                <Badge variant={todayReport.risk_metrics.status === 'healthy' ? 'success' : todayReport.risk_metrics.status === 'warning' ? 'warning' : 'error'}>
                  {todayReport.risk_metrics.status.toUpperCase()}
                </Badge>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div>
                  <div className="text-sm text-gray-600">Realized P&L</div>
                  <div className={`text-2xl font-bold ${todayReport.actual_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatCurrency(todayReport.actual_pnl)}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Target P&L</div>
                  <div className="text-2xl font-bold text-gray-900">
                    {formatCurrency(todayReport.target_pnl)}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Achievement</div>
                  <div className={`text-2xl font-bold ${todayReport.achievement_pct >= 100 ? 'text-green-600' : todayReport.achievement_pct >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                    {todayReport.achievement_pct.toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Win Rate</div>
                  <div className="text-2xl font-bold">
                    {todayReport.win_rate.toFixed(1)}%
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div>
                  <div className="text-sm text-gray-600">Total Trades</div>
                  <div className="text-xl font-semibold">{todayReport.total_trades}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Winners / Losers</div>
                  <div className="text-xl font-semibold">
                    <span className="text-green-600">{todayReport.winning_trades}</span> / <span className="text-red-600">{todayReport.losing_trades}</span>
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Profit Factor</div>
                  <div className="text-xl font-semibold">{todayReport.profit_factor.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Max Drawdown</div>
                  <div className={`text-xl font-semibold ${todayReport.max_drawdown_pct > 1.5 ? 'text-red-600' : 'text-gray-900'}`}>
                    {todayReport.max_drawdown_pct.toFixed(2)}%
                  </div>
                </div>
              </div>

              {todayReport.risk_metrics.warnings && todayReport.risk_metrics.warnings.length > 0 && (
                <div className="border-t pt-4">
                  <div className="text-sm font-medium text-gray-700 mb-2">⚠️ Warnings:</div>
                  <ul className="space-y-1">
                    {todayReport.risk_metrics.warnings.map((warning: string, idx: number) => (
                      <li key={idx} className="text-sm text-yellow-700">• {warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              {Object.keys(todayReport.by_strategy || {}).length > 0 && (
                <div className="border-t pt-4 mt-4">
                  <div className="text-sm font-medium text-gray-700 mb-3">Strategy Breakdown:</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(todayReport.by_strategy).map(([strategy, metrics]: [string, any]) => (
                      <div key={strategy} className="bg-gray-50 p-3 rounded">
                        <div className="font-medium text-sm mb-2">{strategy}</div>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div>
                            <div className="text-gray-600">P&L</div>
                            <div className={`font-semibold ${metrics.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {formatCurrency(metrics.pnl)}
                            </div>
                          </div>
                          <div>
                            <div className="text-gray-600">Trades</div>
                            <div className="font-semibold">{metrics.trades}</div>
                          </div>
                          <div>
                            <div className="text-gray-600">Win Rate</div>
                            <div className="font-semibold">{metrics.win_rate.toFixed(1)}%</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* Recent Reports */}
          <Card>
            <h3 className="text-lg font-semibold mb-4">Last 7 Days</h3>
            {recentReports && recentReports.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">P&L</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Target</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Achievement</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Trades</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Win Rate</th>
                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {recentReports.map((report: any) => (
                      <tr key={report.date} className="hover:bg-gray-50">
                        <td className="px-3 py-2 whitespace-nowrap text-sm">{report.date}</td>
                        <td className={`px-3 py-2 whitespace-nowrap text-sm text-right font-medium ${report.actual_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCurrency(report.actual_pnl)}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-right text-gray-600">
                          {formatCurrency(report.target_pnl)}
                        </td>
                        <td className={`px-3 py-2 whitespace-nowrap text-sm text-right font-medium ${report.achievement_pct >= 100 ? 'text-green-600' : report.achievement_pct >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                          {report.achievement_pct.toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-right">{report.total_trades}</td>
                        <td className="px-3 py-2 whitespace-nowrap text-sm text-right">{report.win_rate.toFixed(1)}%</td>
                        <td className="px-3 py-2 whitespace-nowrap text-center">
                          <Badge variant={report.risk_metrics.status === 'healthy' ? 'success' : report.risk_metrics.status === 'warning' ? 'warning' : 'error'}>
                            {report.risk_metrics.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center text-gray-600 py-8">
                No recent reports available
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
