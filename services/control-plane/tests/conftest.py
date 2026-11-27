import os


TEST_ENVIRONMENT = {
    "SOURCE_DATABASE_URL": "postgresql://unused",
    "TARGET_DATABASE_URL": "postgresql://unused",
    "CONTROL_DATABASE_URL": "postgresql://unused",
    "CONTROL_API_TOKEN": "test-operator-token",
    "MIGRATION_DB_PASSWORD": "test-migration-password",
    "APP_SOURCE_DATABASE_URL": "postgresql://unused",
    "APP_TARGET_DATABASE_URL": "postgresql://unused",
}

for key, value in TEST_ENVIRONMENT.items():
    os.environ.setdefault(key, value)
