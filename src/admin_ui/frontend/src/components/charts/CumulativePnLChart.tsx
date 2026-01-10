import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

interface CumulativePnLData {
  timestamp: string;
  cumulativePnL: number;
}

interface CumulativePnLChartProps {
  data: CumulativePnLData[];
}

export function CumulativePnLChart({ data }: CumulativePnLChartProps) {
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

  // Determine if overall P/L is positive or negative
  const finalPnL = data.length > 0 ? data[data.length - 1].cumulativePnL : 0;
  const isPositive = finalPnL >= 0;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <defs>
          <linearGradient id="cumulativePnLGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0.8} />
            <stop offset="95%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0.1} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatDate}
          tick={{ fontSize: 12 }}
        />
        <YAxis
          tickFormatter={formatCurrency}
          tick={{ fontSize: 12 }}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'Cumulative P/L']}
          labelFormatter={formatDate}
        />
        <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
        <Area
          type="monotone"
          dataKey="cumulativePnL"
          stroke={isPositive ? "#10b981" : "#ef4444"}
          fill="url(#cumulativePnLGradient)"
          name="Cumulative P/L"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
