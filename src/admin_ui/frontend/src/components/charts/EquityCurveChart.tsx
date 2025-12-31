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

interface TradeData {
  entry_time: string;
  exit_time: string;
  pnl?: number;
}

interface EquityCurveChartProps {
  data: EquityCurveData[];
  initialCapital?: number;
  underlyingData?: UnderlyingBar[];
  trades?: TradeData[];
}

export function EquityCurveChart({ data, underlyingData = [], trades = [] }: EquityCurveChartProps) {
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

  const formatPrice = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
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
  const tradeMarkers = trades.flatMap(trade => {
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
          type: 'entry' as const,
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
          type: 'exit' as const,
          pnl: trade.pnl,
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

  return (
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
        <Tooltip
          formatter={(value: any, name: string) => {
            if (value === null || value === undefined) return ['N/A', name];
            const numValue = typeof value === 'number' ? value : parseFloat(value);
            if (isNaN(numValue)) return ['N/A', name];
            if (name === 'Portfolio Value') return [formatCurrency(numValue), name];
            if (name === 'SPX Price') return [formatPrice(numValue), name];
            return [numValue, name];
          }}
          labelFormatter={formatDate}
        />
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
        {/* Trade Entry Points - Green Circles */}
        {tradeMarkers
          .filter(marker => marker.type === 'entry')
          .map((marker, index) => (
            <ReferenceDot
              key={`entry-${index}`}
              yAxisId="left"
              x={marker.timestamp}
              y={marker.portfolioValue}
              r={6}
              fill="#10b981"
              stroke="#ffffff"
              strokeWidth={2}
            />
          ))}
        {/* Trade Exit Points - Colored by P&L */}
        {tradeMarkers
          .filter(marker => marker.type === 'exit')
          .map((marker, index) => {
            const isProfit = (marker.pnl ?? 0) >= 0;
            return (
              <ReferenceDot
                key={`exit-${index}`}
                yAxisId="left"
                x={marker.timestamp}
                y={marker.portfolioValue}
                r={6}
                fill={isProfit ? '#22c55e' : '#ef4444'}
                stroke="#ffffff"
                strokeWidth={2}
              />
            );
          })}
      </LineChart>
    </ResponsiveContainer>
  );
}
