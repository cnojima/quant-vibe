import { useState } from 'react';
import { useLiveStatus, useLivePositions, useLiveOrders, useLiveEvents, useLiveStats, useDailyReport, useRecentDailyReports, useActiveStrategies } from '../api/queries';
// import { useWebSocket } from '../hooks/useWebSocket';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { formatDistanceToNow } from 'date-fns';

export function LiveTradingMonitor() {
  const [selectedTab, setSelectedTab] = useState<'positions' | 'orders' | 'events' | 'reports'>('positions');
  const [orderStatusFilter, setOrderStatusFilter] = useState<'open' | 'filled' | 'rejected' | 'cancelled' | 'all'>('all');
  const { data: status, isLoading: statusLoading } = useLiveStatus();
  const { data: positions } = useLivePositions('open');
  const { data: orders } = useLiveOrders(50, orderStatusFilter);
  const { data: events } = useLiveEvents(50);
  const { data: stats} = useLiveStats();
  const { data: todayReport } = useDailyReport();
  const { data: recentReports } = useRecentDailyReports(7);
  const { data: activeStrategies } = useActiveStrategies();

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
    if (status.paper_trading) {
      return <Badge variant="warning">Paper Trading</Badge>;
    }
    return <Badge variant="success">Live Trading</Badge>;
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

      {/* Engine Status Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mb-4 md:mb-6">
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
      {selectedTab === 'positions' && (
        <div className="space-y-4">
          {positions && positions.length > 0 ? (
            positions.map((position) => (
              <Card key={position.position_id}>
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-lg">{position.symbol}</h4>
                    <p className="text-sm text-gray-600">{position.strategy}</p>
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
                    <div className="font-medium">{position.quantity ?? 0}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Entry Price</div>
                    <div className="font-medium">{formatCurrency(position.entry_price ?? 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Current Price</div>
                    <div className="font-medium">{formatCurrency(position.current_price ?? 0)}</div>
                  </div>
                </div>

                {position.legs && position.legs.length > 0 && (
                  <div className="mt-4 border-t pt-4">
                    <div className="text-sm font-medium text-gray-700 mb-2">Spread Legs:</div>
                    <div className="space-y-2">
                      {position.legs.map((leg, idx) => (
                        <div key={idx} className="flex justify-between text-sm">
                          <span>
                            {(leg.action ?? leg.side) === 'buy' ? '🟢 BUY' : '🔴 SELL'} {leg.contract_symbol}
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
                    <h4 className="font-semibold text-lg">{order.symbol}</h4>
                    <p className="text-sm text-gray-600">
                      {(order.action ?? order.side ?? '').toUpperCase()} {order.quantity} @ {formatCurrency(order.price ?? order.limit_price ?? 0)}
                    </p>
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
                  <div className="text-sm text-gray-600">Actual P&L</div>
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
