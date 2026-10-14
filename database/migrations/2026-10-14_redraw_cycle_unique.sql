-- Apply to an existing database (migrate.py recreates from schema.sql, which already has this).
-- SAMPLE_REDRAWN creates a new cycle row carrying the same CrelioHealth report / test ids,
-- so those ids are unique only among current-cycle rows. Old cycles stay as history.
BEGIN;
ALTER TABLE tat_test_instance DROP CONSTRAINT IF EXISTS uq_ext_report;
ALTER TABLE tat_test_instance DROP CONSTRAINT IF EXISTS uq_sample_test;
DROP INDEX IF EXISTS uq_ext_report;
DROP INDEX IF EXISTS uq_sample_test;
CREATE UNIQUE INDEX uq_ext_report  ON tat_test_instance(external_report_id) WHERE is_current_cycle = 1;
CREATE UNIQUE INDEX uq_sample_test ON tat_test_instance(sample_id, external_test_id) WHERE is_current_cycle = 1;
COMMIT;
