import { useState } from 'react';
import { InfoIcon } from '../common/InfoIcon';

interface FixedParamsPanelProps {
  fixedParams: Record<string, any>;
  onChange?: (params: Record<string, any>) => void;
  editable?: boolean;
}

export function FixedParamsPanel({
  fixedParams,
  onChange,
  editable = false,
}: FixedParamsPanelProps) {
  const [params, setParams] = useState<Record<string, any>>(fixedParams);
  const [isExpanded, setIsExpanded] = useState(false);

  const handleParamChange = (paramName: string, value: any) => {
    const newParams = { ...params, [paramName]: value };
    setParams(newParams);
    if (onChange) {
      onChange(newParams);
    }
  };

  const formatParamName = (name: string) => {
    // Convert snake_case to Title Case
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const getParamDescription = (paramName: string): string => {
    // Add descriptions for common parameters
    const descriptions: Record<string, string> = {
      min_dte: 'Minimum days to expiration for contract selection',
      max_dte: 'Maximum days to expiration for contract selection',
      max_trades_daily: 'Maximum number of trades allowed per day',
      observation_period: 'Historical period (minutes) to observe before trading',
      num_spreads: 'Number of spreads to trade simultaneously',
      stop_loss_pct: 'Stop loss percentage (null = no stop loss)',
      trailing_stop_pct: 'Trailing stop percentage',
      trailing_stop_threshold: 'Minimum profit before trailing stop activates',
    };

    return descriptions[paramName] || `Fixed value for ${formatParamName(paramName)}`;
  };

  const renderParamValue = (_paramName: string, value: any) => {
    if (value === null) {
      return <span className="text-gray-400 italic">None</span>;
    }

    if (typeof value === 'boolean') {
      return <span className={value ? 'text-green-600' : 'text-red-600'}>{value ? 'Yes' : 'No'}</span>;
    }

    if (typeof value === 'number') {
      return <span className="font-mono">{value}</span>;
    }

    return <span>{String(value)}</span>;
  };

  const renderEditableParam = (paramName: string, value: any) => {
    if (value === null) {
      return (
        <input
          type="text"
          value=""
          placeholder="None (optional)"
          onChange={(e) => handleParamChange(paramName, e.target.value || null)}
          className="px-2 py-1 border border-gray-300 rounded text-sm w-32"
        />
      );
    }

    if (typeof value === 'boolean') {
      return (
        <select
          value={value ? 'true' : 'false'}
          onChange={(e) => handleParamChange(paramName, e.target.value === 'true')}
          className="px-2 py-1 border border-gray-300 rounded text-sm"
        >
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      );
    }

    if (typeof value === 'number') {
      return (
        <input
          type="number"
          value={value}
          onChange={(e) => handleParamChange(paramName, parseFloat(e.target.value) || 0)}
          className="px-2 py-1 border border-gray-300 rounded text-sm font-mono w-32"
          step="any"
        />
      );
    }

    return (
      <input
        type="text"
        value={String(value)}
        onChange={(e) => handleParamChange(paramName, e.target.value)}
        className="px-2 py-1 border border-gray-300 rounded text-sm w-32"
      />
    );
  };

  return (
    <div className="border border-gray-200 rounded-lg">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-medium text-gray-900">Fixed Parameters</h3>
          <InfoIcon
            content="These parameters are not optimized and remain constant across all combinations. Expand to view or edit."
          />
          <span className="text-sm text-gray-500">
            ({Object.keys(fixedParams).length} parameters)
          </span>
        </div>
        <svg
          className={`w-5 h-5 text-gray-500 transition-transform ${
            isExpanded ? 'transform rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isExpanded && (
        <div className="border-t border-gray-200 p-4">
          {editable && (
            <div className="mb-3 bg-blue-50 border border-blue-200 rounded p-3">
              <p className="text-sm text-blue-800">
                <strong>Advanced:</strong> You can modify fixed parameters here. These will apply to all
                optimization combinations.
              </p>
            </div>
          )}

          <div className="space-y-3">
            {Object.entries(params).length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <p>No fixed parameters for this strategy.</p>
                <p className="text-sm mt-1">All parameters are being optimized.</p>
              </div>
            ) : (
              Object.entries(params).map(([paramName, value]) => (
                <div
                  key={paramName}
                  className="flex items-start justify-between py-2 border-b border-gray-100 last:border-0"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-700">
                        {formatParamName(paramName)}
                      </span>
                      <InfoIcon
                        content={getParamDescription(paramName)}
                        size="sm"
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {getParamDescription(paramName)}
                    </p>
                  </div>
                  <div className="flex-shrink-0 ml-4">
                    {editable ? (
                      renderEditableParam(paramName, value)
                    ) : (
                      <div className="text-sm text-gray-900">
                        {renderParamValue(paramName, value)}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {editable && Object.keys(params).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-200">
              <button
                type="button"
                onClick={() => {
                  setParams(fixedParams);
                  if (onChange) {
                    onChange(fixedParams);
                  }
                }}
                className="text-sm text-blue-600 hover:text-blue-700"
              >
                Reset to defaults
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
