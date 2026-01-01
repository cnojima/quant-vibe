export interface NumberInputProps {
  id: string;
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  error?: string;
  description?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  min?: number;
  max?: number;
  step?: number;
}

export function NumberInput({
  id,
  label,
  value,
  onChange,
  error,
  description,
  placeholder,
  disabled = false,
  required = false,
  min,
  max,
  step,
}: NumberInputProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    if (val === '') {
      onChange(null);
    } else {
      const num = parseFloat(val);
      if (!isNaN(num)) {
        onChange(num);
      }
    }
  };

  return (
    <div className="mb-4">
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {description && (
        <p className="text-sm text-gray-500 mb-2">{description}</p>
      )}
      <input
        id={id}
        type="number"
        value={value ?? ''}
        onChange={handleChange}
        disabled={disabled}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        className={`
          w-full px-3 py-2 border rounded-md shadow-sm
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
          disabled:bg-gray-100 disabled:cursor-not-allowed
          ${error ? 'border-red-500' : 'border-gray-300'}
        `}
      />
      {error && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
    </div>
  );
}
