import { useState } from 'react';
import { Button } from '../common/Button';

interface ArrayEditorProps {
  id: string;
  label: string;
  items: any[];
  itemSchema: any;
  onChange: (items: any[]) => void;
  description?: string;
  renderItem: (item: any, index: number, onChange: (item: any) => void) => React.ReactNode;
}

export function ArrayEditor({
  label,
  items = [],
  itemSchema,
  onChange,
  description,
  renderItem,
}: ArrayEditorProps) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const handleAddItem = () => {
    const newItem = itemSchema?.default || {};
    onChange([...items, newItem]);
  };

  const handleRemoveItem = (index: number) => {
    const newItems = items.filter((_, i) => i !== index);
    onChange(newItems);
  };

  const handleItemChange = (index: number, newItem: any) => {
    const newItems = [...items];
    newItems[index] = newItem;
    onChange(newItems);
  };

  const toggleCollapse = (index: number) => {
    const newCollapsed = new Set(collapsed);
    if (newCollapsed.has(index)) {
      newCollapsed.delete(index);
    } else {
      newCollapsed.add(index);
    }
    setCollapsed(newCollapsed);
  };

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <label className="block text-sm font-medium text-gray-700">
            {label}
          </label>
          {description && (
            <p className="text-sm text-gray-500 mt-1">{description}</p>
          )}
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={handleAddItem}
          type="button"
        >
          Add Item
        </Button>
      </div>

      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="text-sm text-gray-500 italic border border-dashed border-gray-300 rounded p-4 text-center">
            No items. Click "Add Item" to add one.
          </div>
        ) : (
          items.map((item, index) => (
            <div
              key={index}
              className="border border-gray-200 rounded overflow-hidden"
            >
              <div className="flex items-center justify-between bg-gray-50 px-3 py-2">
                <button
                  type="button"
                  onClick={() => toggleCollapse(index)}
                  className="flex-1 flex items-center gap-2 text-left text-sm font-medium text-gray-700 hover:text-gray-900"
                >
                  <svg
                    className={`w-4 h-4 transition-transform ${
                      collapsed.has(index) ? '' : 'transform rotate-90'
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                  Item {index + 1}
                  {item.name && <span className="text-gray-500">- {item.name}</span>}
                </button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleRemoveItem(index)}
                  type="button"
                >
                  Remove
                </Button>
              </div>
              {!collapsed.has(index) && (
                <div className="p-3 bg-white">
                  {renderItem(item, index, (newItem) => handleItemChange(index, newItem))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
