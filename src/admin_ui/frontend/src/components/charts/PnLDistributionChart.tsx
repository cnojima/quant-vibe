import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';

interface PnLDistributionData {
  range: string;
  count: number;
}

interface PnLDistributionChartProps {
  data: PnLDistributionData[];
}

export function PnLDistributionChart({ data }: PnLDistributionChartProps) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="range" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip />
        <Legend />
        <Bar dataKey="count" name="Number of Trades">
          {data.map((entry, index) => {
            // Color bars based on P&L range (green for positive, red for negative)
            // Extract the starting value from the range (e.g., "$150 to $200" -> 150)
            const match = entry.range.match(/\$(-?\d+)/);
            const startValue = match ? parseInt(match[1], 10) : 0;
            const isPositive = startValue >= 0;
            return <Cell key={`cell-${index}`} fill={isPositive ? '#10b981' : '#ef4444'} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
