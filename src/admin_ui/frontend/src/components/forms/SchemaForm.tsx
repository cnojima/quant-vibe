import React from 'react';
import { TextInput } from './TextInput';
import { NumberInput } from './NumberInput';
import { Toggle } from './Toggle';
import { Select, SelectOption } from './Select';
import { CollapsibleSection } from './CollapsibleSection';

interface JSONSchema {
  type?: string;
  properties?: Record<string, JSONSchema>;
  items?: JSONSchema;
  enum?: string[];
  title?: string;
  description?: string;
  default?: any;
  minimum?: number;
  maximum?: number;
  required?: string[];
  $defs?: Record<string, JSONSchema>;
}

interface SchemaFormProps {
  schema: JSONSchema;
  data: any;
  onChange: (data: any) => void;
  errors?: Record<string, string>;
  path?: string;
}

export function SchemaForm({
  schema,
  data,
  onChange,
  errors = {},
  path = '',
}: SchemaFormProps) {
  if (!schema || !schema.properties) {
    return null;
  }

  const handleFieldChange = (fieldName: string, value: any) => {
    onChange({
      ...data,
      [fieldName]: value,
    });
  };

  const renderField = (fieldName: string, fieldSchema: JSONSchema): React.ReactNode => {
    const fieldPath = path ? `${path}.${fieldName}` : fieldName;
    const fieldValue = data?.[fieldName];
    const fieldError = errors[fieldPath];
    const isRequired = schema.required?.includes(fieldName) || false;

    // Handle enum fields (render as select)
    if (fieldSchema.enum) {
      const options: SelectOption[] = fieldSchema.enum.map((val) => ({
        value: String(val),
        label: String(val),
      }));

      return (
        <Select
          key={fieldName}
          id={fieldPath}
          label={fieldSchema.title || fieldName}
          value={String(fieldValue ?? fieldSchema.default ?? options[0]?.value ?? '')}
          options={options}
          onChange={(val) => handleFieldChange(fieldName, val)}
          error={fieldError}
          description={fieldSchema.description}
          required={isRequired}
        />
      );
    }

    // Handle different types
    switch (fieldSchema.type) {
      case 'string':
        return (
          <TextInput
            key={fieldName}
            id={fieldPath}
            label={fieldSchema.title || fieldName}
            value={fieldValue ?? fieldSchema.default ?? ''}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={fieldSchema.description}
            required={isRequired}
          />
        );

      case 'number':
      case 'integer':
        return (
          <NumberInput
            key={fieldName}
            id={fieldPath}
            label={fieldSchema.title || fieldName}
            value={fieldValue ?? fieldSchema.default ?? null}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={fieldSchema.description}
            required={isRequired}
            min={fieldSchema.minimum}
            max={fieldSchema.maximum}
            step={fieldSchema.type === 'integer' ? 1 : undefined}
          />
        );

      case 'boolean':
        return (
          <Toggle
            key={fieldName}
            id={fieldPath}
            label={fieldSchema.title || fieldName}
            value={fieldValue ?? fieldSchema.default ?? false}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={fieldSchema.description}
          />
        );

      case 'object':
        if (fieldSchema.properties) {
          return (
            <CollapsibleSection
              key={fieldName}
              title={fieldSchema.title || fieldName}
              description={fieldSchema.description}
              defaultOpen={false}
            >
              <SchemaForm
                schema={fieldSchema}
                data={fieldValue || {}}
                onChange={(val) => handleFieldChange(fieldName, val)}
                errors={errors}
                path={fieldPath}
              />
            </CollapsibleSection>
          );
        }
        break;

      case 'array':
        // For now, skip array rendering (can be enhanced later)
        return (
          <div key={fieldName} className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {fieldSchema.title || fieldName}
            </label>
            <p className="text-sm text-gray-500">
              {fieldSchema.description || 'Array field (use YAML mode to edit)'}
            </p>
          </div>
        );

      default:
        return null;
    }
  };

  // Group fields into collapsible sections for top-level objects
  const isTopLevel = path === '';

  if (isTopLevel) {
    return (
      <div className="space-y-4">
        {Object.entries(schema.properties).map(([fieldName, fieldSchema]) => (
          <div key={fieldName}>
            {renderField(fieldName, fieldSchema)}
          </div>
        ))}
      </div>
    );
  }

  // For nested objects, just render fields directly
  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(([fieldName, fieldSchema]) => (
        renderField(fieldName, fieldSchema)
      ))}
    </div>
  );
}
