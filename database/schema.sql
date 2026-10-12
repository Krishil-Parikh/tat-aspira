-- ====================================================================
-- TAT SYSTEM v2 — PostgreSQL Schema
-- Converted from MySQL (newdb.sql) to PostgreSQL
-- ====================================================================

-- ENUM TYPES
CREATE TYPE webhook_status_t AS ENUM ('received','processing','processed','failed','dead_letter','duplicate','awaiting_reconciliation');
CREATE TYPE bill_status_t    AS ENUM ('preview','active','cancelled','completed');
CREATE TYPE sample_status_t  AS ENUM ('draft','unassigned','pending','queued','in_transit','arrived','processing','partially_complete','completed','cancelled','rejected','delayed','error');
CREATE TYPE test_status_t    AS ENUM ('draft','pending','processing','result_saved','signed','submitted','completed','cancelled','invalidated');
CREATE TYPE queue_status_t   AS ENUM ('scheduled','waiting','processing','completed','cancelled','skipped','delayed','error');
CREATE TYPE proc_mode_t      AS ENUM ('sum','max');
CREATE TYPE downtime_t       AS ENUM ('planned','unplanned','maintenance');
CREATE TYPE log_event_t      AS ENUM (
  'sample_created','sample_activated','sample_queued','sample_in_transit',
  'sample_arrived','sample_processing_started','sample_partially_complete',
  'sample_completed','sample_cancelled','sample_delayed','sample_redraw',
  'sample_rejected','sample_collected','sample_received','sample_picked_up',
  'test_completed','test_signed','test_dismissed','queue_inserted',
  'queue_recalculated','queue_lab_reassigned','tat_breach_alert',
  'lab_downtime_alert','processing_error','duplicate_webhook_skipped',
  'routing_assigned','batch_assigned','batch_missed','batch_reassigned',
  'eta_updated','report_saved','report_submitted','report_signed','routing_alert',
  'routing_failed','priority_override','routing_override'
);

-- Shared trigger for updated_at
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- Protect original SLA deadline from being overwritten (immutable per PRD Section 11)
CREATE OR REPLACE FUNCTION fn_protect_original_sla()
RETURNS TRIGGER AS $$
BEGIN
  -- If original_sla_deadline is being changed on UPDATE, restore the old value
  IF OLD.original_sla_deadline IS NOT NULL AND NEW.original_sla_deadline != OLD.original_sla_deadline THEN
    NEW.original_sla_deadline := OLD.original_sla_deadline;
  END IF;
  -- If original_tat_mins is being changed on UPDATE, restore the old value
  IF OLD.original_tat_mins IS NOT NULL AND NEW.original_tat_mins != OLD.original_tat_mins THEN
    NEW.original_tat_mins := OLD.original_tat_mins;
  END IF;
  NEW.updated_at := CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================
-- TABLE 1: tat_webhook_event  (ROOT PARENT)
-- ====================================================================
CREATE TABLE tat_webhook_event (
  id               BIGSERIAL    PRIMARY KEY,
  webhook_id       INT          DEFAULT NULL,
  webhook_type     VARCHAR(32)  NOT NULL,
  bill_id          BIGINT       NOT NULL,
  internal_bill_id INT          DEFAULT NULL,
  lab_id           INT          NOT NULL,
  payload          JSONB        NOT NULL,
  payload_hash     CHAR(64)     DEFAULT NULL,
  source_ip        VARCHAR(64)  DEFAULT NULL,
  auth_token_hash  CHAR(64)     DEFAULT NULL,
  status           webhook_status_t NOT NULL DEFAULT 'received',
  retry_count      SMALLINT     NOT NULL DEFAULT 0,
  error_message    TEXT         DEFAULT NULL,
  processed_at     TIMESTAMP    DEFAULT NULL,
  created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_event_dedup UNIQUE (bill_id, webhook_type, webhook_id)
);
CREATE INDEX idx_we_hash       ON tat_webhook_event(payload_hash);
CREATE INDEX idx_we_bill_id    ON tat_webhook_event(bill_id);
CREATE INDEX idx_we_type       ON tat_webhook_event(webhook_type);
CREATE INDEX idx_we_status     ON tat_webhook_event(status);
CREATE INDEX idx_we_lab_id     ON tat_webhook_event(lab_id);
CREATE INDEX idx_we_created_at ON tat_webhook_event(created_at);

-- ====================================================================
-- TABLE 1B: tat_reconciliation_queue
-- Durable retry queue for out-of-order webhook events.
-- ====================================================================
CREATE TABLE tat_reconciliation_queue (
  id                  BIGSERIAL    PRIMARY KEY,
  webhook_event_id    BIGINT       NOT NULL REFERENCES tat_webhook_event(id) ON DELETE CASCADE ON UPDATE CASCADE,
  webhook_type        VARCHAR(64)  NOT NULL,
  external_bill_id    BIGINT       DEFAULT NULL,
  prerequisite_type   VARCHAR(64)  NOT NULL,
  prerequisite_detail JSONB        DEFAULT NULL,
  attempt_count       SMALLINT     NOT NULL DEFAULT 0,
  max_attempts        SMALLINT     NOT NULL DEFAULT 10,
  next_attempt_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_attempt_at     TIMESTAMP    DEFAULT NULL,
  last_error          TEXT         DEFAULT NULL,
  status              VARCHAR(32)  NOT NULL DEFAULT 'pending',
  resolved_at         TIMESTAMP    DEFAULT NULL,
  created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_recon_event UNIQUE (webhook_event_id)
);
CREATE INDEX idx_rq_next_attempt ON tat_reconciliation_queue(next_attempt_at, status);
CREATE INDEX idx_rq_bill         ON tat_reconciliation_queue(external_bill_id);
CREATE INDEX idx_rq_status       ON tat_reconciliation_queue(status);
CREATE TRIGGER trg_rq_upd BEFORE UPDATE ON tat_reconciliation_queue FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 1C: tat_webhook_nonce
-- Nonce tracking table to prevent replay attacks even if Redis fails.
-- Stores (timestamp, signature_hash) pairs to ensure each webhook is processed only once.
-- ====================================================================
CREATE TABLE tat_webhook_nonce (
  id              BIGSERIAL    PRIMARY KEY,
  timestamp       BIGINT       NOT NULL,
  signature_hash  CHAR(64)     NOT NULL,
  webhook_type    VARCHAR(32)  NOT NULL,
  processed_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_nonce UNIQUE (timestamp, signature_hash)
);
CREATE INDEX idx_nonce_timestamp ON tat_webhook_nonce(timestamp);
CREATE INDEX idx_nonce_expiry   ON tat_webhook_nonce(processed_at);

