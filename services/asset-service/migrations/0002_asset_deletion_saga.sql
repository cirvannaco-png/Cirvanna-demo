ALTER TABLE asset_objects
  DROP CONSTRAINT IF EXISTS asset_objects_status_check;
ALTER TABLE asset_objects
  ADD CONSTRAINT asset_objects_status_check
  CHECK (status IN ('active', 'deleting', 'deleted'));
