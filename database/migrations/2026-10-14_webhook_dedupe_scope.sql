-- Apply to an existing database (migrate.py recreates from schema.sql, which already has this).
-- Sample-level webhooks are deduped per tube and per receiving lab, not per bill:
-- a second SAMPLE_RECEIVED for the same bill (another tube, or another lab) is a new event.
BEGIN;
ALTER TABLE tat_webhook_event
  ADD COLUMN IF NOT EXISTS dedupe_scope VARCHAR(160) NOT NULL DEFAULT '';
ALTER TABLE tat_webhook_event DROP CONSTRAINT IF EXISTS uq_event_dedup;
ALTER TABLE tat_webhook_event
  ADD CONSTRAINT uq_event_dedup UNIQUE (bill_id, webhook_type, webhook_id, dedupe_scope);
COMMIT;
