# AWS reference mapping

```text
On-premises PostgreSQL source
        │ private VPN / Direct Connect (planned)
        ▼
cloudshift-parth VPC
  public subnet: TLS application/control entry point
        │ security-group reference, TCP 5432 only
        ▼
  private DB subnets (two AZs): encrypted RDS PostgreSQL target
        │
        ├── encrypted, versioned private S3 logical backups
        └── CloudWatch operational telemetry
```

The diagram is an architecture artifact, not a deployed environment. The local logical replication,
validation, workload, probe, and cutover evidence does not establish RDS migration behavior until a
separately authorized cloud experiment is executed.