-- ====================================================================
-- TABLE 2: tat_report_pdf_raw
-- ====================================================================
CREATE TABLE tat_report_pdf_raw (
  id                  BIGSERIAL   PRIMARY KEY,
  webhook_event_id    BIGINT      NOT NULL REFERENCES tat_webhook_event(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  external_report_id  BIGINT      NOT NULL,
  external_test_id    INT         DEFAULT NULL,
  test_code           VARCHAR(32) DEFAULT NULL,
  sample_accession_no VARCHAR(32) DEFAULT NULL,
  report_date         TIMESTAMP   DEFAULT NULL,
  approval_date       TIMESTAMP   DEFAULT NULL,
  is_signed           SMALLINT    NOT NULL DEFAULT 0,
  is_amended          SMALLINT    NOT NULL DEFAULT 0,
  report_base64       TEXT        DEFAULT NULL,
  storage_path        VARCHAR(512) DEFAULT NULL,
  created_at          TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_pdf_report UNIQUE (external_report_id)
);
CREATE INDEX idx_pdf_event  ON tat_report_pdf_raw(webhook_event_id);
CREATE INDEX idx_pdf_code   ON tat_report_pdf_raw(test_code);
CREATE INDEX idx_pdf_acc_no ON tat_report_pdf_raw(sample_accession_no);

-- ====================================================================
-- TABLE 3: tat_lab  (ROOT PARENT for lab tables)
-- ====================================================================
CREATE TABLE tat_lab (
  id                     SERIAL       PRIMARY KEY,
  external_lab_id        INT          DEFAULT NULL,
  lab_name               VARCHAR(256) NOT NULL,
  lab_code               VARCHAR(32)  NOT NULL,
  lab_type               SMALLINT     NOT NULL DEFAULT 0,
  timezone               VARCHAR(64)  NOT NULL DEFAULT 'UTC',
  max_concurrent_samples INT          NOT NULL DEFAULT 1,
  processing_mode        proc_mode_t  NOT NULL DEFAULT 'max',
  default_processing_mins INT         NOT NULL DEFAULT 90,
  next_available_time    TIMESTAMP    DEFAULT NULL,
  is_available           SMALLINT     NOT NULL DEFAULT 1,
  unavailable_until      TIMESTAMP    DEFAULT NULL,
  unavailability_reason  VARCHAR(256) DEFAULT NULL,
  is_fallback            SMALLINT     NOT NULL DEFAULT 0,
  is_active              SMALLINT     NOT NULL DEFAULT 1,
  created_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lab_code UNIQUE (lab_code)
);
CREATE INDEX idx_lab_ext_id    ON tat_lab(external_lab_id);
CREATE INDEX idx_lab_type      ON tat_lab(lab_type);
CREATE INDEX idx_lab_fallback  ON tat_lab(is_fallback);
CREATE INDEX idx_lab_next_avail ON tat_lab(next_available_time);
CREATE INDEX idx_lab_avail     ON tat_lab(is_available);
CREATE TRIGGER trg_lab_upd BEFORE UPDATE ON tat_lab FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 4B: tat_user
-- ====================================================================
CREATE TABLE tat_user (
  id             SERIAL        PRIMARY KEY,
  email          VARCHAR(255)  NOT NULL UNIQUE,
  full_name      VARCHAR(255)  DEFAULT NULL,
  role           VARCHAR(32)   NOT NULL,
  lab_id         INT           DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  org_internal_id INT          DEFAULT NULL,
  is_active      SMALLINT      NOT NULL DEFAULT 1,
  created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_user_role   ON tat_user(role);
CREATE INDEX idx_user_lab_id ON tat_user(lab_id);
CREATE INDEX idx_user_active ON tat_user(is_active);
CREATE TRIGGER trg_user_upd BEFORE UPDATE ON tat_user FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 4: tat_test_type_config
-- ====================================================================
CREATE TABLE tat_test_type_config (
  id                   SERIAL        PRIMARY KEY,
  external_test_id     INT           NOT NULL,
  test_code            VARCHAR(32)   NOT NULL,
  test_name            VARCHAR(256)  DEFAULT NULL,
  department_id        INT           DEFAULT NULL,
  department_name      VARCHAR(64)   DEFAULT NULL,
  test_category        VARCHAR(64)   DEFAULT NULL,
  processing_time_mins INT           NOT NULL DEFAULT 60,
  is_parallel_capable  SMALLINT      NOT NULL DEFAULT 1,
  default_priority     SMALLINT      NOT NULL DEFAULT 5,
  is_critical          SMALLINT      NOT NULL DEFAULT 0,
  is_batch_test        SMALLINT      NOT NULL DEFAULT 0,
  predefined_tat_hours NUMERIC(6,2)  DEFAULT NULL,
  tat_schedule_type    VARCHAR(64)   DEFAULT NULL,
  is_active            SMALLINT      NOT NULL DEFAULT 1,
  created_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_test_code UNIQUE (test_code)
);
CREATE INDEX idx_ttc_ext_id  ON tat_test_type_config(external_test_id);
CREATE INDEX idx_ttc_dept_id ON tat_test_type_config(department_id);
CREATE INDEX idx_ttc_critical ON tat_test_type_config(is_critical);
CREATE TRIGGER trg_ttc_upd BEFORE UPDATE ON tat_test_type_config FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 5: tat_bill
-- ====================================================================
CREATE TABLE tat_bill (
  id               BIGSERIAL      PRIMARY KEY,
  webhook_event_id BIGINT         NOT NULL REFERENCES tat_webhook_event(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  external_bill_id BIGINT         NOT NULL,
  external_lab_id  INT            NOT NULL,
  bill_status_type bill_status_t  NOT NULL DEFAULT 'preview',
  bill_time        TIMESTAMP      DEFAULT NULL,
  bill_update_time TIMESTAMP      DEFAULT NULL,
  bill_total_amount NUMERIC(12,2) DEFAULT NULL,
  due_amount       NUMERIC(12,2)  DEFAULT NULL,
  bill_advance     NUMERIC(12,2)  DEFAULT NULL,
  org_id           INT            DEFAULT NULL,
  org_name         VARCHAR(256)   DEFAULT NULL,
  client_type      VARCHAR(32)    NOT NULL DEFAULT 'walk_in',  -- walk_in | corporate | hospital
  org_internal_id  INT            DEFAULT NULL,
  source_lab_id    INT            DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  patient_id       INT            DEFAULT NULL,
  patient_name     VARCHAR(128)   DEFAULT NULL,
  patient_gender   VARCHAR(16)    DEFAULT NULL,
  patient_age      VARCHAR(32)    DEFAULT NULL,
  patient_internal_id INT         DEFAULT NULL,
  total_samples    INT            NOT NULL DEFAULT 0,
  completed_samples INT           NOT NULL DEFAULT 0,
  is_active        SMALLINT       NOT NULL DEFAULT 1,
  created_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_ext_bill UNIQUE (external_bill_id)
);
CREATE INDEX idx_bill_event   ON tat_bill(webhook_event_id);
CREATE INDEX idx_bill_ext_lab ON tat_bill(external_lab_id);
CREATE INDEX idx_bill_status  ON tat_bill(bill_status_type);
CREATE INDEX idx_bill_org     ON tat_bill(org_id);
CREATE INDEX idx_bill_org_internal     ON tat_bill(org_internal_id) WHERE org_internal_id IS NOT NULL;
CREATE INDEX idx_bill_patient_internal  ON tat_bill(patient_internal_id) WHERE patient_internal_id IS NOT NULL;
CREATE INDEX idx_bill_time    ON tat_bill(bill_time);
CREATE TRIGGER trg_bill_upd BEFORE UPDATE ON tat_bill FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 6: tat_sample  (PRIMARY QUEUE UNIT)
-- ====================================================================
CREATE TABLE tat_sample (
  id                  BIGSERIAL      PRIMARY KEY,
  bill_id             BIGINT         NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  webhook_event_id    BIGINT         NOT NULL REFERENCES tat_webhook_event(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  external_sample_id  BIGINT         NOT NULL,
  parent_sample_id    BIGINT         DEFAULT NULL REFERENCES tat_sample(id) ON DELETE SET NULL,
  cycle_number        INT            NOT NULL DEFAULT 1,
  accession_no        VARCHAR(32)    DEFAULT NULL,
  primary_sample_type VARCHAR(64)    DEFAULT NULL,
  primary_sample_name VARCHAR(64)    DEFAULT NULL,
  collected_at        TIMESTAMP      DEFAULT NULL,
  received_at         TIMESTAMP      DEFAULT NULL,
  arrived_at_lab      TIMESTAMP      DEFAULT NULL,
  total_tests         INT            NOT NULL DEFAULT 0,
  completed_tests     INT            NOT NULL DEFAULT 0,
  is_rejected         SMALLINT       NOT NULL DEFAULT 0,
  is_batch            SMALLINT       NOT NULL DEFAULT 0,
  batch_id            VARCHAR(32)    DEFAULT NULL,
  redraw              SMALLINT       NOT NULL DEFAULT 0,
  is_urgent           SMALLINT       NOT NULL DEFAULT 0,
  priority            SMALLINT       NOT NULL DEFAULT 5,
  status              sample_status_t NOT NULL DEFAULT 'draft',
  assigned_lab_id     INT            DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL ON UPDATE CASCADE,
  routing_reason      VARCHAR(128)   DEFAULT NULL,
  comments            VARCHAR(512)   DEFAULT NULL,
  completed_at        TIMESTAMP      DEFAULT NULL,
  is_active           SMALLINT       NOT NULL DEFAULT 1,
  created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_bill_sample UNIQUE (bill_id, external_sample_id)
);
CREATE INDEX idx_smp_ext_id   ON tat_sample(external_sample_id);
CREATE INDEX idx_smp_acc_no   ON tat_sample(accession_no);
CREATE INDEX idx_smp_bill     ON tat_sample(bill_id);
CREATE INDEX idx_smp_status   ON tat_sample(status);
CREATE INDEX idx_smp_lab      ON tat_sample(assigned_lab_id);
CREATE INDEX idx_smp_coll     ON tat_sample(collected_at);
CREATE INDEX idx_smp_arrived  ON tat_sample(arrived_at_lab);
CREATE INDEX idx_smp_priority ON tat_sample(priority);
CREATE INDEX idx_smp_event    ON tat_sample(webhook_event_id);
CREATE TRIGGER trg_smp_upd BEFORE UPDATE ON tat_sample FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 7: tat_test_instance
-- ====================================================================
CREATE TABLE tat_test_instance (
  id                         BIGSERIAL     PRIMARY KEY,
  sample_id                  BIGINT        NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id                    BIGINT        NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  webhook_event_id           BIGINT        NOT NULL REFERENCES tat_webhook_event(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  parent_instance_id         BIGINT        DEFAULT NULL REFERENCES tat_test_instance(id) ON DELETE SET NULL,
  cycle_number               SMALLINT      NOT NULL DEFAULT 1,
  is_current_cycle           SMALLINT      NOT NULL DEFAULT 1,
  external_report_id         BIGINT        NOT NULL,
  external_test_id           INT           DEFAULT NULL,
  external_dict_id           INT           DEFAULT NULL,
  lab_report_index           INT           DEFAULT NULL,
  test_code                  VARCHAR(32)   DEFAULT NULL,
  test_name                  VARCHAR(256)  DEFAULT NULL,
  test_category              VARCHAR(64)   DEFAULT NULL,
  department_id              INT           DEFAULT NULL,
  department_name            VARCHAR(64)   DEFAULT NULL,
  sample_type                VARCHAR(64)   DEFAULT NULL,
  sample_name                VARCHAR(64)   DEFAULT NULL,
  test_amount                NUMERIC(10,2) DEFAULT NULL,
  is_radiology               SMALLINT      NOT NULL DEFAULT 0,
  is_outsourced              SMALLINT      NOT NULL DEFAULT 0,
  processing_time_mins       INT           NOT NULL DEFAULT 60,
  processing_time_is_default SMALLINT      NOT NULL DEFAULT 0,
  processing_time_source     VARCHAR(32)   DEFAULT NULL,
  sample_date                TIMESTAMP     DEFAULT NULL,
  predicted_report_date      TIMESTAMP     DEFAULT NULL,
  report_date                TIMESTAMP     DEFAULT NULL,
  approval_date              TIMESTAMP     DEFAULT NULL,
  result                     TEXT          DEFAULT NULL,
  result_time                TIMESTAMP     DEFAULT NULL,
  accession_date             TIMESTAMP     DEFAULT NULL,
  is_signed                  SMALLINT      NOT NULL DEFAULT 0,
  is_amended                 SMALLINT      NOT NULL DEFAULT 0,
  processing_lab_id          INT           DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  routing_reason             VARCHAR(128)  DEFAULT NULL,
  completion_webhook_id      BIGINT        DEFAULT NULL REFERENCES tat_webhook_event(id) ON DELETE SET NULL ON UPDATE CASCADE,
  status                     test_status_t NOT NULL DEFAULT 'draft',
  is_active                  SMALLINT      NOT NULL DEFAULT 1,
  created_at                 TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at                 TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_ext_report  UNIQUE (external_report_id),
  CONSTRAINT uq_sample_test UNIQUE (sample_id, external_test_id)
);
CREATE INDEX idx_ti_sample   ON tat_test_instance(sample_id);
CREATE INDEX idx_ti_bill     ON tat_test_instance(bill_id);
CREATE INDEX idx_ti_event    ON tat_test_instance(webhook_event_id);
CREATE INDEX idx_ti_comp_evt ON tat_test_instance(completion_webhook_id);
CREATE INDEX idx_ti_ext_test ON tat_test_instance(external_test_id);
CREATE INDEX idx_ti_dept     ON tat_test_instance(department_id);
CREATE INDEX idx_ti_code     ON tat_test_instance(test_code);
CREATE INDEX idx_ti_status   ON tat_test_instance(status);
CREATE TRIGGER trg_ti_upd BEFORE UPDATE ON tat_test_instance FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 8: tat_lab_capability
-- ====================================================================
CREATE TABLE tat_lab_capability (
  id              SERIAL      PRIMARY KEY,
  lab_id          INT         NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  department_id   INT         NOT NULL,
  department_name VARCHAR(64) DEFAULT NULL,
  test_code       VARCHAR(32) DEFAULT NULL,
  is_active       SMALLINT    NOT NULL DEFAULT 1,
  created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lab_dept UNIQUE (lab_id, department_id, test_code)
);
CREATE INDEX idx_lc_lab  ON tat_lab_capability(lab_id);
CREATE INDEX idx_lc_dept ON tat_lab_capability(department_id);

-- ====================================================================
-- TABLE 9: tat_lab_queue  (SCHEDULING TABLE)
-- ====================================================================
CREATE TABLE tat_lab_queue (
  id                       BIGSERIAL      PRIMARY KEY,
  sample_id                BIGINT         NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  lab_id                   INT            NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id                  BIGINT         NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  initial_queue_position   INT            DEFAULT NULL,
  priority                 SMALLINT       NOT NULL DEFAULT 5,
  processing_time_sum_mins INT            NOT NULL DEFAULT 0,
  processing_time_max_mins INT            NOT NULL DEFAULT 0,
  processing_time_mins     INT            NOT NULL DEFAULT 0,
  arrival_time             TIMESTAMP      NOT NULL,
  estimated_start_time     TIMESTAMP      DEFAULT NULL,
  estimated_end_time       TIMESTAMP      DEFAULT NULL,
  actual_start_time        TIMESTAMP      DEFAULT NULL,
  actual_end_time          TIMESTAMP      DEFAULT NULL,
  status                   queue_status_t NOT NULL DEFAULT 'scheduled',
  skip_reason              VARCHAR(256)   DEFAULT NULL,
  recalculation_count      INT            NOT NULL DEFAULT 0,
  last_recalculated_at     TIMESTAMP      DEFAULT NULL,
  created_at               TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at               TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_sample_lab UNIQUE (sample_id, lab_id)
);
CREATE INDEX idx_lq_lab       ON tat_lab_queue(lab_id);
CREATE INDEX idx_lq_sample    ON tat_lab_queue(sample_id);
CREATE INDEX idx_lq_bill      ON tat_lab_queue(bill_id);
CREATE INDEX idx_lq_status    ON tat_lab_queue(status);
CREATE INDEX idx_lq_priority  ON tat_lab_queue(priority);
CREATE INDEX idx_lq_est_start ON tat_lab_queue(estimated_start_time);
CREATE INDEX idx_lq_est_end   ON tat_lab_queue(estimated_end_time);
CREATE INDEX idx_lq_arrival   ON tat_lab_queue(arrival_time);
CREATE INDEX idx_lq_scheduler ON tat_lab_queue(lab_id, status, priority, estimated_start_time);
CREATE INDEX idx_lq_sweep     ON tat_lab_queue(lab_id, estimated_end_time, status);
CREATE TRIGGER trg_lq_upd BEFORE UPDATE ON tat_lab_queue FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 10: tat_eta  (SAMPLE-LEVEL ETA) - DEPRECATED
-- ====================================================================
-- DEPRECATED: Use tat_eta_record (per-test-instance ETA) instead.
-- This table is kept for backward compatibility with existing queries.
-- New code should use tat_eta_record for accurate multi-lab processing ETA tracking.
CREATE TABLE tat_eta (
  id                    BIGSERIAL    PRIMARY KEY,
  sample_id             BIGINT       NOT NULL REFERENCES tat_sample(id) ON DELETE CASCADE ON UPDATE CASCADE,
  queue_entry_id        BIGINT       DEFAULT NULL REFERENCES tat_lab_queue(id) ON DELETE SET NULL ON UPDATE CASCADE,
  bill_id               BIGINT       NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  collection_time       TIMESTAMP    NOT NULL,
  arrival_time_at_lab   TIMESTAMP    NOT NULL,
  estimated_start_time  TIMESTAMP    NOT NULL,
  estimated_end_time    TIMESTAMP    NOT NULL,
  queue_wait_mins       INT          NOT NULL,
  lab_processing_mins   INT          NOT NULL,
  lab_eta_mins          INT          NOT NULL,
  total_eta_mins        INT          NOT NULL,
  predefined_tat_mins   INT          DEFAULT NULL,
  is_tat_breached       SMALLINT     NOT NULL DEFAULT 0,
  breach_by_mins        INT          DEFAULT NULL,
  actual_end_time       TIMESTAMP    DEFAULT NULL,
  actual_total_eta_mins INT          DEFAULT NULL,
  actual_lab_eta_mins   INT          DEFAULT NULL,
  actual_tat_breached   SMALLINT     DEFAULT NULL,
  version               INT          NOT NULL DEFAULT 1,
  calculated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_sample_eta UNIQUE (sample_id)
);
CREATE INDEX idx_eta_queue   ON tat_eta(queue_entry_id);
CREATE INDEX idx_eta_bill    ON tat_eta(bill_id);
CREATE INDEX idx_eta_end     ON tat_eta(estimated_end_time);
CREATE INDEX idx_eta_breach  ON tat_eta(is_tat_breached);
CREATE INDEX idx_eta_collect ON tat_eta(collection_time);
CREATE TRIGGER trg_eta_upd BEFORE UPDATE ON tat_eta FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 11: tat_eta_history  (IMMUTABLE — never delete)
-- ====================================================================
CREATE TABLE tat_eta_history (
  id                   BIGSERIAL   PRIMARY KEY,
  sample_id            BIGINT      NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  eta_id               BIGINT      NOT NULL REFERENCES tat_eta(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  version              INT         NOT NULL,
  collection_time      TIMESTAMP   NOT NULL,
  arrival_time_at_lab  TIMESTAMP   NOT NULL,
  estimated_start_time TIMESTAMP   NOT NULL,
  estimated_end_time   TIMESTAMP   NOT NULL,
  queue_wait_mins      INT         NOT NULL,
  lab_eta_mins         INT         NOT NULL,
  total_eta_mins       INT         NOT NULL,
  predefined_tat_mins  INT         DEFAULT NULL,
  is_tat_breached      SMALLINT    NOT NULL DEFAULT 0,
  breach_by_mins       INT         DEFAULT NULL,
  recalculation_reason VARCHAR(128) DEFAULT NULL,
  triggered_by         VARCHAR(64)  DEFAULT NULL,
  snapshotted_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_eh_sample      ON tat_eta_history(sample_id);
CREATE INDEX idx_eh_eta         ON tat_eta_history(eta_id);
CREATE INDEX idx_eh_version     ON tat_eta_history(sample_id, version);
CREATE INDEX idx_eh_snapshot    ON tat_eta_history(snapshotted_at);

-- ====================================================================
-- TABLE 12: tat_log  (APPEND-ONLY AUDIT)
-- ====================================================================
CREATE TABLE tat_log (
  id                    BIGSERIAL    PRIMARY KEY,
  sample_id             BIGINT       NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id               BIGINT       NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  test_instance_id      BIGINT       DEFAULT NULL REFERENCES tat_test_instance(id) ON DELETE SET NULL ON UPDATE CASCADE,
  lab_id                INT          DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL ON UPDATE CASCADE,
  event_type            log_event_t  NOT NULL,
  event_timestamp       TIMESTAMP    NOT NULL,
  triggered_by          VARCHAR(64)  DEFAULT NULL,
  webhook_event_id      BIGINT       DEFAULT NULL REFERENCES tat_webhook_event(id) ON DELETE SET NULL ON UPDATE CASCADE,
  queue_position        INT          DEFAULT NULL,
  queue_status          VARCHAR(32)  DEFAULT NULL,
  eta_minutes_remaining INT          DEFAULT NULL,
  elapsed_mins          INT          DEFAULT NULL,
  notes                 VARCHAR(512) DEFAULT NULL,
  metadata              JSONB        DEFAULT NULL,
  created_at            TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_log_sample   ON tat_log(sample_id);
CREATE INDEX idx_log_bill     ON tat_log(bill_id);
CREATE INDEX idx_log_ti       ON tat_log(test_instance_id);
CREATE INDEX idx_log_type     ON tat_log(event_type);
CREATE INDEX idx_log_ts       ON tat_log(event_timestamp);
CREATE INDEX idx_log_lab      ON tat_log(lab_id);
CREATE INDEX idx_log_event    ON tat_log(webhook_event_id);

-- ====================================================================
-- TABLE 13: tat_lab_test_override
-- ====================================================================
CREATE TABLE tat_lab_test_override (
  id                   SERIAL       PRIMARY KEY,
  lab_id               INT          NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  test_code            VARCHAR(32)  NOT NULL REFERENCES tat_test_type_config(test_code) ON DELETE RESTRICT ON UPDATE CASCADE,
  test_name            VARCHAR(256) DEFAULT NULL,
  processing_time_mins INT          NOT NULL,
  notes                VARCHAR(256) DEFAULT NULL,
  is_active            SMALLINT     NOT NULL DEFAULT 1,
  created_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lab_test UNIQUE (lab_id, test_code)
);
CREATE INDEX idx_lto_lab  ON tat_lab_test_override(lab_id);
CREATE INDEX idx_lto_code ON tat_lab_test_override(test_code);
CREATE TRIGGER trg_lto_upd BEFORE UPDATE ON tat_lab_test_override FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 14: tat_lab_downtime
-- ====================================================================
CREATE TABLE tat_lab_downtime (
  id               SERIAL        PRIMARY KEY,
  lab_id           INT           NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  downtime_type    downtime_t    NOT NULL DEFAULT 'unplanned',
  start_time       TIMESTAMP     NOT NULL,
  end_time         TIMESTAMP     DEFAULT NULL,
  reason           VARCHAR(256)  DEFAULT NULL,
  affected_samples INT           DEFAULT NULL,
  resolved_at      TIMESTAMP     DEFAULT NULL,
  created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_ld_lab   ON tat_lab_downtime(lab_id);
CREATE INDEX idx_ld_start ON tat_lab_downtime(start_time);
CREATE INDEX idx_ld_end   ON tat_lab_downtime(end_time);
CREATE TRIGGER trg_ld_upd BEFORE UPDATE ON tat_lab_downtime FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- PHASE 1 REDESIGN ADDITIONS
-- ====================================================================
CREATE TABLE tat_org (
  id               SERIAL        PRIMARY KEY,
  external_org_id  INT           NOT NULL,
  org_name         VARCHAR(256)  NOT NULL,
  org_code         VARCHAR(64)   DEFAULT NULL,
  org_type         VARCHAR(32)   NOT NULL DEFAULT 'corporate',
  sla_tier         VARCHAR(32)   NOT NULL DEFAULT 'standard',
  default_priority SMALLINT      NOT NULL DEFAULT 5,
  contact_email    VARCHAR(255)  DEFAULT NULL,
  contact_phone    VARCHAR(32)   DEFAULT NULL,
  address          TEXT          DEFAULT NULL,
  is_active        SMALLINT      NOT NULL DEFAULT 1,
  created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_org_external UNIQUE (external_org_id)
);
CREATE INDEX idx_org_name   ON tat_org(org_name);
CREATE INDEX idx_org_active ON tat_org(is_active);
CREATE TRIGGER trg_org_upd BEFORE UPDATE ON tat_org FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TABLE tat_patient (
  id                  SERIAL        PRIMARY KEY,
  external_patient_id  INT           NOT NULL,
  patient_name         VARCHAR(256)  NOT NULL,
  patient_gender       VARCHAR(16)   DEFAULT NULL,
  patient_dob          DATE          DEFAULT NULL,
  patient_age_str      VARCHAR(32)   DEFAULT NULL,
  contact_phone        VARCHAR(32)   DEFAULT NULL,
  contact_email        VARCHAR(255)  DEFAULT NULL,
  is_active            SMALLINT      NOT NULL DEFAULT 1,
  created_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_patient_external UNIQUE (external_patient_id)
);
CREATE INDEX idx_patient_name  ON tat_patient(patient_name);
CREATE INDEX idx_patient_phone ON tat_patient(contact_phone);
CREATE TRIGGER trg_patient_upd BEFORE UPDATE ON tat_patient FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

ALTER TABLE tat_bill
  ADD CONSTRAINT fk_bill_org_internal
  FOREIGN KEY (org_internal_id) REFERENCES tat_org(id) ON DELETE SET NULL;

ALTER TABLE tat_bill
  ADD CONSTRAINT fk_bill_patient_internal
  FOREIGN KEY (patient_internal_id) REFERENCES tat_patient(id) ON DELETE SET NULL;

ALTER TABLE tat_user
  ADD CONSTRAINT fk_user_org_internal
  FOREIGN KEY (org_internal_id) REFERENCES tat_org(id) ON DELETE SET NULL;

CREATE TABLE tat_processing_assignment (
  id                      BIGSERIAL     PRIMARY KEY,
  sample_id               BIGINT        NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id                 BIGINT        NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  test_instance_id        BIGINT        NOT NULL REFERENCES tat_test_instance(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  source_lab_id           INT           DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  destination_lab_id      INT           DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  outsource_vendor_name   VARCHAR(256)  DEFAULT NULL,
  predicted_eta           TIMESTAMP     DEFAULT NULL,
  actual_processing_start TIMESTAMP     DEFAULT NULL,
  actual_processing_end   TIMESTAMP     DEFAULT NULL,
  route_reason            VARCHAR(128)  DEFAULT NULL,
  assignment_status       VARCHAR(32)   NOT NULL DEFAULT 'assigned',
  created_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_processing_assignment UNIQUE (test_instance_id)
);
CREATE INDEX idx_pa_sample   ON tat_processing_assignment(sample_id);
CREATE INDEX idx_pa_bill     ON tat_processing_assignment(bill_id);
CREATE INDEX idx_pa_test     ON tat_processing_assignment(test_instance_id);
CREATE INDEX idx_pa_dest     ON tat_processing_assignment(destination_lab_id);
CREATE TRIGGER trg_pa_upd BEFORE UPDATE ON tat_processing_assignment FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TABLE tat_lab_edos (
  id                    SERIAL        PRIMARY KEY,
  lab_id                INT           NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  test_code             VARCHAR(32)   NOT NULL REFERENCES tat_test_type_config(test_code) ON DELETE RESTRICT ON UPDATE CASCADE,
  department_id         INT           DEFAULT NULL,
  department_name       VARCHAR(64)   DEFAULT NULL,
  processing_time_mins  INT           NOT NULL,
  committed_tat_hours   NUMERIC(8,2)  DEFAULT NULL,
  processing_mode       VARCHAR(8)    NOT NULL DEFAULT 'max',
  is_outsourced         SMALLINT      NOT NULL DEFAULT 0,
  outsource_vendor_name VARCHAR(256)  DEFAULT NULL,
  outsource_buffer_mins INT           DEFAULT NULL,
  is_active             SMALLINT      NOT NULL DEFAULT 1,
  notes                 TEXT          DEFAULT NULL,
  effective_from        TIMESTAMP     DEFAULT NULL,
  effective_until       TIMESTAMP     DEFAULT NULL,
  created_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lab_edos UNIQUE (lab_id, test_code)
);
CREATE INDEX idx_le_lab      ON tat_lab_edos(lab_id);
CREATE INDEX idx_le_code     ON tat_lab_edos(test_code);
CREATE INDEX idx_le_dept     ON tat_lab_edos(department_id);
CREATE INDEX idx_le_active   ON tat_lab_edos(is_active);
CREATE INDEX idx_le_outsourced ON tat_lab_edos(is_outsourced);
CREATE TRIGGER trg_le_upd BEFORE UPDATE ON tat_lab_edos FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE TABLE tat_sla_record (
  id                      BIGSERIAL     PRIMARY KEY,
  test_instance_id        BIGINT        NOT NULL REFERENCES tat_test_instance(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  sample_id               BIGINT        NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id                 BIGINT        NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  original_sla_deadline   TIMESTAMP     NOT NULL,
  predicted_sla_deadline  TIMESTAMP     DEFAULT NULL,
  revised_sla_deadline    TIMESTAMP     DEFAULT NULL,
  actual_completion_time  TIMESTAMP     DEFAULT NULL,
  original_tat_mins       INT           DEFAULT NULL,
  predicted_tat_mins      INT           DEFAULT NULL,
  revised_tat_mins        INT           DEFAULT NULL,
  actual_tat_mins         INT           DEFAULT NULL,
  is_original_breached    SMALLINT      DEFAULT NULL,
  is_predicted_breached   SMALLINT      DEFAULT NULL,
  is_revised_breached     SMALLINT      DEFAULT NULL,
  breach_by_mins          INT           DEFAULT NULL,
  is_suspended            SMALLINT      NOT NULL DEFAULT 0,
  suspended_at            TIMESTAMP     DEFAULT NULL,
  suspension_reason       VARCHAR(128)  DEFAULT NULL,
  resumed_at              TIMESTAMP     DEFAULT NULL,
  revision_reason         VARCHAR(128)  DEFAULT NULL,
  notes                   VARCHAR(512)  DEFAULT NULL,
  created_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_sla_test UNIQUE (test_instance_id)
);
CREATE INDEX idx_sla_sample    ON tat_sla_record(sample_id);
CREATE INDEX idx_sla_bill      ON tat_sla_record(bill_id);
CREATE INDEX idx_sla_deadline  ON tat_sla_record(original_sla_deadline);
CREATE INDEX idx_sla_actual    ON tat_sla_record(actual_completion_time);
CREATE TRIGGER trg_sla_upd BEFORE UPDATE ON tat_sla_record FOR EACH ROW EXECUTE FUNCTION fn_protect_original_sla();

CREATE TABLE tat_alert (
  id                BIGSERIAL    PRIMARY KEY,
  bill_id           BIGINT       DEFAULT NULL REFERENCES tat_bill(id) ON DELETE SET NULL,
  sample_id         BIGINT       DEFAULT NULL REFERENCES tat_sample(id) ON DELETE SET NULL,
  test_instance_id  BIGINT       DEFAULT NULL REFERENCES tat_test_instance(id) ON DELETE SET NULL,
  lab_id            INT          DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL,
  alert_type        VARCHAR(64)  NOT NULL,
  severity          VARCHAR(16)  NOT NULL DEFAULT 'medium',
  message           TEXT         NOT NULL,
  is_acknowledged   SMALLINT     NOT NULL DEFAULT 0,
  acknowledged_by   INT          DEFAULT NULL REFERENCES tat_user(id) ON DELETE SET NULL,
  acknowledged_at   TIMESTAMP    DEFAULT NULL,
  created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_alert_type ON tat_alert(alert_type);
CREATE INDEX idx_alert_lab ON tat_alert(lab_id);
CREATE INDEX idx_alert_ack ON tat_alert(is_acknowledged);
CREATE INDEX idx_alert_created ON tat_alert(created_at);

CREATE TABLE tat_eta_record (
  id                      BIGSERIAL     PRIMARY KEY,
  test_instance_id        BIGINT        NOT NULL REFERENCES tat_test_instance(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  queue_entry_id          BIGINT        DEFAULT NULL REFERENCES tat_lab_queue(id) ON DELETE SET NULL ON UPDATE CASCADE,
  sample_id               BIGINT        NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  bill_id                 BIGINT        NOT NULL REFERENCES tat_bill(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  lab_id                  INT           DEFAULT NULL REFERENCES tat_lab(id) ON DELETE SET NULL ON UPDATE CASCADE,
  collection_time         TIMESTAMP     NOT NULL,
  arrival_time_at_lab     TIMESTAMP     NOT NULL,
  estimated_start_time    TIMESTAMP     NOT NULL,
  estimated_end_time      TIMESTAMP     NOT NULL,
  queue_wait_mins         INT           NOT NULL,
  lab_processing_mins     INT           NOT NULL,
  total_eta_mins          INT           NOT NULL,
  predefined_tat_mins     INT           DEFAULT NULL,
  is_tat_breached         SMALLINT      NOT NULL DEFAULT 0,
  breach_by_mins          INT           DEFAULT NULL,
  actual_end_time         TIMESTAMP     DEFAULT NULL,
  version                 INT           NOT NULL DEFAULT 1,
  recalculation_reason    VARCHAR(128)  DEFAULT NULL,
  triggered_by            VARCHAR(64)   DEFAULT NULL,
  calculated_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_eta_test_instance UNIQUE (test_instance_id)
);
CREATE INDEX idx_eta_record_queue ON tat_eta_record(queue_entry_id);
CREATE INDEX idx_eta_record_bill  ON tat_eta_record(bill_id);
CREATE INDEX idx_eta_record_samp  ON tat_eta_record(sample_id);
CREATE INDEX idx_eta_record_lab   ON tat_eta_record(lab_id);
CREATE INDEX idx_eta_record_end   ON tat_eta_record(estimated_end_time);
CREATE TRIGGER trg_eta_record_upd BEFORE UPDATE ON tat_eta_record FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- SEED DATA
-- ====================================================================
INSERT INTO tat_lab (lab_name, lab_code, lab_type, max_concurrent_samples, processing_mode, default_processing_mins, is_fallback, is_active) VALUES
  ('Aspira Main Lab (Fallback)', 'MAIN',   0, 5, 'max',  90, 1, 1),
  ('Haematology Lab',            'HAEM',   1, 3, 'max',  60, 0, 1),
  ('Biochemistry Lab',           'BIOCHEM',2, 3, 'max',  75, 0, 1),
  ('Clinical Pathology Lab',     'CPATH',  3, 2, 'sum',  45, 0, 1),
  ('Microbiology Lab',           'MICRO',  4, 2, 'sum', 120, 0, 1);

INSERT INTO tat_user (email, full_name, role, lab_id, is_active) VALUES
  ('admin@aspira.com',     'System Administrator',  'admin',     NULL, 1),
  ('super_admin@aspira.com','Super Administrator',  'super_admin',NULL, 1),
  ('logistics@aspira.com',  'Logistics Coordinator', 'logistics', NULL, 1),
  ('doctor@aspira.com',     'Medical Officer',       'doctor',    NULL, 1),
  ('lab_admin_main@aspira.com', 'Main Lab Admin',     'lab_admin', 1,    1),
  ('lab_main@aspira.com',   'Main Lab Tech',         'lab',       1,    1),
  ('lab_haem@aspira.com',   'Haematology Tech',      'lab',       2,    1),
  ('lab_biochem@aspira.com','Biochemistry Tech',     'lab',       3,    1),
  ('lab_cpath@aspira.com',  'Pathology Tech',        'lab',       4,    1),
  ('lab_micro@aspira.com',  'Microbiology Tech',     'lab',       5,    1)
ON CONFLICT (email) DO UPDATE
  SET full_name = EXCLUDED.full_name,
      role = EXCLUDED.role,
      lab_id = EXCLUDED.lab_id,
      is_active = EXCLUDED.is_active,
      updated_at = CURRENT_TIMESTAMP;

INSERT INTO tat_test_type_config
  (external_test_id, test_code, test_name, department_id, department_name, test_category, processing_time_mins, is_parallel_capable, default_priority, is_critical, predefined_tat_hours) VALUES
  (236290,'BIOC074', 'Creatinine',                      913,'BIOCHEMISTRY',      'Biochemistry', 45,1,5,0, 4.0),
  (234978,'BIOCP029','Liver Function Test - Mini',       913,'BIOCHEMISTRY',      'Profiles',     90,1,5,0, 6.0),
  (234986,'BIOCP044','Renal Function Tests-2 RFT Mini',  913,'BIOCHEMISTRY',      'I',            75,1,5,0, 6.0),
  (230964,'HAEM022', 'Extended CBC Haemogram',           906,'HAEMATOLOGY',       'A',            45,1,5,0, 3.0),
  (231107,'HAEM029', 'HbA1c Glycated Haemoglobin',       906,'HAEMATOLOGY',       'Special Bio', 120,0,5,0, 8.0),
  (231287,'CIPA020', 'Routine Examination Urine',        915,'CLINICAL PATHOLOGY','Clin Path',    30,1,5,0, 2.0);

INSERT INTO tat_lab_capability (lab_id, department_id, department_name) VALUES
  (2, 906,'HAEMATOLOGY'),
  (3, 913,'BIOCHEMISTRY'),
  (4, 915,'CLINICAL PATHOLOGY'),
  (5, 916,'MICROBIOLOGY'),
  (1, 906,'HAEMATOLOGY'),
  (1, 913,'BIOCHEMISTRY'),
  (1, 915,'CLINICAL PATHOLOGY'),
  (1, 916,'MICROBIOLOGY');

-- ====================================================================
-- TABLE 15: tat_lab_batch_schedule  (admin-configured via API)
-- ====================================================================
CREATE TABLE tat_lab_batch_schedule (
  id           SERIAL       PRIMARY KEY,
  lab_id       INT          NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  batch_time   TIME         NOT NULL,
  batch_day    SMALLINT     DEFAULT NULL,  -- 0=Mon..6=Sun, NULL=every day
  max_capacity INT          NOT NULL DEFAULT 50,
  is_active    SMALLINT     NOT NULL DEFAULT 1,
  notes        VARCHAR(256) DEFAULT NULL,
  created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_lab_batch UNIQUE (lab_id, batch_time, batch_day)
);
CREATE INDEX idx_lbs_lab    ON tat_lab_batch_schedule(lab_id);
CREATE INDEX idx_lbs_active ON tat_lab_batch_schedule(is_active);
CREATE TRIGGER trg_lbs_upd BEFORE UPDATE ON tat_lab_batch_schedule FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 16: tat_lab_batch_assignment
-- ====================================================================
CREATE TABLE tat_lab_batch_assignment (
  id                BIGSERIAL   PRIMARY KEY,
  lab_id            INT         NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  sample_id         BIGINT      NOT NULL REFERENCES tat_sample(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  batch_date        DATE        NOT NULL,
  batch_time        TIMESTAMP   NOT NULL,
  batch_schedule_id INT         DEFAULT NULL REFERENCES tat_lab_batch_schedule(id) ON DELETE SET NULL,
  status            VARCHAR(32) NOT NULL DEFAULT 'assigned',
  -- status values: assigned | processed | missed | reassigned
  reassigned_to     TIMESTAMP   DEFAULT NULL,
  missed_at         TIMESTAMP   DEFAULT NULL,
  created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_sample_batch UNIQUE (sample_id, lab_id)
);
CREATE INDEX idx_lba_lab    ON tat_lab_batch_assignment(lab_id);
CREATE INDEX idx_lba_sample ON tat_lab_batch_assignment(sample_id);
CREATE INDEX idx_lba_batch  ON tat_lab_batch_assignment(batch_time);
CREATE INDEX idx_lba_status ON tat_lab_batch_assignment(status);
CREATE INDEX idx_lba_sweep  ON tat_lab_batch_assignment(lab_id, batch_time, status);
CREATE TRIGGER trg_lba_upd BEFORE UPDATE ON tat_lab_batch_assignment FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- TABLE 17: tat_test_routing  (admin fallback, pre-seeded by department)
-- ====================================================================
CREATE TABLE tat_test_routing (
  id                SERIAL       PRIMARY KEY,
  test_code         VARCHAR(32)  DEFAULT NULL,   -- NULL = applies to whole department
  department_id     INT          DEFAULT NULL,
  processing_lab_id INT          NOT NULL REFERENCES tat_lab(id) ON DELETE RESTRICT ON UPDATE CASCADE,
  is_active         SMALLINT     NOT NULL DEFAULT 1,
  notes             VARCHAR(256) DEFAULT NULL,
  created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_test_routing UNIQUE (test_code, department_id)
);
CREATE INDEX idx_tr_code ON tat_test_routing(test_code);
CREATE INDEX idx_tr_dept ON tat_test_routing(department_id);
CREATE TRIGGER trg_tr_upd BEFORE UPDATE ON tat_test_routing FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- ====================================================================
-- VIEWS FOR DYNAMIC BILL STATUS (PRD Section 15.2)
-- ====================================================================
-- Dynamic bill status computation based on test instance states
-- PENDING: all tests pending
-- PARTIAL: some tests complete
-- COMPLETED: all tests complete
-- ACTION_REQUIRED: if any redraw exists
-- NOTE: View disabled due to missing ti.redraw column in tat_test_instance
-- The redraw column exists in tat_sample, not tat_test_instance
-- CREATE OR REPLACE VIEW v_bill_status AS
-- SELECT
--   b.id,
--   b.external_bill_id,
--   b.bill_status_type,
--   CASE
--     WHEN COUNT(*) FILTER (WHERE ti.redraw = 1) > 0 THEN 'ACTION_REQUIRED'
--     WHEN COUNT(*) FILTER (WHERE ti.status NOT IN ('cancelled', 'invalidated')) = 0 THEN 'PENDING'
--     WHEN COUNT(*) FILTER (WHERE ti.status = 'completed') = COUNT(*) FILTER (WHERE ti.status NOT IN ('cancelled', 'invalidated')) THEN 'COMPLETED'
--     WHEN COUNT(*) FILTER (WHERE ti.status = 'completed') > 0 THEN 'PARTIAL'
--     ELSE 'PENDING'
--   END AS computed_status,
--   COUNT(*) FILTER (WHERE ti.status NOT IN ('cancelled', 'invalidated')) AS active_tests,
--   COUNT(*) FILTER (WHERE ti.status = 'completed') AS completed_tests,
--   COUNT(*) FILTER (WHERE ti.redraw = 1) AS redraw_count
-- FROM tat_bill b
-- LEFT JOIN tat_test_instance ti ON b.id = ti.bill_id
-- GROUP BY b.id, b.external_bill_id, b.bill_status_type;

-- Seed: department-level fallback routing (used only if capability lookup fails)
INSERT INTO tat_test_routing (department_id, processing_lab_id, notes) VALUES
  (906, 2, 'HAEMATOLOGY fallback → HAEM Lab'),
  (913, 3, 'BIOCHEMISTRY fallback → BIOCHEM Lab'),
  (915, 4, 'CLINICAL PATHOLOGY fallback → CPATH Lab'),
  (916, 5, 'MICROBIOLOGY fallback → MICRO Lab');

INSERT INTO tat_lab_edos (lab_id, test_code, department_id, department_name, processing_time_mins, committed_tat_hours, processing_mode, is_outsourced, outsource_buffer_mins, is_active, notes)
SELECT l.id, t.test_code, t.department_id, t.department_name, t.processing_time_mins, t.predefined_tat_hours, l.processing_mode::varchar, 0, 0, 1, 'Seeded from master config'
FROM tat_lab l
CROSS JOIN tat_test_type_config t
WHERE l.is_active = 1 AND t.is_active = 1
ON CONFLICT (lab_id, test_code) DO NOTHING;
