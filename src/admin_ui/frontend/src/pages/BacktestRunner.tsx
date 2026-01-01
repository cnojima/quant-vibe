import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useStrategies, useRunBacktest, useBacktestStatus, useBacktestResults, useBacktestHistory, useDeleteBacktest, useDeleteAllBacktests } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { InfoIcon } from '../components/common/InfoIcon';
import { EquityCurveChart } from '../components/charts/EquityCurveChart';
import { PnLDistributionChart } from '../components/charts/PnLDistributionChart';
import { DrawdownChart } from '../components/charts/DrawdownChart';
import { formatDistanceToNow } from 'date-fns';
import {
  getTodayEST,
  getYesterdayEST,
  getThisWeekEST,
  getLastWeekEST,
  getLastNMonthsEST,
  getLastNYearsEST,
} from '../utils/dateUtils';

export function BacktestRunner() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [initialCapital, setInitialCapital] = useState<number>(100000);
  const [minDte, setMinDte] = useState<number>(0);
  const [maxDte, setMaxDte] = useState<number>(2);
  const [maxTradesDaily, setMaxTradesDaily] = useState<number>(1);
  const [currentBacktestId, setCurrentBacktestId] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<'run' | 'results' | 'history'>('run');

  const queryClient = useQueryClient();
  const { data: strategies, isLoading: strategiesLoading } = useStrategies();
  const runBacktest = useRunBacktest();
  const { data: backtestStatus } = useBacktestStatus(currentBacktestId);
  const { data: backtestResults } = useBacktestResults(currentBacktestId, backtestStatus?.status);
  const { data: history } = useBacktestHistory(50);
  const deleteBacktest = useDeleteBacktest();
  const deleteAllBacktests = useDeleteAllBacktests();

  // Invalidate history when backtest completes
  useEffect(() => {
    if (backtestStatus?.status === 'completed' || backtestStatus?.status === 'failed') {
      queryClient.invalidateQueries({ queryKey: ['backtest-history'] });
    }
  }, [backtestStatus?.status, queryClient]);

  const handleRunBacktest = async () => {
    if (!selectedStrategy || !startDate || !endDate) {
      alert('Please fill in all required fields');
      return;
    }

    try {
      const result = await runBacktest.mutateAsync({
        strategy_name: selectedStrategy,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        params: {
          min_dte: minDte,
          max_dte: maxDte,
          max_trades_daily: maxTradesDaily,
        },
        parameters: {
          min_dte: minDte,
          max_dte: maxDte,
          max_trades_daily: maxTradesDaily,
        },
      });

      setCurrentBacktestId(result.backtest_id);
      setSelectedTab('results');
    } catch (error) {
      console.error('Failed to run backtest:', error);
    }
  };

  const handleDeleteBacktest = async (backtestId: string) => {
    if (!confirm('Are you sure you want to delete this backtest? This action cannot be undone.')) {
      return;
    }

    try {
      await deleteBacktest.mutateAsync(backtestId);
    } catch (error) {
      console.error('Failed to delete backtest:', error);
      alert('Failed to delete backtest. Please try again.');
    }
  };

  const handleDeleteAllBacktests = async () => {
    const count = history?.length || 0;
    if (!confirm(`⚠️ WARNING: This will permanently delete ALL ${count} backtests from the database and filesystem.\n\nThis action CANNOT be undone!\n\nAre you absolutely sure?`)) {
      return;
    }

    // Double confirmation
    if (!confirm('This is your final warning. Delete ALL backtests?')) {
      return;
    }

    try {
      const result = await deleteAllBacktests.mutateAsync();
      alert(`Successfully deleted ${result.deleted_count} backtests and ${result.deleted_files_count} report files.`);
    } catch (error) {
      console.error('Failed to delete all backtests:', error);
      alert('Failed to delete all backtests. Please try again.');
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number | undefined | null) => {
    if (value === undefined || value === null || isNaN(value)) {
      return 'N/A';
    }
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  // Process results for charts
  const getEquityCurveData = () => {
    if (!backtestResults?.equity_curve) return [];
    return backtestResults.equity_curve.map((point: any) => ({
      timestamp: point.timestamp || point.date,
      value: point.value || point.portfolio_value,
    }));
  };

  // Transform trades to match chart component's expected format
  const getTransformedTrades = () => {
    if (!backtestResults?.trades) return [];
    return backtestResults.trades.map((trade: any) => {
      // Parse legs if it's a JSON string
      let legs = trade.legs;
      if (typeof legs === 'string') {
        try {
          legs = JSON.parse(legs);
        } catch (e) {
          legs = [];
        }
      }

      return {
        ...trade,
        legs: Array.isArray(legs) ? legs.map((leg: any) => ({
          ...leg,
          option_type: leg.option_type || leg.contract_type,
        })) : [],
      };
    });
  };

  const getPnLDistribution = () => {
    if (!backtestResults?.trades) return [];

    const trades = backtestResults.trades;
    const buckets: { [key: string]: number } = {};
    const bucketSize = 50; // $50 buckets

    trades.forEach((trade: any) => {
      const pnl = parseFloat(trade.pnl || trade.profit_loss) || 0;
      const bucket = Math.floor(pnl / bucketSize) * bucketSize;
      const rangeLabel = `$${bucket} to $${bucket + bucketSize}`;
      buckets[rangeLabel] = (buckets[rangeLabel] || 0) + 1;
    });

    return Object.entries(buckets)
      .map(([range, count]) => ({ range, count }))
      .sort((a, b) => {
        const aStart = parseInt(a.range.split('$')[1]);
        const bStart = parseInt(b.range.split('$')[1]);
        return aStart - bStart;
      });
  };

  const getDrawdownData = () => {
    if (!backtestResults?.equity_curve) return [];

    const equity = backtestResults.equity_curve;
    let peak = initialCapital;
    return equity.map((point: any) => {
      const value = point.value || point.portfolio_value;
      peak = Math.max(peak, value);
      const drawdown = ((value - peak) / peak) * 100;
      return {
        timestamp: point.timestamp || point.date,
        drawdown,
      };
    });
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Backtest Runner</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          Test your trading strategies on historical data
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setSelectedTab('run')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'run'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Run Backtest
          </button>
          <button
            onClick={() => setSelectedTab('results')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'results'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Results
          </button>
          <button
            onClick={() => setSelectedTab('history')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'history'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            History ({history?.length || 0})
          </button>
        </nav>
      </div>

      {/* Run Tab */}
      {selectedTab === 'run' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Backtest Configuration</h3>
              <InfoIcon
                content="Configure the parameters for your backtest simulation. Select a strategy, date range, and capital to test historical performance."
                placement="right"
              />
            </div>

            <div className="space-y-4">
              <div>
                <label className="label">Strategy</label>
                <select
                  className="input"
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  disabled={strategiesLoading}
                >
                  <option value="">Select a strategy...</option>
                  {strategies?.map((strategy) => (
                    <option key={strategy.name} value={strategy.name}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Start Date</label>
                <input
                  type="date"
                  className="input"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </div>

              <div>
                <label className="label">End Date</label>
                <input
                  type="date"
                  className="input"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="label mb-0">DTE Range (Days to Expiration)</label>
                  <InfoIcon
                    content="DTE (Days to Expiration) controls which options contracts are eligible for trading. 0 DTE = same-day expiration, higher values = longer-dated contracts. Most intraday strategies use 0-2 DTE."
                    placement="right"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-gray-600">Min DTE</label>
                    <input
                      type="number"
                      className="input"
                      value={minDte}
                      onChange={(e) => setMinDte(Number(e.target.value))}
                      min={0}
                      max={maxDte}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-600">Max DTE</label>
                    <input
                      type="number"
                      className="input"
                      value={maxDte}
                      onChange={(e) => setMaxDte(Number(e.target.value))}
                      min={minDte}
                      max={45}
                    />
                  </div>
                </div>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
                    onClick={() => { setMinDte(0); setMaxDte(0); }}
                  >
                    0 DTE
                  </button>
                  <button
                    type="button"
                    className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
                    onClick={() => { setMinDte(0); setMaxDte(2); }}
                  >
                    0-2 DTE
                  </button>
                  <button
                    type="button"
                    className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded"
                    onClick={() => { setMinDte(0); setMaxDte(7); }}
                  >
                    0-7 DTE
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="label mb-0">Initial Capital</label>
                  <InfoIcon
                    content="Starting account balance for the backtest. This represents your total available capital for trading. All performance metrics are calculated relative to this amount."
                    placement="right"
                  />
                </div>
                <input
                  type="number"
                  className="input"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value))}
                  step={1000}
                  min={1000}
                />
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="label mb-0">Max Trades Per Day</label>
                  <InfoIcon
                    content="Limits the number of positions that can be opened in a single trading day. This helps control risk and prevents over-trading. 1 = one position per day (recommended for most strategies), 0 = no trading, 999 = unlimited."
                    placement="right"
                  />
                </div>
                <input
                  type="number"
                  className="input"
                  value={maxTradesDaily}
                  onChange={(e) => setMaxTradesDaily(Number(e.target.value))}
                  step={1}
                  min={0}
                  max={999}
                />
                <p className="text-xs text-gray-500 mt-1">
                  Maximum number of trades allowed per day (1 = default, 0 = no trades, 999 = unlimited)
                </p>
              </div>

              <Button
                variant="primary"
                className="w-full"
                onClick={handleRunBacktest}
                disabled={runBacktest.isPending || !selectedStrategy || !startDate || !endDate}
              >
                {runBacktest.isPending ? 'Running...' : 'Run Backtest'}
              </Button>
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Quick Date Presets</h3>
              <InfoIcon
                content="One-click date range selection for common backtest periods. All dates use US Eastern Time (EST) and only include trading days (Mon-Fri, excluding holidays)."
                placement="right"
              />
            </div>
            <div className="space-y-2">
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const dateStr = getTodayEST();
                  setStartDate(dateStr);
                  setEndDate(dateStr);
                }}
              >
                Today
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const dateStr = getYesterdayEST();
                  setStartDate(dateStr);
                  setEndDate(dateStr);
                }}
              >
                Yesterday
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getThisWeekEST();
                  setStartDate(start);
                  setEndDate(end);
                }}
              >
                This Week
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastWeekEST();
                  setStartDate(start);
                  setEndDate(end);
                }}
              >
                Last Week
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastNMonthsEST(1);
                  setStartDate(start);
                  setEndDate(end);
                }}
              >
                Last Month
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastNMonthsEST(3);
                  setStartDate(start);
                  setEndDate(end);
                }}
              >
                Last 3 Months
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastNYearsEST(1);
                  setStartDate(start);
                  setEndDate(end);
                }}
              >
                Last Year
              </Button>
            </div>

            {selectedStrategy && strategies && (
              <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded">
                <h4 className="font-medium text-blue-900 mb-2">Strategy Info</h4>
                <p className="text-sm text-blue-700">
                  {strategies.find((s) => s.name === selectedStrategy)?.description || 'No description available'}
                </p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Results Tab */}
      {selectedTab === 'results' && (
        <div>
          {backtestStatus && backtestStatus.status !== 'completed' && (
            <Card className="mb-6">
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="font-medium mb-1">
                    Backtest Status: {backtestStatus.status}
                  </div>
                  {backtestStatus.status === 'failed' && backtestStatus.error && (
                    <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded">
                      <div className="text-sm font-medium text-red-800">Error:</div>
                      <pre className="text-xs text-red-700 mt-1 whitespace-pre-wrap overflow-x-auto">
                        {backtestStatus.error}
                      </pre>
                    </div>
                  )}
                  {backtestStatus.progress !== undefined && (
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-blue-600 h-2 rounded-full transition-all"
                        style={{ width: `${backtestStatus.progress}%` }}
                      />
                    </div>
                  )}
                </div>
                {backtestStatus.status === 'running' && (
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                )}
              </div>
            </Card>
          )}

          {backtestResults && (
            <>
              {/* Performance Summary */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <Card>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="text-sm text-gray-600">Total Return</div>
                    <InfoIcon
                      content="The total percentage gain or loss from your initial capital. A positive return means your strategy made money, negative means it lost money. This is the primary measure of strategy profitability."
                      placement="bottom"
                    />
                  </div>
                  <div className={`text-2xl font-bold ${
                    (backtestResults.metrics?.total_return || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {formatPercent(backtestResults.metrics?.total_return || 0)}
                  </div>
                </Card>

                <Card>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="text-sm text-gray-600">Sharpe Ratio</div>
                    <InfoIcon
                      content="Risk-adjusted return metric. Higher is better. >1.0 = good, >2.0 = very good, >3.0 = excellent. Measures excess return per unit of risk. A Sharpe ratio of 2.0 means you earned 2% of excess return for every 1% of risk taken."
                      placement="bottom"
                    />
                  </div>
                  <div className="text-2xl font-bold">
                    {backtestResults.metrics?.sharpe_ratio?.toFixed(2) || 'N/A'}
                  </div>
                </Card>

                <Card>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="text-sm text-gray-600">Max Drawdown</div>
                    <InfoIcon
                      content="The largest peak-to-trough decline in portfolio value. Represents the worst losing period you would have experienced. Lower is better. For example, -15% means your portfolio fell 15% from its highest point before recovering."
                      placement="bottom"
                    />
                  </div>
                  <div className="text-2xl font-bold text-red-600">
                    {formatPercent(backtestResults.metrics?.max_drawdown || 0)}
                  </div>
                </Card>

                <Card>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="text-sm text-gray-600">Win Rate</div>
                    <InfoIcon
                      content="Percentage of trades that were profitable. A 60% win rate means 6 out of 10 trades made money. Note: A high win rate doesn't guarantee profitability if winning trades are small and losing trades are large."
                      placement="bottom"
                    />
                  </div>
                  <div className="text-2xl font-bold">
                    {((backtestResults.metrics?.win_rate || 0) * 100).toFixed(1)}%
                  </div>
                </Card>
              </div>

              {/* Backtest Configuration */}
              {backtestResults.parameters && Object.keys(backtestResults.parameters).length > 0 && (
                <Card className="mb-6">
                  <div className="flex items-center gap-2 mb-4">
                    <h3 className="text-lg font-semibold">Backtest Configuration</h3>
                    <InfoIcon
                      content="Summary of the parameters used to run this backtest. This includes the strategy name, date range, initial capital, and all strategy-specific parameters that were configured."
                      placement="right"
                    />
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Strategy</div>
                      <div className="font-semibold">{backtestResults.strategy_name || 'N/A'}</div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Start Date</div>
                      <div className="font-semibold">
                        {backtestResults.start_date
                          ? new Date(backtestResults.start_date).toLocaleDateString()
                          : 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">End Date</div>
                      <div className="font-semibold">
                        {backtestResults.end_date
                          ? new Date(backtestResults.end_date).toLocaleDateString()
                          : 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Initial Capital</div>
                      <div className="font-semibold">{formatCurrency(backtestResults.initial_capital || 0)}</div>
                    </div>
                    {Object.entries(backtestResults.parameters).map(([key, value]) => (
                      <div key={key}>
                        <div className="text-sm text-gray-600 mb-1">
                          {key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                        </div>
                        <div className="font-semibold">
                          {typeof value === 'number' ? value.toFixed(2) : String(value)}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Charts */}
              <Card className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-lg font-semibold">Equity Curve & Underlying Price</h3>
                  <InfoIcon
                    content="Shows your portfolio value over time (blue line) and the underlying SPX price (gray line). Green dots = position entries, light green = profitable exits, red = losing exits. Use this to visualize when your strategy enters/exits and how it performs in different market conditions."
                    placement="right"
                  />
                </div>
                <EquityCurveChart
                  data={getEquityCurveData()}
                  initialCapital={initialCapital}
                  underlyingData={backtestResults?.underlying_bars || []}
                  trades={getTransformedTrades()}
                />
                <div className="mt-4 text-sm text-gray-600 flex items-center gap-4">
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-3 h-3 rounded-full bg-[#10b981] border-2 border-white"></span>
                    Position Entry
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-3 h-3 rounded-full bg-[#22c55e] border-2 border-white"></span>
                    Profitable Exit
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-3 h-3 rounded-full bg-[#ef4444] border-2 border-white"></span>
                    Loss Exit
                  </span>
                </div>
              </Card>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <Card>
                  <div className="flex items-center gap-2 mb-4">
                    <h3 className="text-lg font-semibold">P&L Distribution</h3>
                    <InfoIcon
                      content="Histogram showing the distribution of trade profits and losses. This helps you understand if your strategy has consistent returns or high variability. A tight distribution around positive values is ideal."
                      placement="right"
                    />
                  </div>
                  <PnLDistributionChart data={getPnLDistribution()} />
                </Card>

                <Card>
                  <div className="flex items-center gap-2 mb-4">
                    <h3 className="text-lg font-semibold">Drawdown</h3>
                    <InfoIcon
                      content="Shows how far your portfolio has fallen from its peak at any point in time. Measures the pain of losing streaks. Shallower drawdowns (closer to 0%) mean smoother performance with less severe losing periods."
                      placement="right"
                    />
                  </div>
                  <DrawdownChart data={getDrawdownData()} />
                </Card>
              </div>

              {/* Trades Table */}
              <Card>
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-lg font-semibold">Trades ({backtestResults.trades?.length || 0})</h3>
                  <InfoIcon
                    content="Detailed list of all trades executed during the backtest. Shows entry/exit times, position identifiers, profit/loss in dollars, and return percentage. Use this to analyze individual trade performance and identify patterns."
                    placement="right"
                  />
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead>
                      <tr>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entry</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Exit</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">P&L</th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Return %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {backtestResults.trades?.slice(0, 50).map((trade: any, idx: number) => {
                        const pnl = parseFloat(trade.pnl) || 0;
                        const returnPct = parseFloat(trade.pnl_percent || trade.return_pct) || 0;

                        return (
                          <tr key={idx} className="hover:bg-gray-50">
                            <td className="px-4 py-3 text-sm">
                              {new Date(trade.entry_time).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-3 text-sm">
                              {new Date(trade.exit_time).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-3 text-sm font-mono">{trade.position_id || trade.symbol || 'N/A'}</td>
                            <td className={`px-4 py-3 text-sm text-right font-medium ${
                              pnl >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {formatCurrency(pnl)}
                            </td>
                            <td className={`px-4 py-3 text-sm text-right font-medium ${
                              returnPct >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {formatPercent(returnPct)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}

          {!backtestResults && !backtestStatus && (
            <Card>
              <div className="text-center text-gray-600 py-12">
                No backtest results available. Run a backtest to see results.
              </div>
            </Card>
          )}
        </div>
      )}

      {/* History Tab */}
      {selectedTab === 'history' && (
        <div className="space-y-4">
          {/* Delete All Button */}
          {history && history.length > 0 && (
            <div className="flex justify-end mb-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleDeleteAllBacktests}
                disabled={deleteAllBacktests.isPending}
                className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-300"
              >
                {deleteAllBacktests.isPending ? 'Deleting All...' : `🗑️ Delete All (${history.length})`}
              </Button>
            </div>
          )}

          {history && history.length > 0 ? (
            history.map((backtest) => (
              <Card key={backtest.backtest_id}>
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-lg">{(backtest as any).request?.strategy_name || backtest.strategy_name || 'Unknown Strategy'}</h4>
                    <p className="text-sm text-gray-600">
                      {(backtest as any).request?.start_date && (backtest as any).request?.end_date
                        ? `${new Date((backtest as any).request.start_date).toLocaleDateString()} - ${new Date((backtest as any).request.end_date).toLocaleDateString()}`
                        : backtest.start_date && backtest.end_date
                        ? `${new Date(backtest.start_date).toLocaleDateString()} - ${new Date(backtest.end_date).toLocaleDateString()}`
                        : 'Date not available'}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge
                      variant={
                        backtest.status === 'completed' ? 'success' :
                        backtest.status === 'failed' ? 'error' :
                        'warning'
                      }
                    >
                      {backtest.status}
                    </Badge>
                    {backtest.created_at && (
                      <p className="text-sm text-gray-600 mt-1">
                        {formatDistanceToNow(new Date(backtest.created_at), { addSuffix: true })}
                      </p>
                    )}
                  </div>
                </div>

                {backtest.metrics && (
                  <div className="mt-4 grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-gray-600">Return</div>
                      <div className={`font-medium ${
                        backtest.metrics.total_return >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        {formatPercent(backtest.metrics.total_return)}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-600">Sharpe</div>
                      <div className="font-medium">
                        {backtest.metrics.sharpe_ratio?.toFixed(2) || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-600">Max DD</div>
                      <div className="font-medium text-red-600">
                        {formatPercent(backtest.metrics.max_drawdown)}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-600">Trades</div>
                      <div className="font-medium">{backtest.total_trades}</div>
                    </div>
                  </div>
                )}

                <div className="mt-4 flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setCurrentBacktestId(backtest.backtest_id);
                      setSelectedTab('results');
                    }}
                  >
                    View Results
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleDeleteBacktest(backtest.backtest_id)}
                    disabled={deleteBacktest.isPending}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    {deleteBacktest.isPending ? 'Deleting...' : 'Delete'}
                  </Button>
                </div>
              </Card>
            ))
          ) : (
            <Card>
              <div className="text-center text-gray-600 py-12">
                No backtest history available
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
