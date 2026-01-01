import { useState } from 'react';
import { useBacktestConfig, useLiveConfig, useUpdateBacktestConfig, useUpdateLiveConfig } from '../api/queries';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';

type ConfigType = 'backtest' | 'live';

export function ConfigEditor() {
  const [selectedConfig, setSelectedConfig] = useState<ConfigType>('backtest');
  const [editMode, setEditMode] = useState(false);
  const [editedConfig, setEditedConfig] = useState<string>('');

  const { data: backtestConfig, isLoading: backtestLoading } = useBacktestConfig();
  const { data: liveConfig, isLoading: liveLoading } = useLiveConfig();
  const updateBacktest = useUpdateBacktestConfig();
  const updateLive = useUpdateLiveConfig();

  const currentConfig = selectedConfig === 'backtest' ? backtestConfig : liveConfig;
  const isLoading = selectedConfig === 'backtest' ? backtestLoading : liveLoading;

  const handleEdit = () => {
    setEditedConfig(JSON.stringify(currentConfig, null, 2));
    setEditMode(true);
  };

  const handleCancel = () => {
    setEditMode(false);
    setEditedConfig('');
  };

  const handleSave = async () => {
    try {
      const parsedConfig = JSON.parse(editedConfig);

      if (selectedConfig === 'backtest') {
        await updateBacktest.mutateAsync(parsedConfig);
      } else {
        await updateLive.mutateAsync(parsedConfig);
      }

      setEditMode(false);
      setEditedConfig('');
    } catch (error: any) {
      if (error instanceof SyntaxError) {
        alert('Invalid JSON format. Please check your syntax.');
      } else {
        alert(`Failed to save configuration: ${error.message || error}`);
      }
    }
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Configuration Editor</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          View and edit YAML configuration files
        </p>
      </div>

      {/* Config Type Selector */}
      <div className="mb-4 md:mb-6 flex flex-col sm:flex-row gap-2 sm:gap-4">
        <Button
          variant={selectedConfig === 'backtest' ? 'primary' : 'secondary'}
          onClick={() => {
            setSelectedConfig('backtest');
            setEditMode(false);
          }}
          className="w-full sm:w-auto"
        >
          Backtest Config
        </Button>
        <Button
          variant={selectedConfig === 'live' ? 'primary' : 'secondary'}
          onClick={() => {
            setSelectedConfig('live');
            setEditMode(false);
          }}
          className="w-full sm:w-auto"
        >
          Live Trading Config
        </Button>
      </div>

      <Card>
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-4">
          <h3 className="text-base md:text-lg font-semibold truncate">
            {selectedConfig === 'backtest' ? 'config/backtest.yaml' : 'config/live_trading.yaml'}
          </h3>
          {!editMode ? (
            <Button variant="primary" onClick={handleEdit} disabled={isLoading} className="w-full sm:w-auto">
              Edit Configuration
            </Button>
          ) : (
            <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
              <Button variant="secondary" onClick={handleCancel} className="w-full sm:w-auto">
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleSave}
                disabled={updateBacktest.isPending || updateLive.isPending}
                className="w-full sm:w-auto"
              >
                {updateBacktest.isPending || updateLive.isPending ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="flex justify-center items-center py-12">
            <div className="text-gray-600">Loading configuration...</div>
          </div>
        ) : editMode ? (
          <div>
            <div className="mb-2 bg-yellow-50 border border-yellow-200 rounded p-3 text-xs md:text-sm text-yellow-800">
              <strong>Warning:</strong> Be careful when editing configuration files. Invalid
              configurations may prevent services from starting. A backup is automatically created
              before saving.
            </div>
            <div className="overflow-x-auto">
              <textarea
                className="w-full min-w-[600px] md:min-w-0 h-80 md:h-96 font-mono text-xs md:text-sm p-3 md:p-4 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                value={editedConfig}
                onChange={(e) => setEditedConfig(e.target.value)}
                placeholder="Edit configuration (JSON format)..."
                spellCheck={false}
              />
            </div>
            <div className="mt-2 text-xs md:text-sm text-gray-600">
              Format: JSON (will be converted to YAML on save)
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <pre className="bg-gray-50 border border-gray-200 rounded p-3 md:p-4">
              <code className="text-xs md:text-sm">{JSON.stringify(currentConfig, null, 2)}</code>
            </pre>
          </div>
        )}

        {(updateBacktest.isSuccess || updateLive.isSuccess) && (
          <div className="mt-4 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded">
            Configuration saved successfully! Restart affected services for changes to take effect.
          </div>
        )}

        {(updateBacktest.isError || updateLive.isError) && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            Failed to save configuration. Please check the format and try again.
          </div>
        )}
      </Card>

      {/* Configuration Help */}
      <Card className="mt-6">
        <h3 className="text-lg font-semibold mb-4">Configuration Guidelines</h3>

        <div className="space-y-4 text-sm">
          <div className="bg-blue-50 border border-blue-200 rounded p-3">
            <p className="text-blue-900 font-medium mb-1">Backtest Configuration</p>
            <p className="text-blue-700">
              Controls backtest execution parameters including:
            </p>
            <ul className="list-disc list-inside text-blue-700 mt-2 ml-2">
              <li>Enabled strategies and their parameters</li>
              <li>Data source settings (database, date ranges)</li>
              <li>Initial capital and commission rates</li>
              <li>Output and logging preferences</li>
            </ul>
          </div>

          <div className="bg-purple-50 border border-purple-200 rounded p-3">
            <p className="text-purple-900 font-medium mb-1">Live Trading Configuration</p>
            <p className="text-purple-700">
              Controls live trading engine behavior including:
            </p>
            <ul className="list-disc list-inside text-purple-700 mt-2 ml-2">
              <li>Trading mode (paper vs. live)</li>
              <li>Active strategies and position limits</li>
              <li>Risk management rules and stop losses</li>
              <li>Data feed settings (Redis vs. direct Schwab)</li>
              <li>Order execution and monitoring intervals</li>
            </ul>
          </div>

          <div className="bg-gray-50 border border-gray-200 rounded p-3">
            <p className="text-gray-900 font-medium mb-1">Best Practices</p>
            <ul className="list-disc list-inside text-gray-700 ml-2">
              <li>Always test configuration changes in paper trading mode first</li>
              <li>Backup is created automatically before saving</li>
              <li>Restart services after configuration changes</li>
              <li>Validate JSON syntax before saving</li>
              <li>Keep configuration files version controlled</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
