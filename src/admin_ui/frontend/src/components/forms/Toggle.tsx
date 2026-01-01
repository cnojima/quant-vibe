export interface ToggleProps {
  id: string;
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  error?: string;
  description?: string;
  disabled?: boolean;
}

export function Toggle({
  id,
  label,
  value,
  onChange,
  error,
  description,
  disabled = false,
}: ToggleProps) {
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <label htmlFor={id} className="block text-sm font-medium text-gray-700">
            {label}
          </label>
          {description && (
            <p className="text-sm text-gray-500 mt-1">{description}</p>
          )}
        </div>
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={value}
          disabled={disabled}
          onClick={() => onChange(!value)}
          className={`
            relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
            transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            ${value ? 'bg-blue-600' : 'bg-gray-200'}
          `}
        >
          <span
            aria-hidden="true"
            className={`
              pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0
              transition duration-200 ease-in-out
              ${value ? 'translate-x-5' : 'translate-x-0'}
            `}
          />
        </button>
      </div>
      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}
