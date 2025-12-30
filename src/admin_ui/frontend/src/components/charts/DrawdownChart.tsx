import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface DrawdownData {
  timestamp: string;
  drawdown: number;
}

interface DrawdownChartProps {
  data: DrawdownData[];
}

export function DrawdownChart({ data }: DrawdownChartProps) {
  const formatPercent = (value: number) => {
    return `${value.toFixed(2)}%`;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <defs>
          <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatDate}
          tick={{ fontSize: 12 }}
        />
        <YAxis
          tickFormatter={formatPercent}
          tick={{ fontSize: 12 }}
          domain={['dataMin', 0]}
        />
        <Tooltip
          formatter={(value: number) => [formatPercent(value), 'Drawdown']}
          labelFormatter={formatDate}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke="#ef4444"
          fill="url(#drawdownGradient)"
          name="Drawdown %"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
