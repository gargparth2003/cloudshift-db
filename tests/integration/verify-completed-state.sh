#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"
set -a
. ./.env
set +a

topology=$(curl --fail --silent --show-error \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/topology")
printf '%s' "$topology" | python3 -c '
import json, sys
result = json.load(sys.stdin)
assert result["state"] == "COMPLETED", result["state"]
assert result["route"]["active_endpoint"] == "TARGET", result["route"]
assert result["route"]["writes_enabled"] is True, result["route"]
assert result["replication"]["ready_tables"] == 13, result["replication"]
'

cutovers=$(curl --fail --silent --show-error \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/cutovers?limit=1")
printf '%s' "$cutovers" | python3 -c '
import json, sys
result = json.load(sys.stdin)[0]
assert result["outcome"] == "COMPLETED", result
assert len(result["stages"]) == 11, result["stages"]
assert all(stage["status"] == "COMPLETED" for stage in result["stages"]), result["stages"]
'

validations=$(curl --fail --silent --show-error \
  "http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/migrations/parth-commerce-migration-001/validations?limit=20")
printf '%s' "$validations" | python3 -c '
import json, sys
result = json.load(sys.stdin)
final = next(item for item in result if item["scope"] == "FINAL_QUIESCED")
assert final["status"] == "MATCHED", final
assert final["mismatches"] == 0, final
'

subscription_enabled=$($compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -Atc \
  "SELECT subenabled FROM pg_subscription WHERE subname='parth_cloudshift_subscription';")
test "$subscription_enabled" = "f"

if $compose exec -T -e PGPASSWORD="$APP_DB_PASSWORD" source-db \
  psql -U parth_commerce_app -d parth_commerce_source -v ON_ERROR_STOP=1 \
  -c "UPDATE commerce.products SET updated_at=updated_at WHERE product_id=1;" >/dev/null 2>&1; then
  printf '%s\n' 'source application-role write unexpectedly succeeded after cutover' >&2
  exit 1
fi

target_only=$($compose exec -T target-db psql -U cloudshift_admin -d parth_commerce_target -Atc \
  "SELECT count(*) FROM commerce.orders WHERE order_ref='ORD-LIVE-F89F046F7A2A4EE4';")
source_absent=$($compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -Atc \
  "SELECT count(*) FROM commerce.orders WHERE order_ref='ORD-LIVE-F89F046F7A2A4EE4';")
test "$target_only" = "1"
test "$source_absent" = "0"

printf '%s\n' 'completed state verified: route=TARGET stages=11 final_validation=MATCHED subscription=disabled source_app_write=denied target_only_order=present'
