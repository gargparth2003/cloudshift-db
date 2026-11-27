#!/bin/sh
set -eu

compose="docker compose --project-name cloudshift-parth --profile core"
$compose ps

curl --fail --silent --show-error http://127.0.0.1:${CLOUDSHIFT_API_PORT:-18000}/api/v1/health
printf '\n'
