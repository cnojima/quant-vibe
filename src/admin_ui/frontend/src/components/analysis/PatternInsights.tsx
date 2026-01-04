import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Card } from '../common/Card';
import { Patterns } from '../../types/api';

interface PatternInsightsProps {
  patterns: Patterns;
}

const COLORS = ['#00C49F', '#FFBB28', '#FF8042', '#0088FE', '#FF6B9D', '#8884d8'];

export const PatternInsights: React.FC<PatternInsightsProps> = ({ patterns }) => {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatPercentage = (value: number) => {
    return `${(value * 100).toFixed(1)}%`;
  };

  // Entry Timing Pattern
  const renderEntryTiming = () => {
    if (!patterns.entry_timing) return null;

    const chartData = Object.entries(patterns.entry_timing.hourly_stats)
      .map(([hour, stats]) => ({
        hour: `${hour}:00`,
        avg_pnl: stats.avg_pnl,
        win_rate: stats.win_rate * 100,
        count: stats.count,
      }))
      .sort((a, b) => parseInt(a.hour) - parseInt(b.hour));

    return (
      <div className="md:col-span-1">
        <Card>
          <h4 className="text-lg font-semibold mb-2">Entry Timing Analysis</h4>
          <p className="text-sm text-gray-600 mb-4">
            Best Hour: {patterns.entry_timing.best_hour}:00 | Worst Hour:{' '}
            {patterns.entry_timing.worst_hour}:00
          </p>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip
                formatter={(value: any, name: string) => {
                  if (name === 'avg_pnl') return formatCurrency(value);
                  if (name === 'win_rate') return `${value.toFixed(1)}%`;
                  return value;
                }}
              />
              <Legend />
              <Bar yAxisId="left" dataKey="avg_pnl" fill="#8884d8" name="Avg P&L" />
              <Bar yAxisId="right" dataKey="win_rate" fill="#82ca9d" name="Win Rate %" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    );
  };

  // Exit Reason Pattern
  const renderExitReasons = () => {
    if (!patterns.exit_reasons) return null;

    const pieData = Object.entries(patterns.exit_reasons.exit_reason_counts).map(
      ([reason, count]) => ({
        name: reason.replace(/_/g, ' '),
        value: count,
      })
    );

    const winRates = [
      {
        reason: 'Profit Target',
        win_rate: patterns.exit_reasons.profit_target_win_rate,
        avg_pnl:
          patterns.exit_reasons.exit_reason_avg_pnl['profit_target'] ||
          patterns.exit_reasons.exit_reason_avg_pnl['profit target'] ||
          0,
      },
      {
        reason: 'Stop Loss',
        win_rate: patterns.exit_reasons.stop_loss_win_rate,
        avg_pnl:
          patterns.exit_reasons.exit_reason_avg_pnl['stop_loss'] ||
          patterns.exit_reasons.exit_reason_avg_pnl['stop loss'] ||
          0,
      },
      {
        reason: 'Expiration',
        win_rate: patterns.exit_reasons.expiration_win_rate,
        avg_pnl: patterns.exit_reasons.exit_reason_avg_pnl['expiration'] || 0,
      },
      {
        reason: 'Trailing Stop',
        win_rate: patterns.exit_reasons.trailing_stop_win_rate,
        avg_pnl:
          patterns.exit_reasons.exit_reason_avg_pnl['trailing_stop'] ||
          patterns.exit_reasons.exit_reason_avg_pnl['trailing stop'] ||
          0,
      },
    ].filter((item) => item.win_rate > 0 || item.avg_pnl !== 0);

    return (
      <div className="md:col-span-1">
        <Card>
          <h4 className="text-lg font-semibold mb-2">Exit Reason Performance</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-600 mb-2">Trade Distribution</p>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    outerRadius={60}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {pieData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div>
              <p className="text-sm text-gray-600 mb-2">Win Rates</p>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-2 py-1 text-left font-medium text-gray-700">Reason</th>
                      <th className="px-2 py-1 text-right font-medium text-gray-700">Win Rate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {winRates.map((row) => (
                      <tr key={row.reason}>
                        <td className="px-2 py-1">{row.reason}</td>
                        <td className="px-2 py-1 text-right">{formatPercentage(row.win_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </Card>
      </div>
    );
  };

  // DTE Performance
  const renderDTEPerformance = () => {
    if (!patterns.dte_performance || !patterns.dte_performance.dte_buckets) return null;

    const chartData = Object.entries(patterns.dte_performance.dte_buckets).map(
      ([range, stats]) => ({
        range,
        avg_pnl: stats.avg_pnl,
        win_rate: stats.win_rate * 100,
        count: stats.count,
      })
    );

    if (chartData.length === 0) return null;

    return (
      <div className="md:col-span-1">
        <Card>
          <h4 className="text-lg font-semibold mb-2">Days to Expiration (DTE) Performance</h4>
          <p className="text-sm text-gray-600 mb-4">
            Optimal DTE Range: {patterns.dte_performance.optimal_dte_range}
          </p>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="range" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip
                formatter={(value: any, name: string) => {
                  if (name === 'avg_pnl') return formatCurrency(value);
                  if (name === 'win_rate') return `${value.toFixed(1)}%`;
                  return value;
                }}
              />
              <Legend />
              <Bar yAxisId="left" dataKey="avg_pnl" fill="#8884d8" name="Avg P&L" />
              <Bar yAxisId="right" dataKey="win_rate" fill="#82ca9d" name="Win Rate %" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    );
  };

  // Strike Selection
  const renderStrikeSelection = () => {
    if (!patterns.strike_selection || !patterns.strike_selection.otm_pct_buckets) return null;

    const chartData = Object.entries(patterns.strike_selection.otm_pct_buckets).map(
      ([range, stats]) => ({
        range,
        avg_pnl: stats.avg_pnl,
        win_rate: stats.win_rate * 100,
        count: stats.count,
      })
    );

    if (chartData.length === 0) return null;

    return (
      <div className="md:col-span-1">
        <Card>
          <h4 className="text-lg font-semibold mb-2">Strike Selection (OTM %) Performance</h4>
          <p className="text-sm text-gray-600 mb-4">
            Optimal OTM %: {patterns.strike_selection.optimal_otm_pct.toFixed(1)}%
          </p>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="range" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <Tooltip
                formatter={(value: any, name: string) => {
                  if (name === 'avg_pnl') return formatCurrency(value);
                  if (name === 'win_rate') return `${value.toFixed(1)}%`;
                  return value;
                }}
              />
              <Legend />
              <Bar yAxisId="left" dataKey="avg_pnl" fill="#8884d8" name="Avg P&L" />
              <Bar yAxisId="right" dataKey="win_rate" fill="#82ca9d" name="Win Rate %" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    );
  };

  const hasPatterns =
    patterns.entry_timing ||
    patterns.exit_reasons ||
    patterns.dte_performance ||
    patterns.strike_selection;

  if (!hasPatterns) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-2">Pattern Analysis</h3>
        <p className="text-gray-600">
          No patterns identified. More trades may be needed for pattern analysis.
        </p>
      </Card>
    );
  }

  return (
    <div className="mb-4">
      <h3 className="text-xl font-semibold mb-4">Pattern Analysis</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {renderEntryTiming()}
        {renderExitReasons()}
        {renderDTEPerformance()}
        {renderStrikeSelection()}
      </div>
    </div>
  );
};
