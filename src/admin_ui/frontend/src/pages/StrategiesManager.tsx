import { useState } from 'react';
import { useLiveStrategies, useToggleLiveStrategy } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import type { StrategyInfo } from '../types/api';

export function StrategiesManager() {
  const { data: strategiesData, isLoading } = useLiveStrategies();
  const toggleStrategy = useToggleLiveStrategy();
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-600">Loading strategies...</div>
      </div>
    );
  }

  const strategies = strategiesData?.strategies || [];

  const handleToggle = async (strategyName: string, currentlyEnabled: boolean) => {
    try {
      await toggleStrategy.mutateAsync({
        strategyName,
        enabled: !currentlyEnabled,
      });
    } catch (error) {
      console.error('Failed to toggle strategy:', error);
      alert(`Failed to ${currentlyEnabled ? 'disable' : 'enable'} strategy`);
    }
  };

  const toggleExpand = (strategyName: string) => {
    setExpandedStrategy(expandedStrategy === strategyName ? null : strategyName);
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Strategy Management</h1>
        <p className="text-gray-600 mt-2">
          Enable, disable, and configure trading strategies
        </p>
      </div>

      {/* Warning Banner */}
      <Card className="mb-6 bg-yellow-50 border-yellow-200">
        <div className="flex items-start gap-3">
          <svg className="w-6 h-6 text-yellow-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="font-semibold text-yellow-900">Restart Required</h3>
            <p className="text-sm text-yellow-800 mt-1">
              Changes to strategy configuration require restarting the live_trading service to take effect.
              Use the Services page to restart the service after making changes.
            </p>
          </div>
        </div>
      </Card>

      {/* Strategy List */}
      <div className="space-y-4">
        {strategies.map((strategy: StrategyInfo) => (
          <Card key={strategy.name} className={strategy.enabled ? 'border-green-200 bg-green-50' : ''}>
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-semibold text-gray-900">
                    {strategy.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </h3>
                  <Badge variant={strategy.enabled ? 'success' : 'default'}>
                    {strategy.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
                <p className="text-sm text-gray-600 mb-3">{strategy.description}</p>

                {/* Toggle Button */}
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => handleToggle(strategy.name, strategy.enabled)}
                    disabled={toggleStrategy.isPending}
                    className={`px-4 py-2 rounded-md font-medium text-sm transition-colors ${
                      strategy.enabled
                        ? 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-400'
                        : 'bg-green-600 text-white hover:bg-green-700 disabled:bg-green-400'
                    }`}
                  >
                    {toggleStrategy.isPending ? 'Updating...' : strategy.enabled ? 'Disable' : 'Enable'}
                  </button>

                  <button
                    onClick={() => toggleExpand(strategy.name)}
                    className="text-sm text-blue-600 hover:text-blue-800"
                  >
                    {expandedStrategy === strategy.name ? 'Hide Parameters' : 'Show Parameters'}
                  </button>
                </div>

                {/* Parameters (Expanded) */}
                {expandedStrategy === strategy.name && (
                  <div className="mt-4 pt-4 border-t border-gray-200">
                    <h4 className="text-sm font-semibold text-gray-700 mb-3">Parameters:</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {Object.entries(strategy.params).map(([key, value]) => (
                        <div key={key} className="bg-white p-3 rounded border border-gray-200">
                          <div className="text-xs text-gray-500 mb-1">
                            {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </div>
                          <div className="text-sm font-medium text-gray-900">
                            {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Card>
        ))}

        {strategies.length === 0 && (
          <Card>
            <div className="text-center text-gray-600 py-8">
              No strategies available
            </div>
          </Card>
        )}
      </div>

      {/* Info Footer */}
      <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
        <h4 className="font-semibold text-blue-900 mb-2">About Strategies</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Enabled strategies will be loaded when the live_trading service starts</li>
          <li>• Each strategy can have multiple instances with different parameters</li>
          <li>• Strategies run independently and can trade concurrently</li>
          <li>• Risk limits apply across all strategies combined</li>
        </ul>
      </div>
    </div>
  );
}
