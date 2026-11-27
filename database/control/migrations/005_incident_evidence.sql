\set ON_ERROR_STOP on

ALTER TABLE control.migration_incidents
    ADD COLUMN IF NOT EXISTS affected_resources text[] NOT NULL DEFAULT '{}'::text[],
    ADD COLUMN IF NOT EXISTS supporting_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS detection_duration_ms bigint CHECK (detection_duration_ms IS NULL OR detection_duration_ms >= 0),
    ADD COLUMN IF NOT EXISTS recovery_timestamp timestamptz,
    ADD COLUMN IF NOT EXISTS recovery_duration_ms bigint CHECK (recovery_duration_ms IS NULL OR recovery_duration_ms >= 0),
    ADD COLUMN IF NOT EXISTS remaining_risk text;
