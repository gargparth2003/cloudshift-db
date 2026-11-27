\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS control.application_routes (
    route_key text PRIMARY KEY,
    active_endpoint control.endpoint_role NOT NULL CHECK (active_endpoint IN ('SOURCE', 'TARGET')),
    writes_enabled boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO control.application_routes (route_key, active_endpoint, writes_enabled)
VALUES ('parth-commerce-application', 'SOURCE', true)
ON CONFLICT (route_key) DO NOTHING;
