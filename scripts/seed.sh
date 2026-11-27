#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"
$compose exec -T source-db psql -U cloudshift_admin -d parth_commerce_source -v ON_ERROR_STOP=1 -P pager=off -c "
SELECT table_name, (xpath('/row/count/text()', query_to_xml(format('SELECT count(*) AS count FROM commerce.%I', table_name), false, true, '')))[1]::text::bigint AS exact_rows
FROM information_schema.tables
WHERE table_schema = 'commerce' AND table_type = 'BASE TABLE'
ORDER BY table_name;"
