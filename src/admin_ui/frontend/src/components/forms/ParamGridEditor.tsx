import { useState, useEffect } from 'react';
import { Button } from '../common/Button';
import { InfoIcon } from '../common/InfoIcon';
import { useValidateParamGrid } from '../../api/queries';

interface ParamGridEditorProps {
  strategyName: string;
  initialGrid: Record<string, any[]>;
  onChange: (grid: Record<string, any[]>) => void;
  maxCombinations?: number;
}

export function ParamGridEditor({
  strategyName,
  initialGrid,
  onChange,
  maxCombinations = 200,
}: ParamGridEditorProps) {
  const [paramGrid, setParamGrid] = useState<Record<string, any[]>>(initialGrid);
  const [totalCombinations, setTotalCombinations] = useState<number>(0);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [showWarningModal, setShowWarningModal] = useState(false);

  const validateGrid = useValidateParamGrid();

  // Calculate permutations
  const calculatePermutations = (grid: Record<string, any[]>) => {
    if (Object.keys(grid).length === 0) return 0;
    return Object.values(grid).reduce((total, values) => total * values.length, 1);
  };

  // Validate grid whenever it changes
  useEffect(() => {
    const count = calculatePermutations(paramGrid);
    setTotalCombinations(count);

    // Validate with backend
    if (Object.keys(paramGrid).length > 0) {
      validateGrid.mutate(
        {
          strategy_name: strategyName,
          param_grid: paramGrid,
          max_combinations: maxCombinations,
        },
        {
          onSuccess: (data) => {
            setWarnings(data.warnings || []);
            setErrors(data.errors || []);

            // Show warning modal if exceeds threshold
            if (data.warnings && data.warnings.length > 0 && count > maxCombinations) {
              setShowWarningModal(true);
            }
          },
        }
      );
    }

    onChange(paramGrid);
  }, [paramGrid, strategyName, maxCombinations]);

  const handleAddValue = (paramName: string) => {
    const currentValues = paramGrid[paramName] || [];
    const lastValue = currentValues[currentValues.length - 1];

    // Infer type and suggest next value
    let newValue: any;
    if (typeof lastValue === 'number') {
      newValue = lastValue + 1;
    } else if (typeof lastValue === 'string') {
      newValue = '';
    } else {
      newValue = 0;
    }

    setParamGrid({
      ...paramGrid,
      [paramName]: [...currentValues, newValue],
    });
  };

  const handleRemoveValue = (paramName: string, index: number) => {
    const currentValues = paramGrid[paramName] || [];
    if (currentValues.length <= 1) {
      // Can't remove last value - remove entire parameter instead
      const newGrid = { ...paramGrid };
      delete newGrid[paramName];
      setParamGrid(newGrid);
    } else {
      setParamGrid({
        ...paramGrid,
        [paramName]: currentValues.filter((_, i) => i !== index),
      });
    }
  };

  const handleValueChange = (paramName: string, index: number, value: any) => {
    const currentValues = paramGrid[paramName] || [];
    const newValues = [...currentValues];

    // Parse value based on type
    const originalValue = currentValues[index];
    if (typeof originalValue === 'number') {
      newValues[index] = parseFloat(value) || 0;
    } else {
      newValues[index] = value;
    }

    setParamGrid({
      ...paramGrid,
      [paramName]: newValues,
    });
  };

  const getStatusColor = () => {
    if (errors.length > 0) return 'text-red-600';
    if (warnings.length > 0) return 'text-yellow-600';
    if (totalCombinations > maxCombinations) return 'text-orange-600';
    return 'text-green-600';
  };

  const getStatusIcon = () => {
    if (errors.length > 0) return '❌';
    if (warnings.length > 0) return '⚠️';
    if (totalCombinations > maxCombinations) return '⚠️';
    return '✓';
  };

  return (
    <div className="space-y-4">
      {/* Header with permutation count */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-medium text-gray-900">Parameter Grid</h3>
          <InfoIcon
            content="Edit parameter values to optimize. Each parameter must have at least one value. Total combinations = product of all value counts."
          />
        </div>
        <div className={`text-sm font-semibold ${getStatusColor()}`}>
          {getStatusIcon()} Total Combinations: {totalCombinations.toLocaleString()}
        </div>
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-yellow-800">Warnings</h3>
              <div className="mt-2 text-sm text-yellow-700">
                <ul className="list-disc list-inside space-y-1">
                  {warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-md p-3">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Errors</h3>
              <div className="mt-2 text-sm text-red-700">
                <ul className="list-disc list-inside space-y-1">
                  {errors.map((error, i) => (
                    <li key={i}>{error}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Parameter grid */}
      <div className="border border-gray-200 rounded-lg divide-y divide-gray-200">
        {Object.entries(paramGrid).map(([paramName, values]) => (
          <div key={paramName} className="p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium text-gray-700">
                  {paramName}
                </label>
                <span className="text-xs text-gray-500">
                  ({values.length} {values.length === 1 ? 'value' : 'values'})
                </span>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleAddValue(paramName)}
                type="button"
              >
                + Add Value
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              {values.map((value, index) => (
                <div
                  key={index}
                  className="flex items-center gap-1 bg-gray-50 border border-gray-300 rounded px-2 py-1"
                >
                  <input
                    type={typeof value === 'number' ? 'number' : 'text'}
                    value={value}
                    onChange={(e) => handleValueChange(paramName, index, e.target.value)}
                    className="w-20 px-1 py-0.5 text-sm border-0 bg-transparent focus:outline-none focus:ring-1 focus:ring-blue-500 rounded"
                    step={typeof value === 'number' ? 'any' : undefined}
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveValue(paramName, index)}
                    className="text-gray-400 hover:text-red-600 transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Warning Modal */}
      {showWarningModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md mx-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-6 w-6 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-lg font-medium text-gray-900">High Combination Count</h3>
                <div className="mt-2 text-sm text-gray-500">
                  <p>
                    You have <strong>{totalCombinations.toLocaleString()}</strong> parameter combinations,
                    which exceeds the recommended maximum of <strong>{maxCombinations}</strong>.
                  </p>
                  <p className="mt-2">
                    This optimization may take a very long time (potentially hours). Consider:
                  </p>
                  <ul className="list-disc list-inside mt-2 space-y-1">
                    <li>Reducing the number of values per parameter</li>
                    <li>Removing less important parameters</li>
                    <li>Running multiple smaller optimizations</li>
                  </ul>
                </div>
                <div className="mt-4">
                  <Button
                    variant="primary"
                    onClick={() => setShowWarningModal(false)}
                    className="w-full"
                  >
                    I Understand, Continue
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
