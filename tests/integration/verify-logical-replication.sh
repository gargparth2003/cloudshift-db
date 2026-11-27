#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"
run_id=$(date -u +%Y%m%d%H%M%S)

source_sql() {
  $compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -v ON_ERROR_STOP=1 -Atc "$1"
}

target_sql() {
  $compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -v ON_ERROR_STOP=1 -Atc "$1"
}

wait_target_value() {
  sql=$1
  expected=$2
  attempts=0
  while [ "$attempts" -lt 30 ]; do
    observed=$(target_sql "$sql")
    if [ "$observed" = "$expected" ]; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  printf 'target observation timeout: expected=%s observed=%s\n' "$expected" "$observed" >&2
  return 1
}

ready_tables=$(target_sql "SELECT count(*) FROM pg_subscription_rel WHERE srsubstate = 'r';")
test "$ready_tables" = "13"

source_total=$(source_sql "SELECT count(*) FROM commerce.customers;")
wait_target_value "SELECT count(*) FROM commerce.customers;" "$source_total"

insert_ref="CUS-LIVE-$run_id"
source_sql "
WITH inserted AS (
  INSERT INTO commerce.customers (external_ref, email, full_name, region_code)
  VALUES ('$insert_ref', 'live-$run_id@example.invalid', 'Live Replication Customer', 'NR')
  RETURNING customer_id, external_ref
)
INSERT INTO commerce.transaction_events (transaction_ref, event_type, entity_type, entity_id, payload)
SELECT 'tx-insert-$run_id', 'CUSTOMER_CREATED', 'CUSTOMER', customer_id,
       jsonb_build_object('external_ref', external_ref)
FROM inserted;" >/dev/null
wait_target_value "SELECT count(*) FROM commerce.customers WHERE external_ref = '$insert_ref';" "1"
wait_target_value "SELECT count(*) FROM commerce.transaction_events WHERE transaction_ref = 'tx-insert-$run_id';" "1"

source_sql "
BEGIN;
UPDATE commerce.products SET price = price + 1.00, updated_at = now() WHERE product_id = 1;
INSERT INTO commerce.transaction_events (transaction_ref, event_type, entity_type, entity_id, payload)
VALUES ('tx-update-$run_id', 'PRODUCT_UPDATED', 'PRODUCT', 1, jsonb_build_object('delta', 1.00));
COMMIT;" >/dev/null
source_price=$(source_sql "SELECT price FROM commerce.products WHERE product_id = 1;")
wait_target_value "SELECT price FROM commerce.products WHERE product_id = 1;" "$source_price"
wait_target_value "SELECT count(*) FROM commerce.transaction_events WHERE transaction_ref = 'tx-update-$run_id';" "1"

delete_ref="CUS-DELETE-$run_id"
source_sql "INSERT INTO commerce.customers (external_ref, email, full_name, region_code) VALUES ('$delete_ref', 'delete-$run_id@example.invalid', 'Delete Replication Customer', 'WR');" >/dev/null
wait_target_value "SELECT count(*) FROM commerce.customers WHERE external_ref = '$delete_ref';" "1"
source_sql "DELETE FROM commerce.customers WHERE external_ref = '$delete_ref';" >/dev/null
wait_target_value "SELECT count(*) FROM commerce.customers WHERE external_ref = '$delete_ref';" "0"

rollback_ref="CUS-ROLLBACK-$run_id"
source_sql "BEGIN; INSERT INTO commerce.customers (external_ref, email, full_name, region_code) VALUES ('$rollback_ref', 'rollback-$run_id@example.invalid', 'Rolled Back Customer', 'SR'); ROLLBACK;" >/dev/null
test "$(source_sql "SELECT count(*) FROM commerce.customers WHERE external_ref = '$rollback_ref';")" = "0"
sleep 1
test "$(target_sql "SELECT count(*) FROM commerce.customers WHERE external_ref = '$rollback_ref';")" = "0"

multi_a="CUS-MULTI-A-$run_id"
multi_b="CUS-MULTI-B-$run_id"
source_sql "
BEGIN;
INSERT INTO commerce.customers (external_ref, email, full_name, region_code)
VALUES ('$multi_a', 'multi-a-$run_id@example.invalid', 'Multi Row Customer A', 'ER'),
       ('$multi_b', 'multi-b-$run_id@example.invalid', 'Multi Row Customer B', 'ER');
INSERT INTO commerce.transaction_events (transaction_ref, event_type, entity_type, entity_id, payload)
SELECT 'tx-multi-$run_id', 'CUSTOMER_CREATED', 'CUSTOMER', customer_id,
       jsonb_build_object('external_ref', external_ref)
FROM commerce.customers WHERE external_ref IN ('$multi_a', '$multi_b');
COMMIT;" >/dev/null
wait_target_value "SELECT count(*) FROM commerce.customers WHERE external_ref IN ('$multi_a', '$multi_b');" "2"
wait_target_value "SELECT count(*) FROM commerce.transaction_events WHERE transaction_ref = 'tx-multi-$run_id';" "2"

wal_lag=$(source_sql "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint FROM pg_replication_slots WHERE slot_name = 'parth_cloudshift_slot';")
test -n "$wal_lag"

printf 'logical replication verified: run_id=%s insert=1 update=1 delete=1 rollback_excluded=1 multi_row=2 wal_byte_lag=%s\n' "$run_id" "$wal_lag"
