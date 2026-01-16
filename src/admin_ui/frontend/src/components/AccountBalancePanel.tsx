import { useAccountBalance } from '../api/queries';
import { formatDistanceToNow } from 'date-fns';
import { ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/24/solid';

interface AccountBalancePanelProps {
  accountHash: string | null;
  tradingMode: 'real' | 'paper';
  realtime?: boolean;
}

interface BalanceCardProps {
  title: string;
  value: number;
  subtitle?: string;
  change?: number;
  changePercent?: number;
  icon?: string;
  colorClass?: string;
}

function BalanceCard({ title, value, subtitle, change, changePercent, icon, colorClass = 'text-gray-900' }: BalanceCardProps) {
  const formatValue = (val: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(val);
  };

  const formatPercent = (val: number) => {
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(2)}%`;
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2">
            {icon && <span className="text-lg">{icon}</span>}
            <h3 className="text-sm font-medium text-gray-500">{title}</h3>
          </div>
          <p className={`mt-2 text-2xl font-semibold ${colorClass}`}>
            {formatValue(value)}
          </p>
          {change !== undefined && (
            <div className="mt-2 flex items-center space-x-1">
              {change >= 0 ? (
                <ArrowUpIcon className="h-4 w-4 text-green-500" />
              ) : (
                <ArrowDownIcon className="h-4 w-4 text-red-500" />
              )}
              <span className={`text-sm font-medium ${change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {formatValue(Math.abs(change))}
              </span>
              {changePercent !== undefined && (
                <span className={`text-sm ${change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ({formatPercent(changePercent)})
                </span>
              )}
            </div>
          )}
          {subtitle && (
            <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function AccountBalancePanel({ accountHash, tradingMode, realtime = true }: AccountBalancePanelProps) {
  const { data: balanceData, isLoading, error } = useAccountBalance(
    accountHash || '',
    tradingMode,
    realtime && tradingMode === 'real' // Only use realtime for real trading
  );

  if (!accountHash) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-sm text-yellow-800">No account selected. Please select an account above.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
              <div className="h-8 bg-gray-200 rounded w-32"></div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-sm text-red-800">Failed to load account balance. Please try refreshing.</p>
      </div>
    );
  }

  const balance = balanceData?.balance;
  if (!balance) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <p className="text-sm text-gray-600">No balance data available for this account.</p>
      </div>
    );
  }

  // Calculate some derived values
  const portfolioChange = balance.daily_pnl || 0;
  const portfolioChangePercent = balance.portfolio_value > 0
    ? (portfolioChange / balance.portfolio_value) * 100
    : 0;

  const marginUsed = balance.margin_balance || 0;
  const marginPercent = balance.buying_power > 0
    ? (marginUsed / balance.buying_power) * 100
    : 0;

  return (
    <div className="space-y-4">
      {/* Main Balance Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <BalanceCard
          title="Total Account Value"
          value={balance.liquidation_value}
          change={portfolioChange}
          changePercent={portfolioChangePercent}
          subtitle="Cash + Positions"
          icon="💰"
          colorClass="text-gray-900"
        />

        <BalanceCard
          title="Cash Balance"
          value={balance.cash_balance}
          subtitle="Settled cash"
          icon="💵"
        />

        <BalanceCard
          title="Buying Power"
          value={balance.buying_power}
          subtitle="Options buying power"
          icon="🎯"
          colorClass="text-blue-600"
        />

        <BalanceCard
          title="Available Cash"
          value={balance.available_funds}
          subtitle="Available for trading"
          icon="✅"
          colorClass="text-green-600"
        />
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-500">Day P&L</h3>
          <p className={`mt-2 text-xl font-semibold ${balance.daily_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              signDisplay: 'always',
            }).format(balance.daily_pnl)}
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-500">Total P&L</h3>
          <p className={`mt-2 text-xl font-semibold ${balance.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              signDisplay: 'always',
            }).format(balance.total_pnl)}
          </p>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-500">Win Rate</h3>
          <p className="mt-2 text-xl font-semibold text-gray-900">
            {balance.win_rate ? `${(balance.win_rate * 100).toFixed(1)}%` : 'N/A'}
          </p>
          {balance.win_rate && (
            <p className="text-xs text-gray-500 mt-1">
              Sharpe: {balance.sharpe_ratio?.toFixed(2) || 'N/A'}
            </p>
          )}
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-500">Margin Used</h3>
          <p className="mt-2 text-xl font-semibold text-gray-900">
            {new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
            }).format(marginUsed)}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {marginPercent.toFixed(1)}% of buying power
          </p>
        </div>
      </div>

      {/* Additional Account Info */}
      <div className="bg-gray-50 rounded-lg p-3">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center space-x-4">
            <span>
              Long Options: {new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
              }).format(balance.long_option_market_value)}
            </span>
            <span>
              Short Options: {new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
              }).format(balance.short_option_market_value)}
            </span>
            <span>
              Maintenance: {new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
              }).format(balance.maintenance_requirement)}
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <span>
              Source: {balanceData?.source === 'schwab_api' ? '🔄 Live' : '💾 Cached'}
            </span>
            <span>
              Updated: {balance.timestamp ? formatDistanceToNow(new Date(balance.timestamp), { addSuffix: true }) : 'Unknown'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}