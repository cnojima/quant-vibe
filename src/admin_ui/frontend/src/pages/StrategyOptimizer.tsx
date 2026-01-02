import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useStrategies,
  useRunOptimization,
  useOptimizationStatus,
  useOptimizationResults,
  useOptimizationHistory,
  useDeleteOptimization,
} from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { InfoIcon } from '../components/common/InfoIcon';
import { formatDistanceToNow } from 'date-fns';
import {
  getLastNMonthsEST,
  getLastNYearsEST,
} from '../utils/dateUtils';

export function StrategyOptimizer() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>('');
  const [trainStartDate, setTrainStartDate] = useState<string>('');
  const [trainEndDate, setTrainEndDate] = useState<string>('');
  const [testStartDate, setTestStartDate] = useState<string>('');
  const [testEndDate, setTestEndDate] = useState<string>('');
  const [initialCapital, setInitialCapital] = useState<number>(100000);
  const [optimizationType, setOptimizationType] = useState<'grid_search' | 'walk_forward'>('grid_search');
  const [currentOptimizationId, setCurrentOptimizationId] = useState<string | null>(null);
  const [selectedTab, setSelectedTab] = useState<'run' | 'results' | 'history'>('run');

  const queryClient = useQueryClient();
  const { data: strategies, isLoading: strategiesLoading } = useStrategies();
  const runOptimization = useRunOptimization();
  const { data: optimizationStatus } = useOptimizationStatus(currentOptimizationId);
  const { data: optimizationResults } = useOptimizationResults(currentOptimizationId, optimizationStatus?.status);
  const { data: history } = useOptimizationHistory(50);
  const deleteOptimization = useDeleteOptimization();

  // Invalidate history when optimization completes
  useEffect(() => {
    if (optimizationStatus?.status === 'completed' || optimizationStatus?.status === 'failed') {
      queryClient.invalidateQueries({ queryKey: ['optimization-history'] });
    }
  }, [optimizationStatus?.status, queryClient]);

  const handleRunOptimization = async () => {
    if (!selectedStrategy || !trainStartDate || !trainEndDate) {
      alert('Please fill in all required fields');
      return;
    }

    try {
      const result = await runOptimization.mutateAsync({
        strategy_name: selectedStrategy,
        train_start_date: trainStartDate,
        train_end_date: trainEndDate,
        test_start_date: testStartDate || undefined,
        test_end_date: testEndDate || undefined,
        initial_capital: initialCapital,
        optimization_type: optimizationType,
      });

      setCurrentOptimizationId(result.optimization_id);
      setSelectedTab('results');
    } catch (error) {
      console.error('Failed to run optimization:', error);
      alert('Failed to start optimization. Please check the console for details.');
    }
  };

  const handleDeleteOptimization = async (optimizationId: string) => {
    if (!confirm('Are you sure you want to delete this optimization? This action cannot be undone.')) {
      return;
    }

    try {
      await deleteOptimization.mutateAsync(optimizationId);
    } catch (error) {
      console.error('Failed to delete optimization:', error);
      alert('Failed to delete optimization. Please try again.');
    }
  };

  const formatPercent = (value: number | undefined | null) => {
    if (value === undefined || value === null || isNaN(value)) {
      return 'N/A';
    }
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Strategy Optimizer</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          Find optimal parameters using grid search and walk-forward analysis
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
            Run Optimization
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
              <h3 className="text-lg font-semibold">Optimization Configuration</h3>
              <InfoIcon
                content="Configure parameter optimization. Grid search tests all parameter combinations. Walk-forward validates robustness across different time periods."
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
                <div className="flex items-center gap-2 mb-1">
                  <label className="label mb-0">Optimization Type</label>
                  <InfoIcon
                    content="Grid Search: Test all parameter combinations on training data. Walk-Forward: Test parameters across multiple time periods to validate robustness and prevent overfitting."
                    placement="right"
                  />
                </div>
                <select
                  className="input"
                  value={optimizationType}
                  onChange={(e) => setOptimizationType(e.target.value as 'grid_search' | 'walk_forward')}
                >
                  <option value="grid_search">Grid Search</option>
                  <option value="walk_forward">Walk-Forward Analysis</option>
                </select>
              </div>

              <div>
                <label className="label">Training Start Date</label>
                <input
                  type="date"
                  className="input"
                  value={trainStartDate}
                  onChange={(e) => setTrainStartDate(e.target.value)}
                />
              </div>

              <div>
                <label className="label">Training End Date</label>
                <input
                  type="date"
                  className="input"
                  value={trainEndDate}
                  onChange={(e) => setTrainEndDate(e.target.value)}
                />
              </div>

              {optimizationType === 'grid_search' && (
                <>
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <label className="label mb-0">Test Start Date (Optional)</label>
                      <InfoIcon
                        content="Out-of-sample test period to validate optimal parameters. Leave empty to use only training data."
                        placement="right"
                      />
                    </div>
                    <input
                      type="date"
                      className="input"
                      value={testStartDate}
                      onChange={(e) => setTestStartDate(e.target.value)}
                    />
                  </div>

                  <div>
                    <label className="label">Test End Date (Optional)</label>
                    <input
                      type="date"
                      className="input"
                      value={testEndDate}
                      onChange={(e) => setTestEndDate(e.target.value)}
                    />
                  </div>
                </>
              )}

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <label className="label mb-0">Initial Capital</label>
                  <InfoIcon
                    content="Starting account balance for optimization. All performance metrics are calculated relative to this amount."
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

              <Button
                variant="primary"
                className="w-full"
                onClick={handleRunOptimization}
                disabled={runOptimization.isPending || !selectedStrategy || !trainStartDate || !trainEndDate}
              >
                {runOptimization.isPending ? 'Starting...' : 'Run Optimization'}
              </Button>
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Quick Date Presets</h3>
              <InfoIcon
                content="One-click date range selection for common optimization periods. Training periods should have enough data to find meaningful patterns."
                placement="right"
              />
            </div>
            <div className="space-y-2">
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastNMonthsEST(3);
                  setTrainStartDate(start);
                  setTrainEndDate(end);
                }}
              >
                Last 3 Months (Training)
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start: trainStart, end: trainEnd } = getLastNMonthsEST(5, 2);
                  const { start: testStart, end: testEnd } = getLastNMonthsEST(2);
                  setTrainStartDate(trainStart);
                  setTrainEndDate(trainEnd);
                  setTestStartDate(testStart);
                  setTestEndDate(testEnd);
                }}
              >
                Train: 5-2 months ago, Test: Last 2 months
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start: trainStart, end: trainEnd } = getLastNMonthsEST(12, 3);
                  const { start: testStart, end: testEnd } = getLastNMonthsEST(3);
                  setTrainStartDate(trainStart);
                  setTrainEndDate(trainEnd);
                  setTestStartDate(testStart);
                  setTestEndDate(testEnd);
                }}
              >
                Train: Year (excl. last 3 mo), Test: Last 3 months
              </Button>
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const { start, end } = getLastNYearsEST(1);
                  setTrainStartDate(start);
                  setTrainEndDate(end);
                }}
              >
                Last Year (Training only)
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

            <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded">
              <h4 className="font-medium text-yellow-900 mb-2">About Optimization</h4>
              <ul className="text-sm text-yellow-700 space-y-1">
                <li>• Grid search tests all parameter combinations</li>
                <li>• Results are ranked by Sharpe ratio (risk-adjusted return)</li>
                <li>• Walk-forward prevents overfitting with rolling validation</li>
                <li>• Optimization may take 5-60 minutes depending on parameters</li>
              </ul>
            </div>
          </Card>
        </div>
      )}

      {/* Results Tab */}
      {selectedTab === 'results' && (
        <div>
          {optimizationStatus && optimizationStatus.status !== 'completed' && (
            <>
              <Card className="mb-6">
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <div className="font-medium mb-1">
                      Optimization Status: {optimizationStatus.status}
                    </div>
                    {optimizationStatus.status === 'failed' && optimizationStatus.error && (
                      <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded">
                        <div className="text-sm font-medium text-red-800">Error:</div>
                        <pre className="text-xs text-red-700 mt-1 whitespace-pre-wrap overflow-x-auto">
                          {optimizationStatus.error}
                        </pre>
                      </div>
                    )}
                    {optimizationStatus.current_combination !== undefined && optimizationStatus.total_combinations !== undefined && (
                      <div className="mt-2">
                        <div className="text-sm text-gray-600 mb-1">
                          Testing combination {optimizationStatus.current_combination} of {optimizationStatus.total_combinations} ({optimizationStatus.progress}%)
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div
                            className="bg-blue-600 h-2.5 rounded-full transition-all"
                            style={{ width: `${optimizationStatus.progress}%` }}
                          />
                        </div>

                        {/* Current parameters and metrics */}
                        {optimizationStatus.current_params && (
                          <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded">
                            <div className="text-xs font-medium text-blue-900 mb-2">Current Test:</div>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                              {Object.entries(optimizationStatus.current_params).slice(0, 8).map(([key, value]) => (
                                <div key={key}>
                                  <span className="text-blue-700">{key}:</span>{' '}
                                  <span className="font-semibold text-blue-900">
                                    {typeof value === 'number' ? value.toFixed(2) : String(value)}
                                  </span>
                                </div>
                              ))}
                            </div>
                            {optimizationStatus.current_error && (
                              <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs">
                                <span className="text-red-700 font-medium">Error:</span>{' '}
                                <span className="text-red-900">{optimizationStatus.current_error}</span>
                              </div>
                            )}
                            {optimizationStatus.current_metrics && (
                              <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs pt-2 border-t border-blue-300">
                                {optimizationStatus.current_metrics.sharpe_ratio !== undefined && (
                                  <div>
                                    <span className="text-blue-700">Sharpe:</span>{' '}
                                    <span className="font-semibold text-blue-900">
                                      {optimizationStatus.current_metrics.sharpe_ratio.toFixed(2)}
                                    </span>
                                  </div>
                                )}
                                {optimizationStatus.current_metrics.total_return !== undefined && (
                                  <div>
                                    <span className="text-blue-700">Return:</span>{' '}
                                    <span className="font-semibold text-blue-900">
                                      {formatPercent(optimizationStatus.current_metrics.total_return)}
                                    </span>
                                  </div>
                                )}
                                {optimizationStatus.current_metrics.win_rate !== undefined && (
                                  <div>
                                    <span className="text-blue-700">Win Rate:</span>{' '}
                                    <span className="font-semibold text-blue-900">
                                      {optimizationStatus.current_metrics.win_rate.toFixed(1)}%
                                    </span>
                                  </div>
                                )}
                                {optimizationStatus.current_metrics.num_trades !== undefined && (
                                  <div>
                                    <span className="text-blue-700">Trades:</span>{' '}
                                    <span className="font-semibold text-blue-900">
                                      {optimizationStatus.current_metrics.num_trades}
                                    </span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {optimizationStatus.progress !== undefined && optimizationStatus.current_combination === undefined && (
                      <div className="mt-2">
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div
                            className="bg-blue-600 h-2.5 rounded-full transition-all"
                            style={{ width: `${optimizationStatus.progress}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                  {optimizationStatus.status === 'running' && (
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                  )}
                </div>
              </Card>

              {/* Optimization Logs */}
              {optimizationStatus.logs && optimizationStatus.logs.length > 0 && (
                <Card className="mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-lg font-semibold">Optimization Progress Log</h3>
                    <InfoIcon
                      content="Real-time log messages from the optimization process. Shows what the optimizer is currently doing."
                      placement="right"
                    />
                  </div>
                  <div className="bg-gray-900 text-gray-100 rounded p-4 font-mono text-xs max-h-96 overflow-y-auto">
                    {optimizationStatus.logs.map((log: any, idx: number) => (
                      <div key={idx} className="mb-1">
                        <span className="text-gray-500">[{new Date(log.timestamp).toLocaleTimeString()}]</span>{' '}
                        <span className={
                          log.level === 'ERROR' ? 'text-red-400' :
                          log.level === 'WARNING' ? 'text-yellow-400' :
                          'text-green-400'
                        }>
                          [{log.level}]
                        </span>{' '}
                        <span className="text-gray-200">{log.message}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}

          {optimizationResults && (
            <>
              {/* Best Parameters */}
              <Card className="mb-6">
                <div className="flex items-center gap-2 mb-4">
                  <h3 className="text-lg font-semibold">Best Parameters</h3>
                  <InfoIcon
                    content="Optimal parameter combination found by the optimization. These parameters achieved the highest Sharpe ratio (risk-adjusted return) during training."
                    placement="right"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <div className="text-sm text-gray-600">Best Sharpe Ratio</div>
                    <div className="text-2xl font-bold text-blue-600">
                      {optimizationResults.best_sharpe?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Best Return</div>
                    <div className={`text-2xl font-bold ${
                      (optimizationResults.best_return || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {formatPercent(optimizationResults.best_return || 0)}
                    </div>
                  </div>
                </div>

                {optimizationResults.best_params && (
                  <div className="p-4 bg-gray-50 rounded border border-gray-200">
                    <div className="font-medium text-gray-900 mb-2">Optimal Parameter Values:</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {Object.entries(optimizationResults.best_params).map(([key, value]) => (
                        <div key={key}>
                          <div className="text-xs text-gray-600">
                            {key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                          </div>
                          <div className="font-semibold text-gray-900">
                            {typeof value === 'number' ? value.toFixed(2) : String(value)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              {/* Top Results */}
              {optimizationResults.top_results && optimizationResults.top_results.length > 0 && (
                <Card className="mb-6">
                  <div className="flex items-center gap-2 mb-4">
                    <h3 className="text-lg font-semibold">Top 10 Parameter Combinations</h3>
                    <InfoIcon
                      content="Best performing parameter combinations ranked by Sharpe ratio. Compare these to identify robust parameter ranges that work well."
                      placement="right"
                    />
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead>
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rank</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sharpe</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Return</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Win Rate</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Max DD</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Trades</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {optimizationResults.top_results.slice(0, 10).map((result: any, idx: number) => (
                          <tr key={idx} className="hover:bg-gray-50">
                            <td className="px-4 py-3 text-sm font-medium">#{idx + 1}</td>
                            <td className="px-4 py-3 text-sm font-semibold text-blue-600">
                              {result.sharpe_ratio?.toFixed(2) || 'N/A'}
                            </td>
                            <td className={`px-4 py-3 text-sm font-medium ${
                              result.total_return >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {formatPercent(result.total_return)}
                            </td>
                            <td className="px-4 py-3 text-sm">
                              {result.win_rate?.toFixed(1)}%
                            </td>
                            <td className="px-4 py-3 text-sm text-red-600">
                              {formatPercent(result.max_drawdown)}
                            </td>
                            <td className="px-4 py-3 text-sm">
                              {result.num_trades}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {/* Walk-Forward Summary */}
              {optimizationResults.walk_forward_summary && (
                <Card>
                  <div className="flex items-center gap-2 mb-4">
                    <h3 className="text-lg font-semibold">Walk-Forward Analysis Summary</h3>
                    <InfoIcon
                      content="Out-of-sample validation across multiple time periods. Low degradation indicates robust parameters that work in different market conditions."
                      placement="right"
                    />
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-sm text-gray-600">Periods Tested</div>
                      <div className="text-xl font-bold">
                        {optimizationResults.walk_forward_summary.num_periods}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Avg OOS Sharpe</div>
                      <div className="text-xl font-bold text-blue-600">
                        {optimizationResults.walk_forward_summary.avg_out_of_sample_sharpe?.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Avg OOS Return</div>
                      <div className="text-xl font-bold text-green-600">
                        {formatPercent(optimizationResults.walk_forward_summary.avg_out_of_sample_return)}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Sharpe Degradation</div>
                      <div className={`text-xl font-bold ${
                        optimizationResults.walk_forward_summary.avg_sharpe_degradation < 30
                          ? 'text-green-600'
                          : optimizationResults.walk_forward_summary.avg_sharpe_degradation < 50
                          ? 'text-yellow-600'
                          : 'text-red-600'
                      }`}>
                        {formatPercent(optimizationResults.walk_forward_summary.avg_sharpe_degradation)}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded">
                    <p className="text-sm text-blue-700">
                      <strong>Interpretation:</strong> Sharpe degradation below 50% indicates good robustness.
                      Lower degradation means parameters perform consistently across different time periods.
                    </p>
                  </div>
                </Card>
              )}
            </>
          )}

          {!optimizationResults && !optimizationStatus && (
            <Card>
              <div className="text-center text-gray-600 py-12">
                No optimization results available. Run an optimization to see results.
              </div>
            </Card>
          )}
        </div>
      )}

      {/* History Tab */}
      {selectedTab === 'history' && (
        <div className="space-y-4">
          {history && history.length > 0 ? (
            history.map((opt: any) => (
              <Card key={opt.optimization_id}>
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-semibold text-lg">{opt.request?.strategy_name || 'Unknown Strategy'}</h4>
                    <p className="text-sm text-gray-600">
                      {opt.request?.optimization_type === 'walk_forward' ? 'Walk-Forward Analysis' : 'Grid Search'}
                    </p>
                    <p className="text-sm text-gray-600 mt-1">
                      Training: {opt.request?.train_start_date && new Date(opt.request.train_start_date).toLocaleDateString()} - {opt.request?.train_end_date && new Date(opt.request.train_end_date).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge
                      variant={
                        opt.status === 'completed' ? 'success' :
                        opt.status === 'failed' ? 'error' :
                        'warning'
                      }
                    >
                      {opt.status}
                    </Badge>
                    {opt.created_at && (
                      <p className="text-sm text-gray-600 mt-1">
                        {formatDistanceToNow(new Date(opt.created_at), { addSuffix: true })}
                      </p>
                    )}
                  </div>
                </div>

                <div className="mt-4 flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setCurrentOptimizationId(opt.optimization_id);
                      setSelectedTab('results');
                    }}
                    disabled={opt.status !== 'completed'}
                  >
                    View Results
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleDeleteOptimization(opt.optimization_id)}
                    disabled={deleteOptimization.isPending}
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    {deleteOptimization.isPending ? 'Deleting...' : 'Delete'}
                  </Button>
                </div>
              </Card>
            ))
          ) : (
            <Card>
              <div className="text-center text-gray-600 py-12">
                No optimization history available
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
