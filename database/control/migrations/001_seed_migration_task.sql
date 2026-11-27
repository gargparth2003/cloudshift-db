\set ON_ERROR_STOP on

INSERT INTO control.migration_tasks (
    task_key, workspace_id, source_endpoint_id, target_endpoint_id
)
SELECT 'parth-commerce-migration-001', w.workspace_id, source.endpoint_id, target.endpoint_id
FROM control.workspaces w
JOIN control.database_endpoints source ON source.endpoint_key = 'source'
JOIN control.database_endpoints target ON target.endpoint_key = 'target'
WHERE w.name = 'Parth Garg — Cloud Engineering Lab'
ON CONFLICT (task_key) DO NOTHING;

INSERT INTO control.migration_events (migration_id, event_type, component, message)
SELECT migration_id, 'MIGRATION_CREATED', 'cloudshift-control-plane',
       'Migration task created in DRAFT state.'
FROM control.migration_tasks task
WHERE task.task_key = 'parth-commerce-migration-001'
  AND NOT EXISTS (
      SELECT 1 FROM control.migration_events event
      WHERE event.migration_id = task.migration_id AND event.event_type = 'MIGRATION_CREATED'
  );
