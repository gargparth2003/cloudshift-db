\set ON_ERROR_STOP on

CREATE SCHEMA commerce;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE TABLE commerce.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_ref text NOT NULL UNIQUE,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    region_code char(2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT customers_email_format CHECK (position('@' IN email) > 1)
);

CREATE TABLE commerce.customer_addresses (
    address_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES commerce.customers(customer_id) ON DELETE CASCADE,
    address_type text NOT NULL CHECK (address_type IN ('BILLING', 'SHIPPING')),
    city text NOT NULL,
    state text NOT NULL,
    postal_code text NOT NULL,
    country_code char(2) NOT NULL DEFAULT 'IN',
    UNIQUE (customer_id, address_type)
);

CREATE TABLE commerce.product_categories (
    category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    description text
);

CREATE TABLE commerce.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category_id bigint NOT NULL REFERENCES commerce.product_categories(category_id),
    name text NOT NULL,
    description text,
    price numeric(12,2) NOT NULL CHECK (price >= 0),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE commerce.warehouses (
    warehouse_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    region_code char(2) NOT NULL
);

CREATE TABLE commerce.suppliers (
    supplier_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    contact_email text NOT NULL
);

CREATE TABLE commerce.inventory (
    warehouse_id bigint NOT NULL REFERENCES commerce.warehouses(warehouse_id),
    product_id bigint NOT NULL REFERENCES commerce.products(product_id),
    supplier_id bigint REFERENCES commerce.suppliers(supplier_id),
    quantity_on_hand integer NOT NULL CHECK (quantity_on_hand >= 0),
    quantity_reserved integer NOT NULL DEFAULT 0 CHECK (quantity_reserved >= 0),
    reorder_level integer NOT NULL DEFAULT 10 CHECK (reorder_level >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (warehouse_id, product_id),
    CONSTRAINT inventory_reservation_valid CHECK (quantity_reserved <= quantity_on_hand)
);

CREATE TABLE commerce.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_ref text NOT NULL UNIQUE,
    customer_id bigint NOT NULL REFERENCES commerce.customers(customer_id),
    status text NOT NULL CHECK (status IN ('PENDING', 'PAID', 'FULFILLING', 'SHIPPED', 'CANCELLED')),
    currency char(3) NOT NULL DEFAULT 'INR',
    subtotal numeric(14,2) NOT NULL CHECK (subtotal >= 0),
    tax numeric(14,2) NOT NULL CHECK (tax >= 0),
    total numeric(14,2) GENERATED ALWAYS AS (subtotal + tax) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE commerce.order_items (
    order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES commerce.orders(order_id) ON DELETE CASCADE,
    product_id bigint NOT NULL REFERENCES commerce.products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    line_total numeric(14,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    UNIQUE (order_id, product_id)
);

CREATE TABLE commerce.payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_ref text NOT NULL UNIQUE,
    order_id bigint NOT NULL UNIQUE REFERENCES commerce.orders(order_id),
    status text NOT NULL CHECK (status IN ('PENDING', 'AUTHORIZED', 'CAPTURED', 'FAILED', 'REFUNDED')),
    amount numeric(14,2) NOT NULL CHECK (amount >= 0),
    provider text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE commerce.shipments (
    shipment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shipment_ref text NOT NULL UNIQUE,
    order_id bigint NOT NULL UNIQUE REFERENCES commerce.orders(order_id),
    warehouse_id bigint NOT NULL REFERENCES commerce.warehouses(warehouse_id),
    status text NOT NULL CHECK (status IN ('QUEUED', 'PACKED', 'IN_TRANSIT', 'DELIVERED', 'RETURNED')),
    carrier text,
    tracking_code text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE commerce.inventory_movements (
    movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_id bigint NOT NULL,
    product_id bigint NOT NULL,
    order_id bigint REFERENCES commerce.orders(order_id),
    movement_type text NOT NULL CHECK (movement_type IN ('RECEIPT', 'RESERVATION', 'RELEASE', 'SHIPMENT', 'ADJUSTMENT')),
    quantity_delta integer NOT NULL CHECK (quantity_delta <> 0),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (warehouse_id, product_id) REFERENCES commerce.inventory(warehouse_id, product_id)
);

CREATE TABLE commerce.transaction_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_ref text NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('CUSTOMER_CREATED', 'ORDER_CREATED', 'PAYMENT_UPDATED', 'SHIPMENT_UPDATED', 'PRODUCT_UPDATED', 'CONTROLLED_DELETE', 'PROBE_WRITE')),
    entity_type text NOT NULL,
    entity_id bigint NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    committed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_region_created ON commerce.customers(region_code, created_at DESC);
CREATE INDEX idx_orders_customer_created ON commerce.orders(customer_id, created_at DESC);
CREATE INDEX idx_orders_status_created ON commerce.orders(status, created_at DESC);
CREATE INDEX idx_inventory_product ON commerce.inventory(product_id);
CREATE INDEX idx_inventory_low_stock ON commerce.inventory(quantity_on_hand) WHERE quantity_on_hand <= reorder_level;
CREATE INDEX idx_events_transaction_ref ON commerce.transaction_events(transaction_ref);
CREATE INDEX idx_events_committed_at ON commerce.transaction_events(committed_at DESC);
CREATE INDEX idx_products_name_hash ON commerce.products USING hash(name);

CREATE VIEW commerce.order_summary AS
SELECT o.order_id, o.order_ref, o.status, o.total, o.currency, o.created_at,
       c.external_ref AS customer_ref, count(oi.order_item_id) AS item_lines
FROM commerce.orders o
JOIN commerce.customers c USING (customer_id)
LEFT JOIN commerce.order_items oi USING (order_id)
GROUP BY o.order_id, c.external_ref;

CREATE MATERIALIZED VIEW commerce.product_sales_summary AS
SELECT p.product_id, p.sku, p.name,
       COALESCE(sum(oi.quantity), 0)::bigint AS units_ordered,
       COALESCE(sum(oi.line_total), 0)::numeric(16,2) AS gross_value
FROM commerce.products p
LEFT JOIN commerce.order_items oi USING (product_id)
GROUP BY p.product_id
WITH NO DATA;
CREATE UNIQUE INDEX idx_product_sales_summary_id ON commerce.product_sales_summary(product_id);

GRANT USAGE ON SCHEMA commerce TO cloudshift_migrator, parth_commerce_app, cloudshift_observer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA commerce TO parth_commerce_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA commerce TO parth_commerce_app;
GRANT SELECT ON ALL TABLES IN SCHEMA commerce TO cloudshift_migrator, cloudshift_observer;
ALTER DEFAULT PRIVILEGES IN SCHEMA commerce GRANT SELECT ON TABLES TO cloudshift_migrator, cloudshift_observer;
