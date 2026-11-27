#!/bin/sh
set -eu

project_name="cloudshift-parth"
confirmation="${1:-}"

if [ "$confirmation" != "$project_name" ]; then
    printf 'Refusing reset. Re-run with the exact project name:\n  %s %s\n' "$0" "$project_name" >&2
    exit 2
fi

printf '%s\n' 'Reset scope: CloudShift Compose project cloudshift-parth only.'
printf '%s\n' 'Reset includes only Compose project cloudshift-parth volumes, including optional restore, academic, and shard volumes.'
docker compose --project-name "$project_name" --profile core --profile observability --profile backup --profile academic --profile distributed down --volumes --remove-orphans
printf '%s\n' 'CloudShift project containers, network, and named data volumes were removed. Images and all other Docker projects were preserved.'
