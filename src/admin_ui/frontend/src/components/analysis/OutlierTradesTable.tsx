import React, { useState } from 'react';
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';
import { Card } from '../common/Card';
import { Badge } from '../common/Badge';
import { TradeInsight } from '../../types/api';

interface OutlierTradesTableProps {
  title: string;
  trades: TradeInsight[];
  type: 'winner' | 'loser';
}

const OutlierRow: React.FC<{ trade: TradeInsight; type: 'winner' | 'loser' }> = ({
  trade,
  type,
}) => {
  const [open, setOpen] = useState(false);

  const getGeneralizationColor = (potential: string): 'success' | 'warning' | 'default' => {
    switch (potential) {
      case 'high':
        return 'success';
      case 'medium':
        return 'warning';
      default:
        return 'default';
    }
  };

  const formatPercentage = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer border-b border-gray-200"
        onClick={() => setOpen(!open)}
      >
        <td className="px-4 py-3">
          <button className="p-1">
            {open ? (
              <ChevronUpIcon className="h-5 w-5 text-gray-500" />
            ) : (
              <ChevronDownIcon className="h-5 w-5 text-gray-500" />
            )}
          </button>
        </td>
        <td className="px-4 py-3 text-sm">{trade.trade_id}</td>
        <td
          className={`px-4 py-3 text-sm font-semibold text-right ${
            type === 'winner' ? 'text-green-600' : 'text-red-600'
          }`}
        >
          {formatCurrency(trade.pnl)}
        </td>
        <td className="px-4 py-3 text-sm text-right">{formatPercentage(trade.pnl_pct)}</td>
        <td className="px-4 py-3 text-sm text-right">{trade.std_devs_from_mean.toFixed(2)}σ</td>
        <td className="px-4 py-3">
          <Badge variant={getGeneralizationColor(trade.generalization_potential)} size="sm">
            {trade.generalization_potential}
          </Badge>
        </td>
        <td className="px-4 py-3 text-sm">{trade.key_takeaway}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7} className="px-4 py-4 bg-gray-50">
            <div className="space-y-4">
              <h4 className="font-semibold text-lg mb-3">Trade Analysis Details</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Greeks Analysis */}
                <Card>
                  <h5 className="font-semibold mb-2">Greeks Analysis</h5>
                  <div className="space-y-1 text-sm">
                    <p>
                      <strong>Dominant Factor:</strong> {trade.insights.greeks.dominant_factor}
                    </p>
                    <p>
                      <strong>Delta Contribution:</strong>{' '}
                      {(trade.insights.greeks.delta_contribution * 100).toFixed(1)}%
                    </p>
                    <p>
                      <strong>Theta Contribution:</strong>{' '}
                      {(trade.insights.greeks.theta_contribution * 100).toFixed(1)}%
                    </p>
                    <p>
                      <strong>Vega Contribution:</strong>{' '}
                      {(trade.insights.greeks.vega_contribution * 100).toFixed(1)}%
                    </p>
                    {trade.insights.greeks.theta_decay_total && (
                      <p>
                        <strong>Theta Decay:</strong>{' '}
                        {formatCurrency(trade.insights.greeks.theta_decay_total)}
                      </p>
                    )}
                  </div>
                </Card>

                {/* Market Conditions */}
                <Card>
                  <h5 className="font-semibold mb-2">Market Conditions</h5>
                  <div className="space-y-1 text-sm">
                    <p>
                      <strong>Underlying Move:</strong>{' '}
                      {formatPercentage(trade.insights.market_conditions.underlying_move_pct)}{' '}
                      {trade.insights.market_conditions.underlying_move_direction}
                    </p>
                    <p>
                      <strong>Market Regime:</strong>{' '}
                      {trade.insights.market_conditions.market_regime.replace(/_/g, ' ')}
                    </p>
                    {trade.insights.market_conditions.volatility_change_pct && (
                      <p>
                        <strong>Volatility Change:</strong>{' '}
                        {formatPercentage(trade.insights.market_conditions.volatility_change_pct)}
                      </p>
                    )}
                  </div>
                </Card>

                {/* Strategy Adherence */}
                <Card>
                  <h5 className="font-semibold mb-2">Strategy Adherence</h5>
                  <div className="space-y-1 text-sm">
                    <p>
                      <strong>Within All Rules:</strong>{' '}
                      {trade.insights.strategy_adherence.within_all_rules ? 'Yes' : 'No'}
                    </p>
                    <p>
                      <strong>Entry Quality Score:</strong>{' '}
                      {(trade.insights.strategy_adherence.entry_quality_score * 100).toFixed(0)}%
                    </p>
                    {trade.insights.strategy_adherence.rule_violations.length > 0 && (
                      <div className="mt-2">
                        <p className="font-semibold">Rule Violations:</p>
                        <ul className="list-disc list-inside text-red-600 ml-2">
                          {trade.insights.strategy_adherence.rule_violations.map((v, i) => (
                            <li key={i}>{v}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {trade.insights.strategy_adherence.edge_case_flags.length > 0 && (
                      <div className="mt-2">
                        <p className="font-semibold">Edge Cases:</p>
                        <ul className="list-disc list-inside text-yellow-600 ml-2">
                          {trade.insights.strategy_adherence.edge_case_flags.map((f, i) => (
                            <li key={i}>{f}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </Card>

                {/* Exit Timing */}
                <Card>
                  <h5 className="font-semibold mb-2">Exit Timing</h5>
                  <div className="space-y-1 text-sm">
                    <p>
                      <strong>Exit Reason:</strong> {trade.insights.exit_timing.exit_reason}
                    </p>
                    <p>
                      <strong>Was Optimal:</strong>{' '}
                      {trade.insights.exit_timing.was_optimal ? 'Yes' : 'No'}
                    </p>
                    {trade.insights.exit_timing.profit_captured_pct !== null && (
                      <p>
                        <strong>Profit Captured:</strong>{' '}
                        {trade.insights.exit_timing.profit_captured_pct.toFixed(1)}%
                      </p>
                    )}
                    <p>
                      <strong>Holding Period:</strong>{' '}
                      {(trade.insights.exit_timing.held_pct_of_max_duration * 100).toFixed(1)}% of
                      max duration
                    </p>
                    {trade.insights.exit_timing.timing_notes && (
                      <p className="text-yellow-600 mt-2">
                        <strong>Note:</strong> {trade.insights.exit_timing.timing_notes}
                      </p>
                    )}
                  </div>
                </Card>

                {/* Macro Events */}
                {trade.insights.macro_events && trade.insights.macro_events.length > 0 && (
                  <Card className="md:col-span-2">
                    <h5 className="font-semibold mb-2">Macro Events</h5>
                    {trade.insights.macro_events.map((event, idx) => (
                      <div key={idx} className="mb-2 text-sm">
                        <p>
                          <strong>{event.event_type}:</strong> {event.description}
                        </p>
                        <p className="text-gray-600">
                          {event.proximity_to_trade} (Impact: {event.likely_impact})
                        </p>
                      </div>
                    ))}
                  </Card>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

export const OutlierTradesTable: React.FC<OutlierTradesTableProps> = ({
  title,
  trades,
  type,
}) => {
  if (!trades || trades.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-gray-600">No outlier trades found.</p>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <p className="text-sm text-gray-600 mb-4">
        {trades.length} outlier {type === 'winner' ? 'winning' : 'losing'} trade(s) identified
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">

              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Trade ID
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&L
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&L %
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Std Devs
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Generalization
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Key Takeaway
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {trades.map((trade) => (
              <OutlierRow key={trade.trade_id} trade={trade} type={type} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};
