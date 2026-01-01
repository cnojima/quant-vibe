import React from 'react';
import { TextInput } from './TextInput';
import { NumberInput } from './NumberInput';
import { Toggle } from './Toggle';
import { Select, SelectOption } from './Select';
import { CollapsibleSection } from './CollapsibleSection';
import { ArrayEditor } from './ArrayEditor';

interface JSONSchema {
  type?: string;
  properties?: Record<string, JSONSchema>;
  items?: JSONSchema;
  enum?: string[];
  anyOf?: JSONSchema[];
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

    // Handle anyOf (common for optional/nullable fields in Pydantic)
    // Extract the non-null type from anyOf
    let actualSchema = fieldSchema;
    if (fieldSchema.anyOf && Array.isArray(fieldSchema.anyOf)) {
      // Find the first non-null type
      const nonNullSchema = fieldSchema.anyOf.find(
        (s: any) => s.type !== 'null'
      );
      if (nonNullSchema) {
        actualSchema = {
          ...nonNullSchema,
          title: fieldSchema.title,
          description: fieldSchema.description,
          default: fieldSchema.default,
        };
      }
    }

    // Handle enum fields (render as select)
    if (actualSchema.enum) {
      const options: SelectOption[] = actualSchema.enum.map((val) => ({
        value: String(val),
        label: String(val),
      }));

      return (
        <Select
          key={fieldName}
          id={fieldPath}
          label={actualSchema.title || fieldName}
          value={String(fieldValue ?? actualSchema.default ?? options[0]?.value ?? '')}
          options={options}
          onChange={(val) => handleFieldChange(fieldName, val)}
          error={fieldError}
          description={actualSchema.description}
          required={isRequired}
        />
      );
    }

    // Handle different types
    switch (actualSchema.type) {
      case 'string':
        return (
          <TextInput
            key={fieldName}
            id={fieldPath}
            label={actualSchema.title || fieldName}
            value={fieldValue ?? actualSchema.default ?? ''}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={actualSchema.description}
            required={isRequired}
          />
        );

      case 'number':
      case 'integer':
        return (
          <NumberInput
            key={fieldName}
            id={fieldPath}
            label={actualSchema.title || fieldName}
            value={fieldValue ?? actualSchema.default ?? null}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={actualSchema.description}
            required={isRequired}
            min={actualSchema.minimum}
            max={actualSchema.maximum}
            step={actualSchema.type === 'integer' ? 1 : undefined}
          />
        );

      case 'boolean':
        return (
          <Toggle
            key={fieldName}
            id={fieldPath}
            label={actualSchema.title || fieldName}
            value={fieldValue ?? actualSchema.default ?? false}
            onChange={(val) => handleFieldChange(fieldName, val)}
            error={fieldError}
            description={actualSchema.description}
          />
        );

      case 'object':
        if (actualSchema.properties) {
          return (
            <CollapsibleSection
              key={fieldName}
              title={actualSchema.title || fieldName}
              description={actualSchema.description}
              defaultOpen={false}
            >
              <SchemaForm
                schema={actualSchema}
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
        if (actualSchema.items) {
          return (
            <ArrayEditor
              key={fieldName}
              id={fieldPath}
              label={actualSchema.title || fieldName}
              items={fieldValue || []}
              itemSchema={actualSchema.items}
              onChange={(val) => handleFieldChange(fieldName, val)}
              description={actualSchema.description}
              renderItem={(item, index, onChange) => (
                <SchemaForm
                  schema={actualSchema.items!}
                  data={item}
                  onChange={onChange}
                  errors={errors}
                  path={`${fieldPath}[${index}]`}
                />
              )}
            />
          );
        }
        return (
          <div key={fieldName} className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {actualSchema.title || fieldName}
            </label>
            <p className="text-sm text-gray-500">
              {actualSchema.description || 'Array field (use YAML mode to edit)'}
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
