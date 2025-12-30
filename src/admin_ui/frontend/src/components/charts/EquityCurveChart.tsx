import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface EquityCurveData {
  timestamp: string;
  value: number;
}

interface EquityCurveChartProps {
  data: EquityCurveData[];
  initialCapital?: number;
}

export function EquityCurveChart({ data }: EquityCurveChartProps) {
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

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatDate}
          tick={{ fontSize: 12 }}
        />
        <YAxis
          tickFormatter={formatCurrency}
          tick={{ fontSize: 12 }}
          domain={['dataMin', 'dataMax']}
        />
        <Tooltip
          formatter={(value: number) => [formatCurrency(value), 'Portfolio Value']}
          labelFormatter={formatDate}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          name="Portfolio Value"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
