import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceDot } from 'recharts';

interface EquityCurveData {
  timestamp: string;
  value: number;
}

interface UnderlyingBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OptionLeg {
  option_ticker: string;
  option_type: string;
  strike_price: number;
  action: string; // "BUY" or "SELL"
  quantity: number;
  entry_price: number;
  exit_price?: number;
  expiration_date?: string;
}

interface TradeData {
  entry_time: string;
  exit_time: string;
  pnl?: number;
  spread_type?: string;
  legs?: OptionLeg[];
  entry_trigger?: string;
  exit_reason?: string;
}

interface EquityCurveChartProps {
  data: EquityCurveData[];
  initialCapital?: number;
  underlyingData?: UnderlyingBar[];
  trades?: TradeData[];
}

export function EquityCurveChart({ data, underlyingData = [], trades = [] }: EquityCurveChartProps) {
  const [selectedTradeIndex, setSelectedTradeIndex] = useState<number | null>(null);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const formatDateTime = (dateString: string) => {
    const date = new Date(dateString);
    return {
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
      time: date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    };
  };

  const formatPrice = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  // Custom tooltip component
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload || !payload.length) return null;

    // Find if there's a trade at this timestamp
    const timestamp = label;
    const tradeAtPoint = tradeMarkers.find(m => m.timestamp === timestamp);

    // Parse legs if it's a string (comes from database as JSON string)
    let legs: OptionLeg[] = [];
    if (tradeAtPoint?.trade?.legs) {
      if (typeof tradeAtPoint.trade.legs === 'string') {
        try {
          legs = JSON.parse(tradeAtPoint.trade.legs);
        } catch (e) {
          console.error('Failed to parse legs:', e);
        }
      } else if (Array.isArray(tradeAtPoint.trade.legs)) {
        legs = tradeAtPoint.trade.legs;
      }
    }

    const { date, time } = formatDateTime(timestamp);

    return (
      <div className="bg-white p-3 border border-gray-300 rounded shadow-lg">
        <div className="mb-1">
          <p className="font-semibold text-gray-700">{date}</p>
          <p className="text-xs text-gray-600">{time}</p>
        </div>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: {entry.name === 'Portfolio Value' ? formatCurrency(entry.value) : formatPrice(entry.value)}
          </p>
        ))}
        {tradeAtPoint && tradeAtPoint.trade && (
          <div className="mt-2 pt-2 border-t border-gray-200">
            <p className="font-semibold text-sm text-gray-700 mb-1">
              {tradeAtPoint.type === 'entry' ? '🔵 Trade Entry' : tradeAtPoint.pnl && tradeAtPoint.pnl >= 0 ? '🟢 Trade Exit' : '🔴 Trade Exit'}
            </p>
            {tradeAtPoint.trade.spread_type && (
              <p className="text-xs text-gray-600">Spread: {tradeAtPoint.trade.spread_type}</p>
            )}
            {legs.length > 0 && (
              <div className="text-xs text-gray-600 mt-1">
                {legs.map((leg, idx) => {
                  const action = leg.action || (leg.quantity > 0 ? 'BUY' : 'SELL');
                  const qty = leg.quantity;
                  const strike = leg.strike_price?.toFixed(2) || '0.00';
                  const price = leg.entry_price?.toFixed(2) || '0.00';
                  const optionType = leg.option_type?.toUpperCase() || 'OPTION';
                  return (
                    <div key={idx}>
                      {action} {qty}x {optionType} {strike} @ ${price}
                    </div>
                  );
                })}
              </div>
            )}
            {tradeAtPoint.type === 'entry' && tradeAtPoint.trade.entry_trigger && (
              <p className="text-xs text-gray-600 mt-1">Trigger: {tradeAtPoint.trade.entry_trigger}</p>
            )}
            {tradeAtPoint.type === 'exit' && tradeAtPoint.trade.exit_reason && (
              <p className="text-xs text-gray-600 mt-1">Exit: {tradeAtPoint.trade.exit_reason}</p>
            )}
            {tradeAtPoint.type === 'exit' && tradeAtPoint.pnl !== undefined && (
              <p className={`text-xs font-semibold mt-1 ${tradeAtPoint.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                P&L: {formatCurrency(tradeAtPoint.pnl)}
              </p>
            )}
          </div>
        )}
      </div>
    );
  };

  // Sort and prepare underlying data with timestamps
  const underlyingSorted = underlyingData
    .map(bar => ({
      time: new Date(bar.timestamp).getTime(),
      close: bar.close,
    }))
    .sort((a, b) => a.time - b.time);

  // Merge equity curve and underlying data using efficient nearest-neighbor matching
  // This handles different granularities (1-min equity vs 5-min underlying)
  let underlyingIndex = 0;
  const mergedData = data.map(equityPoint => {
    const equityTime = new Date(equityPoint.timestamp).getTime();

    // If no underlying data, return null price
    if (underlyingSorted.length === 0) {
      return {
        timestamp: equityPoint.timestamp,
        portfolioValue: equityPoint.value,
        underlyingPrice: null,
      };
    }

    // Advance index to the last bar at or before equity time
    while (
      underlyingIndex < underlyingSorted.length - 1 &&
      underlyingSorted[underlyingIndex + 1].time <= equityTime
    ) {
      underlyingIndex++;
    }

    // Get the underlying price if within 10 minutes
    const currentBar = underlyingSorted[underlyingIndex];
    const timeDiff = equityTime - currentBar.time;
    const underlyingPrice = timeDiff >= 0 && timeDiff <= 10 * 60 * 1000
      ? currentBar.close
      : null;

    return {
      timestamp: equityPoint.timestamp,
      portfolioValue: equityPoint.value,
      underlyingPrice,
    };
  });

  // Process trade entry/exit points to match with equity curve data
  const tradeMarkers = trades.flatMap((trade, tradeIndex) => {
    const markers = [];

    // Entry marker
    if (trade.entry_time) {
      const entryTime = new Date(trade.entry_time).getTime();
      const entryPoint = mergedData.find(d =>
        Math.abs(new Date(d.timestamp).getTime() - entryTime) < 60000 // Within 1 minute
      );

      if (entryPoint) {
        markers.push({
          timestamp: entryPoint.timestamp,
          portfolioValue: entryPoint.portfolioValue,
          underlyingPrice: entryPoint.underlyingPrice,
          type: 'entry' as const,
          trade: trade, // Store complete trade data
          tradeIndex: tradeIndex, // Store trade index for selection
        });
      }
    }

    // Exit marker
    if (trade.exit_time) {
      const exitTime = new Date(trade.exit_time).getTime();
      const exitPoint = mergedData.find(d =>
        Math.abs(new Date(d.timestamp).getTime() - exitTime) < 60000 // Within 1 minute
      );

      if (exitPoint) {
        markers.push({
          timestamp: exitPoint.timestamp,
          portfolioValue: exitPoint.portfolioValue,
          underlyingPrice: exitPoint.underlyingPrice,
          type: 'exit' as const,
          pnl: trade.pnl,
          trade: trade, // Store complete trade data
          tradeIndex: tradeIndex, // Store trade index for selection
        });
      }
    }

    return markers;
  });

  // Debug: Check if we have underlying data
  const hasUnderlyingData = mergedData.some(d => d.underlyingPrice !== null);
  const matchedCount = mergedData.filter(d => d.underlyingPrice !== null).length;

  console.log('EquityCurveChart - Has underlying data:', hasUnderlyingData);
  console.log('EquityCurveChart - Underlying data points:', underlyingData.length);
  console.log('EquityCurveChart - Equity data points:', data.length);
  console.log('EquityCurveChart - Matched data points:', matchedCount);
  console.log('EquityCurveChart - Trade markers:', tradeMarkers.length);

  if (underlyingData.length > 0) {
    console.log('EquityCurveChart - Sample underlying bar:', underlyingData[0]);
    console.log('EquityCurveChart - Underlying timestamp (normalized):', new Date(underlyingData[0].timestamp).toISOString());
  }
  if (data.length > 0) {
    console.log('EquityCurveChart - Sample equity point:', data[0]);
    console.log('EquityCurveChart - Equity timestamp (normalized):', new Date(data[0].timestamp).toISOString());
  }
  if (mergedData.length > 0) {
    const firstMatched = mergedData.find(d => d.underlyingPrice !== null);
    if (firstMatched) {
      console.log('EquityCurveChart - First matched point:', firstMatched);
    } else {
      console.log('EquityCurveChart - No matched points found!');
    }
  }

  // Get selected trade data
  const selectedTrade = selectedTradeIndex !== null ? trades[selectedTradeIndex] : null;

  // Parse legs for selected trade
  let selectedLegs: OptionLeg[] = [];
  if (selectedTrade?.legs) {
    if (typeof selectedTrade.legs === 'string') {
      try {
        selectedLegs = JSON.parse(selectedTrade.legs);
      } catch (e) {
        console.error('Failed to parse legs:', e);
      }
    } else if (Array.isArray(selectedTrade.legs)) {
      selectedLegs = selectedTrade.legs;
    }
  }

  // Navigation functions
  const navigateToPrevTrade = useCallback(() => {
    if (trades.length === 0) return;

    if (selectedTradeIndex === null) {
      setSelectedTradeIndex(trades.length - 1);
    } else if (selectedTradeIndex > 0) {
      setSelectedTradeIndex(selectedTradeIndex - 1);
    }
  }, [selectedTradeIndex, trades.length]);

  const navigateToNextTrade = useCallback(() => {
    if (trades.length === 0) return;

    if (selectedTradeIndex === null) {
      setSelectedTradeIndex(0);
    } else if (selectedTradeIndex < trades.length - 1) {
      setSelectedTradeIndex(selectedTradeIndex + 1);
    }
  }, [selectedTradeIndex, trades.length]);

  const navigateToFirstTrade = useCallback(() => {
    if (trades.length > 0) {
      setSelectedTradeIndex(0);
    }
  }, [trades.length]);

  const navigateToLastTrade = useCallback(() => {
    if (trades.length > 0) {
      setSelectedTradeIndex(trades.length - 1);
    }
  }, [trades.length]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Only handle if chart is visible and has trades
      if (trades.length === 0) return;

      switch (event.key) {
        case 'ArrowLeft':
          event.preventDefault();
          navigateToPrevTrade();
          break;
        case 'ArrowRight':
          event.preventDefault();
          navigateToNextTrade();
          break;
        case 'Home':
          event.preventDefault();
          navigateToFirstTrade();
          break;
        case 'End':
          event.preventDefault();
          navigateToLastTrade();
          break;
        case 'Escape':
          event.preventDefault();
          setSelectedTradeIndex(null);
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigateToPrevTrade, navigateToNextTrade, navigateToFirstTrade, navigateToLastTrade, trades.length]);

  return (
    <div>
      {/* Navigation Controls */}
      {trades.length > 0 && (
        <div className="mb-4 flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg p-3">
          <div className="flex items-center gap-2">
            <button
              onClick={navigateToFirstTrade}
              disabled={selectedTradeIndex === 0}
              className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="First Trade (Home)"
            >
              ⏮ First
            </button>
            <button
              onClick={navigateToPrevTrade}
              disabled={selectedTradeIndex === 0}
              className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Previous Trade (←)"
            >
              ◀ Prev
            </button>
            <span className="px-3 py-1.5 text-sm font-medium text-gray-700">
              {selectedTradeIndex !== null ? `Trade ${selectedTradeIndex + 1} of ${trades.length}` : `${trades.length} Trades`}
            </span>
            <button
              onClick={navigateToNextTrade}
              disabled={selectedTradeIndex === trades.length - 1}
              className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Next Trade (→)"
            >
              Next ▶
            </button>
            <button
              onClick={navigateToLastTrade}
              disabled={selectedTradeIndex === trades.length - 1}
              className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Last Trade (End)"
            >
              Last ⏭
            </button>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-xs text-gray-600">
              <kbd className="px-2 py-1 bg-white border border-gray-300 rounded text-xs">←</kbd>
              <kbd className="ml-1 px-2 py-1 bg-white border border-gray-300 rounded text-xs">→</kbd>
              <span className="ml-1">Navigate</span>
              <span className="mx-2">•</span>
              <kbd className="px-2 py-1 bg-white border border-gray-300 rounded text-xs">Esc</kbd>
              <span className="ml-1">Clear</span>
            </div>
            {selectedTradeIndex !== null && (
              <button
                onClick={() => setSelectedTradeIndex(null)}
                className="px-3 py-1.5 text-sm bg-white border border-gray-300 rounded hover:bg-red-50 hover:border-red-300 hover:text-red-600 transition-colors"
                title="Clear Selection (Esc)"
              >
                ✕ Clear
              </button>
            )}
          </div>
        </div>
      )}

      <ResponsiveContainer width="100%" height={400}>
      <LineChart data={mergedData} margin={{ top: 5, right: 60, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatDate}
          tick={{ fontSize: 12 }}
        />
        {/* Left Y-axis for Portfolio Value */}
        <YAxis
          yAxisId="left"
          tickFormatter={formatCurrency}
          tick={{ fontSize: 12 }}
          domain={['dataMin', 'dataMax']}
          label={{ value: 'Portfolio Value', angle: -90, position: 'insideLeft', style: { fontSize: 12 } }}
        />
        {/* Right Y-axis for Underlying Price */}
        <YAxis
          yAxisId="right"
          orientation="right"
          tickFormatter={formatPrice}
          tick={{ fontSize: 12 }}
          domain={['dataMin', 'dataMax']}
          label={{ value: 'SPX Price', angle: 90, position: 'insideRight', style: { fontSize: 12 } }}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend />
        <Line
          yAxisId="left"
          type="monotone"
          dataKey="portfolioValue"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          name="Portfolio Value"
        />
        {hasUnderlyingData && (
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="underlyingPrice"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
            name="SPX Price"
            connectNulls={true}
          />
        )}
        {/* Trade Entry Points - Blue Circles */}
        {tradeMarkers
          .filter(marker => marker.type === 'entry' && marker.underlyingPrice !== null)
          .map((marker, index) => {
            const isSelected = marker.tradeIndex === selectedTradeIndex;
            return (
              <ReferenceDot
                key={`entry-${index}`}
                yAxisId="right"
                x={marker.timestamp}
                y={marker.underlyingPrice ?? undefined}
                r={isSelected ? 12 : 10}
                fill="#3b82f6"
                stroke={isSelected ? "#fbbf24" : "#ffffff"}
                strokeWidth={isSelected ? 4 : 2}
                onClick={() => setSelectedTradeIndex(marker.tradeIndex)}
                style={{ cursor: 'pointer' }}
              />
            );
          })}
        {/* Trade Exit Points - Colored by P&L */}
        {tradeMarkers
          .filter(marker => marker.type === 'exit' && marker.underlyingPrice !== null)
          .map((marker, index) => {
            const isProfit = (marker.pnl ?? 0) >= 0;
            const isSelected = marker.tradeIndex === selectedTradeIndex;
            return (
              <ReferenceDot
                key={`exit-${index}`}
                yAxisId="right"
                x={marker.timestamp}
                y={marker.underlyingPrice ?? undefined}
                r={isSelected ? 12 : 10}
                fill={isProfit ? '#22c55e' : '#ef4444'}
                stroke={isSelected ? "#fbbf24" : "#ffffff"}
                strokeWidth={isSelected ? 4 : 2}
                onClick={() => setSelectedTradeIndex(marker.tradeIndex)}
                style={{ cursor: 'pointer' }}
              />
            );
          })}
      </LineChart>
    </ResponsiveContainer>

    {/* Trade Info Card */}
    {selectedTrade && (
      <div className="mt-4 p-4 bg-white border border-gray-300 rounded-lg shadow-md">
        <div className="flex justify-between items-start mb-3">
          <h3 className="text-lg font-semibold text-gray-800">
            Trade Details
          </h3>
          <button
            onClick={() => setSelectedTradeIndex(null)}
            className="text-gray-500 hover:text-gray-700 font-bold text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {/* Left Column */}
          <div>
            {selectedTrade.spread_type && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Spread Type:</span>
                <p className="text-base text-gray-800">{selectedTrade.spread_type}</p>
              </div>
            )}

            {selectedLegs.length > 0 && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Legs:</span>
                <div className="mt-1 space-y-1">
                  {selectedLegs.map((leg, idx) => {
                    const action = leg.action || (leg.quantity > 0 ? 'BUY' : 'SELL');
                    const qty = leg.quantity;
                    const strike = leg.strike_price?.toFixed(2) || '0.00';
                    const price = leg.entry_price?.toFixed(2) || '0.00';
                    const optionType = leg.option_type?.toUpperCase() || 'OPTION';
                    return (
                      <div key={idx} className="text-sm text-gray-800">
                        <span className={action === 'BUY' ? 'text-blue-600 font-semibold' : 'text-orange-600 font-semibold'}>
                          {action}
                        </span> {qty}x {optionType} {strike} @ ${price}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {selectedTrade.entry_trigger && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Entry Trigger:</span>
                <p className="text-sm text-gray-800">{selectedTrade.entry_trigger}</p>
              </div>
            )}
          </div>

          {/* Right Column */}
          <div>
            {selectedTrade.exit_reason && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Exit Reason:</span>
                <p className="text-sm text-gray-800">{selectedTrade.exit_reason}</p>
              </div>
            )}

            {selectedTrade.pnl !== undefined && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">P&L:</span>
                <p className={`text-lg font-bold ${selectedTrade.pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {formatCurrency(selectedTrade.pnl)}
                </p>
              </div>
            )}

            {selectedTrade.entry_time && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Entry Time:</span>
                <p className="text-sm text-gray-800">
                  {new Date(selectedTrade.entry_time).toLocaleString()}
                </p>
              </div>
            )}

            {selectedTrade.exit_time && (
              <div className="mb-2">
                <span className="text-sm font-semibold text-gray-600">Exit Time:</span>
                <p className="text-sm text-gray-800">
                  {new Date(selectedTrade.exit_time).toLocaleString()}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    )}
  </div>
  );
}
