\set ON_ERROR_STOP on

CREATE SCHEMA shard;
CREATE TABLE shard.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_ref text NOT NULL UNIQUE,
    region_code text NOT NULL,
    full_name text NOT NULL,
    annual_value numeric(14,2) NOT NULL CHECK (annual_value >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (region_code = current_setting('cloudshift.region'))
);

INSERT INTO shard.customers (tenant_ref, region_code, full_name, annual_value)
SELECT current_setting('cloudshift.region') || '-' || series,
       current_setting('cloudshift.region'),
       'Shard Customer ' || series,
       (series * 17.25)::numeric(14,2)
FROM generate_series(1, 1000) AS series;

CREATE INDEX idx_shard_customers_region_value ON shard.customers (region_code, annual_value DESC);
