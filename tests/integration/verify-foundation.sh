#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"

source_total=$($compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -Atc "
SELECT sum(row_count) FROM (
  SELECT count(*) row_count FROM commerce.customers
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
) counts;")

target_total=$($compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -Atc "
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'commerce' AND table_type = 'BASE TABLE';")

control_total=$($compose exec -T control-db psql -U cloudshift_admin -d cloudshift_control -Atc "
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'control' AND table_type = 'BASE TABLE';")

wal_level=$($compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -Atc "SHOW wal_level;")

test "$source_total" -ge "13034"
test "$target_total" = "13"
test "$control_total" -ge "26"
test "$wal_level" = "logical"

curl --fail --silent --show-error http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/health >/dev/null
curl --fail --silent --show-error http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/endpoints/source/schema >/dev/null

printf 'foundation verified: source_rows=%s (baseline>=13034) target_tables=%s control_tables=%s wal_level=%s\n' \
  "$source_total" "$target_total" "$control_total" "$wal_level"
