\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.cutover_stages (
    cutover_stage_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cutover_id uuid NOT NULL REFERENCES control.cutover_history(cutover_id) ON DELETE CASCADE,
    stage_name text NOT NULL,
    stage_order integer NOT NULL CHECK (stage_order > 0),
    status text NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED')),
    started_at timestamptz,
    completed_at timestamptz,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    UNIQUE (cutover_id, stage_name)
);

CREATE INDEX IF NOT EXISTS idx_cutover_stages_cutover_order
    ON control.cutover_stages(cutover_id, stage_order);
