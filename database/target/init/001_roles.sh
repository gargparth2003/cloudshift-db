#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=migration_password="$MIGRATION_DB_PASSWORD" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=observer_password="$OBSERVER_DB_PASSWORD" <<'SQL'
CREATE ROLE cloudshift_migrator LOGIN PASSWORD :'migration_password';
CREATE ROLE parth_commerce_app LOGIN PASSWORD :'app_password';
CREATE ROLE cloudshift_observer LOGIN PASSWORD :'observer_password';
GRANT CONNECT ON DATABASE parth_commerce_target TO cloudshift_migrator, parth_commerce_app, cloudshift_observer;
SQL
