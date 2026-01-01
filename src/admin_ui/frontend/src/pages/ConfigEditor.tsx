import { useState, useEffect } from 'react';
import {
  useBacktestConfig,
  useLiveConfig,
  useUpdateBacktestConfig,
  useUpdateLiveConfig,
  useBacktestSchema,
  useLiveSchema,
} from '../api/queries';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { SchemaForm } from '../components/forms';
import yaml from 'js-yaml';

type ConfigType = 'backtest' | 'live';
type ViewMode = 'form' | 'yaml';

export function ConfigEditor() {
  const [selectedConfig, setSelectedConfig] = useState<ConfigType>('backtest');
  const [viewMode, setViewMode] = useState<ViewMode>('form');
  const [editMode, setEditMode] = useState(false);
  const [editedConfig, setEditedConfig] = useState<any>(null);
  const [yamlText, setYamlText] = useState<string>('');
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  const { data: backtestConfig, isLoading: backtestLoading } = useBacktestConfig();
  const { data: liveConfig, isLoading: liveLoading } = useLiveConfig();
  const { data: backtestSchema, isLoading: backtestSchemaLoading } = useBacktestSchema();
  const { data: liveSchema, isLoading: liveSchemaLoading } = useLiveSchema();
  const updateBacktest = useUpdateBacktestConfig();
  const updateLive = useUpdateLiveConfig();

  const currentConfig = selectedConfig === 'backtest' ? backtestConfig : liveConfig;
  const currentSchema = selectedConfig === 'backtest' ? backtestSchema : liveSchema;
  const isLoading = selectedConfig === 'backtest' ? backtestLoading : liveLoading;
  const schemaLoading = selectedConfig === 'backtest' ? backtestSchemaLoading : liveSchemaLoading;

  // Initialize YAML text when entering YAML mode or config changes
  useEffect(() => {
    if (viewMode === 'yaml' && editMode && editedConfig) {
      try {
        const yamlStr = yaml.dump(editedConfig, {
          indent: 2,
          lineWidth: -1,
          noRefs: true,
        });
        setYamlText(yamlStr);
      } catch (error) {
        console.error('Failed to convert to YAML:', error);
      }
    }
  }, [viewMode, editMode, editedConfig]);

  const handleEdit = () => {
    setEditedConfig(JSON.parse(JSON.stringify(currentConfig))); // Deep clone
    setValidationErrors({});
    setEditMode(true);
  };

  const handleCancel = () => {
    setEditMode(false);
    setEditedConfig(null);
    setYamlText('');
    setValidationErrors({});
  };

  const handleSave = async () => {
    try {
      let configToSave = editedConfig;

      // If in YAML mode, parse YAML to object
      if (viewMode === 'yaml') {
        try {
          configToSave = yaml.load(yamlText) as any;
        } catch (error: any) {
          alert(`Invalid YAML format: ${error.message}`);
          return;
        }
      }

      if (selectedConfig === 'backtest') {
        await updateBacktest.mutateAsync(configToSave);
      } else {
        await updateLive.mutateAsync(configToSave);
      }

      setEditMode(false);
      setEditedConfig(null);
      setYamlText('');
      setValidationErrors({});
    } catch (error: any) {
      // Handle validation errors from backend
      if (error.response?.status === 422 && error.response?.data?.detail?.errors) {
        const errors: Record<string, string> = {};
        error.response.data.detail.errors.forEach((err: any) => {
          const path = err.loc.join('.');
          errors[path] = err.msg;
        });
        setValidationErrors(errors);
        alert('Configuration validation failed. Please check the error messages below.');
      } else {
        alert(`Failed to save configuration: ${error.response?.data?.detail?.message || error.message || error}`);
      }
    }
  };

  const handleFormChange = (newData: any) => {
    setEditedConfig(newData);
    setValidationErrors({}); // Clear errors on change
  };

  const handleYamlChange = (newYaml: string) => {
    setYamlText(newYaml);
  };

  const handleModeSwitch = (mode: ViewMode) => {
    if (mode === 'yaml' && viewMode === 'form') {
      // Switching from form to YAML
      if (editedConfig) {
        try {
          const yamlStr = yaml.dump(editedConfig, {
            indent: 2,
            lineWidth: -1,
            noRefs: true,
          });
          setYamlText(yamlStr);
        } catch (error) {
          console.error('Failed to convert to YAML:', error);
        }
      }
      setViewMode('yaml');
    } else if (mode === 'form' && viewMode === 'yaml') {
      // Switching from YAML to form
      try {
        const parsed = yaml.load(yamlText) as any;
        setEditedConfig(parsed);
        setViewMode('form');
      } catch (error: any) {
        alert(`Invalid YAML format. Cannot switch to form mode: ${error.message}`);
      }
    }
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Configuration Editor</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          View and edit YAML configuration files using form controls or raw YAML
        </p>
      </div>

      {/* Config Type Selector */}
      <div className="mb-4 md:mb-6 flex flex-col sm:flex-row gap-2 sm:gap-4">
        <Button
          variant={selectedConfig === 'backtest' ? 'primary' : 'secondary'}
          onClick={() => {
            setSelectedConfig('backtest');
            setEditMode(false);
            setEditedConfig(null);
            setYamlText('');
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
            setEditedConfig(null);
            setYamlText('');
          }}
          className="w-full sm:w-auto"
        >
          Live Trading Config
        </Button>
      </div>

      <Card>
        <div className="flex flex-col gap-3 mb-4">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3">
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

          {/* View Mode Toggle (only in edit mode) */}
          {editMode && (
            <div className="flex gap-2">
              <Button
                variant={viewMode === 'form' ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => handleModeSwitch('form')}
                className="flex-1 sm:flex-initial"
              >
                Form Editor
              </Button>
              <Button
                variant={viewMode === 'yaml' ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => handleModeSwitch('yaml')}
                className="flex-1 sm:flex-initial"
              >
                YAML Editor
              </Button>
            </div>
          )}
        </div>

        {isLoading || schemaLoading ? (
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

            {viewMode === 'form' ? (
              <div className="max-h-[600px] overflow-y-auto pr-2">
                {currentSchema && editedConfig ? (
                  <SchemaForm
                    schema={currentSchema}
                    data={editedConfig}
                    onChange={handleFormChange}
                    errors={validationErrors}
                  />
                ) : (
                  <div className="text-gray-600">Schema not available. Please use YAML editor.</div>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <textarea
                  className="w-full min-w-[600px] md:min-w-0 h-80 md:h-96 font-mono text-xs md:text-sm p-3 md:p-4 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  value={yamlText}
                  onChange={(e) => handleYamlChange(e.target.value)}
                  placeholder="Edit configuration (YAML format)..."
                  spellCheck={false}
                />
              </div>
            )}

            {Object.keys(validationErrors).length > 0 && (
              <div className="mt-4 bg-red-50 border border-red-200 rounded p-3">
                <p className="text-red-800 font-semibold mb-2">Validation Errors:</p>
                <ul className="list-disc list-inside text-red-700 text-sm">
                  {Object.entries(validationErrors).map(([path, message]) => (
                    <li key={path}>
                      <strong>{path}:</strong> {message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <pre className="bg-gray-50 border border-gray-200 rounded p-3 md:p-4">
              <code className="text-xs md:text-sm">
                {yaml.dump(currentConfig, { indent: 2, lineWidth: -1, noRefs: true })}
              </code>
            </pre>
          </div>
        )}

        {(updateBacktest.isSuccess || updateLive.isSuccess) && (
          <div className="mt-4 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded">
            Configuration saved successfully! Restart affected services for changes to take effect.
          </div>
        )}

        {(updateBacktest.isError || updateLive.isError) && !Object.keys(validationErrors).length && (
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
              <li>Use Form Editor for guided editing with validation</li>
              <li>Use YAML Editor for advanced editing and bulk changes</li>
              <li>Keep configuration files version controlled</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
