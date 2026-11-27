\set ON_ERROR_STOP on

-- Deterministic starter profile: 13,034 rows across the 13 business tables.
INSERT INTO commerce.product_categories (name, description)
SELECT 'Category ' || value, 'Synthetic product category ' || value
FROM generate_series(1, 10) AS value;

INSERT INTO commerce.warehouses (code, name, region_code)
VALUES ('WH-NR-01', 'North Region Warehouse', 'NR'),
       ('WH-WR-01', 'West Region Warehouse', 'WR'),
       ('WH-SR-01', 'South Region Warehouse', 'SR'),
       ('WH-ER-01', 'East Region Warehouse', 'ER');

INSERT INTO commerce.suppliers (code, name, contact_email)
SELECT 'SUP-' || lpad(value::text, 3, '0'),
       'Synthetic Supplier ' || value,
       'supplier' || value || '@example.invalid'
FROM generate_series(1, 20) AS value;

INSERT INTO commerce.products (sku, category_id, name, description, price)
SELECT 'SKU-' || lpad(value::text, 6, '0'),
       1 + ((value - 1) % 10),
       'Synthetic Product ' || value,
       'Deterministic demonstration product ' || value,
       round((100 + ((value * 7919) % 90000))::numeric / 100, 2)
FROM generate_series(1, 1000) AS value;

INSERT INTO commerce.customers (external_ref, email, full_name, region_code, created_at, updated_at)
SELECT 'CUS-' || lpad(value::text, 7, '0'),
       'customer' || value || '@example.invalid',
       'Synthetic Customer ' || value,
       (ARRAY['NR', 'WR', 'SR', 'ER'])[1 + ((value - 1) % 4)],
       timestamptz '2026-01-01 00:00:00+00' + value * interval '1 minute',
       timestamptz '2026-01-01 00:00:00+00' + value * interval '1 minute'
FROM generate_series(1, 3000) AS value;

INSERT INTO commerce.customer_addresses (customer_id, address_type, city, state, postal_code)
SELECT value, 'SHIPPING',
       (ARRAY['Chandigarh', 'Delhi', 'Mumbai', 'Bengaluru'])[1 + ((value - 1) % 4)],
       (ARRAY['CH', 'DL', 'MH', 'KA'])[1 + ((value - 1) % 4)],
       lpad((100000 + value)::text, 6, '0')
FROM generate_series(1, 2000) AS value;

INSERT INTO commerce.inventory (warehouse_id, product_id, supplier_id, quantity_on_hand, quantity_reserved, reorder_level)
SELECT 1 + ((product_id - 1) % 4), product_id, 1 + ((product_id - 1) % 20),
       50 + ((product_id * 37) % 450), 0, 20
FROM generate_series(1, 1000) AS product_id;

INSERT INTO commerce.orders (order_ref, customer_id, status, subtotal, tax, created_at, updated_at)
SELECT 'ORD-' || lpad(value::text, 8, '0'),
       1 + ((value * 13) % 3000),
       'PAID',
       round((250 + ((value * 6151) % 25000))::numeric / 10, 2),
       round((45 + ((value * 1107) % 4500))::numeric / 10, 2),
       timestamptz '2026-02-01 00:00:00+00' + value * interval '2 minutes',
       timestamptz '2026-02-01 00:00:00+00' + value * interval '2 minutes'
FROM generate_series(1, 1000) AS value;

INSERT INTO commerce.order_items (order_id, product_id, quantity, unit_price)
SELECT value, 1 + ((value * 17) % 1000), 1 + (value % 3),
       (SELECT price FROM commerce.products WHERE product_id = 1 + ((value * 17) % 1000))
FROM generate_series(1, 1000) AS value;

INSERT INTO commerce.payments (payment_ref, order_id, status, amount, provider, created_at, updated_at)
SELECT 'PAY-' || lpad(value::text, 8, '0'), value, 'CAPTURED', total, 'SYNTHETIC_GATEWAY', created_at, updated_at
FROM commerce.orders
CROSS JOIN LATERAL (SELECT order_id AS value) AS ref;

INSERT INTO commerce.shipments (shipment_ref, order_id, warehouse_id, status, carrier, tracking_code, created_at, updated_at)
SELECT 'SHP-' || lpad(order_id::text, 8, '0'), order_id, 1 + ((order_id - 1) % 4),
       'IN_TRANSIT', 'SYNTHETIC_CARRIER', 'TRK-' || lpad(order_id::text, 10, '0'), created_at, updated_at
FROM commerce.orders;

INSERT INTO commerce.inventory_movements (warehouse_id, product_id, order_id, movement_type, quantity_delta, occurred_at)
SELECT 1 + (((order_id * 17) % 1000) % 4), 1 + ((order_id * 17) % 1000), order_id,
       'RESERVATION', -1, created_at
FROM commerce.orders;

INSERT INTO commerce.transaction_events (transaction_ref, event_type, entity_type, entity_id, payload, committed_at)
SELECT 'seed-tx-' || lpad(order_id::text, 8, '0'), 'ORDER_CREATED', 'ORDER', order_id,
       jsonb_build_object('order_ref', order_ref, 'profile', 'starter'), created_at
FROM commerce.orders;

REFRESH MATERIALIZED VIEW commerce.product_sales_summary;
ANALYZE commerce.customers;
ANALYZE commerce.products;
ANALYZE commerce.orders;
ANALYZE commerce.transaction_events;

DO $$
DECLARE
    actual_count bigint;
BEGIN
    SELECT sum(row_count) INTO actual_count
    FROM (
        SELECT count(*) AS row_count FROM commerce.customers
        UNION ALL SELECT count(*) FROM commerce.customer_addresses
        UNION ALL SELECT count(*) FROM commerce.product_categories
        UNION ALL SELECT count(*) FROM commerce.products
        UNION ALL SELECT count(*) FROM commerce.warehouses
        UNION ALL SELECT count(*) FROM commerce.suppliers
        UNION ALL SELECT count(*) FROM commerce.inventory
        UNION ALL SELECT count(*) FROM commerce.orders
        UNION ALL SELECT count(*) FROM commerce.order_items
        UNION ALL SELECT count(*) FROM commerce.payments
        UNION ALL SELECT count(*) FROM commerce.shipments
        UNION ALL SELECT count(*) FROM commerce.inventory_movements
        UNION ALL SELECT count(*) FROM commerce.transaction_events
    ) counts;
    IF actual_count <> 13034 THEN
        RAISE EXCEPTION 'starter dataset expected 13034 rows, observed %', actual_count;
    END IF;
END $$;
