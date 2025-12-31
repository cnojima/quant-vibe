import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

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

interface EquityCurveChartProps {
  data: EquityCurveData[];
  initialCapital?: number;
  underlyingData?: UnderlyingBar[];
}

export function EquityCurveChart({ data, underlyingData = [] }: EquityCurveChartProps) {
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

  // Create a timestamp lookup map for faster matching
  const underlyingMap = new Map<string, number>();
  underlyingData.forEach(bar => {
    // Normalize timestamp to ISO string without milliseconds
    const normalizedTimestamp = new Date(bar.timestamp).toISOString();
    underlyingMap.set(normalizedTimestamp, bar.close);
  });

  // Merge equity curve and underlying data by timestamp
  const mergedData = data.map(equityPoint => {
    // Normalize timestamp to ISO string without milliseconds
    const normalizedTimestamp = new Date(equityPoint.timestamp).toISOString();
    const underlyingPrice = underlyingMap.get(normalizedTimestamp) || null;

    return {
      timestamp: equityPoint.timestamp,
      portfolioValue: equityPoint.value,
      underlyingPrice: underlyingPrice,
    };
  });

  // Debug: Check if we have underlying data
  const hasUnderlyingData = mergedData.some(d => d.underlyingPrice !== null);
  const matchedCount = mergedData.filter(d => d.underlyingPrice !== null).length;

  console.log('EquityCurveChart - Has underlying data:', hasUnderlyingData);
  console.log('EquityCurveChart - Underlying data points:', underlyingData.length);
  console.log('EquityCurveChart - Equity data points:', data.length);
  console.log('EquityCurveChart - Matched data points:', matchedCount);

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
          formatter={(value: number | null, name: string) => {
            if (value === null) return ['N/A', name];
            if (name === 'Portfolio Value') return [formatCurrency(value), name];
            if (name === 'SPX Price') return [formatPrice(value), name];
            return [value, name];
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
            strokeDasharray="5 5"
            connectNulls={false}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
