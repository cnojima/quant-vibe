-- Migration: Add action_type column to live_orders table
-- Date: 2026-01-02
-- Description: Adds action_type column to distinguish between opening and closing orders

-- Add the action_type column (nullable to allow existing rows)
ALTER TABLE live_orders
ADD COLUMN IF NOT EXISTS action_type TEXT;

-- Add a comment to document the column
COMMENT ON COLUMN live_orders.action_type IS 'Order action type: opening (new position) or closing (exit position)';

-- Update existing rows: Set default to 'opening' for pending/new orders, 'closing' for others
-- This is a best-effort guess for historical data
UPDATE live_orders
SET action_type = 'opening'
WHERE action_type IS NULL
  AND status IN ('pending', 'submitted', 'accepted');

-- For filled orders, we can't definitively know if they were opening or closing
-- Set to 'opening' as default, manual correction may be needed for historical data
UPDATE live_orders
SET action_type = 'opening'
WHERE action_type IS NULL;

-- Verify the migration
SELECT
    action_type,
    status,
    COUNT(*) as count
FROM live_orders
GROUP BY action_type, status
ORDER BY action_type, status;

-- Optional: Make the column NOT NULL after backfilling
-- ALTER TABLE live_orders ALTER COLUMN action_type SET NOT NULL;
-- ALTER TABLE live_orders ALTER COLUMN action_type SET DEFAULT 'opening';

-- Migration complete
SELECT 'Migration completed: action_type column added to live_orders' as status;
