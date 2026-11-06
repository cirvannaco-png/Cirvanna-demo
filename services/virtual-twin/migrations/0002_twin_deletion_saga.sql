ALTER TABLE virtual_twin_records
  DROP CONSTRAINT IF EXISTS virtual_twin_records_status_check;
ALTER TABLE virtual_twin_records
  ADD CONSTRAINT virtual_twin_records_status_check
  CHECK (status IN ('active', 'deleting', 'deleted'));
