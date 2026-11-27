#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"
set -a
. ./.env
set +a

source_price=$($compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -Atc "SELECT price FROM commerce.products WHERE product_id = 1;")

restore_target() {
  $compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -v ON_ERROR_STOP=1 \
    -c "UPDATE commerce.products SET price = $source_price WHERE product_id = 1;" >/dev/null
}
trap restore_target EXIT INT TERM

$compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -v ON_ERROR_STOP=1 \
  -c "UPDATE commerce.products SET price = price + 5.00 WHERE product_id = 1;" >/dev/null

mismatch_result=$(curl --fail --silent --show-error -X POST \
  -H "x-cloudshift-token: $CONTROL_API_TOKEN" \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/validate?scope=FULL")

printf '%s' "$mismatch_result" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result["status"] == "MISMATCHED", result
assert result["mismatch_count"] >= 1, result
products = next(table for table in result["tables"] if table["table_name"] == "products")
assert products["mismatched_rows"] == 1, products
'

final_status=$(curl --silent --output /dev/null --write-out '%{http_code}' -X POST \
  -H "x-cloudshift-token: $CONTROL_API_TOKEN" \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/validate?scope=FINAL_QUIESCED")
test "$final_status" = "409"

restore_target
trap - EXIT INT TERM

restored_result=$(curl --fail --silent --show-error -X POST \
  -H "x-cloudshift-token: $CONTROL_API_TOKEN" \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/validate?scope=FULL")
printf '%s' "$restored_result" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result["status"] == "MATCHED", result
assert result["mismatch_count"] == 0, result
'

printf 'validation mismatch verified: detected=1 final_without_fence_blocked=1 restored=1\n'
