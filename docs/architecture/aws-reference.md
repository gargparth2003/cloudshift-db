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

The validated reference keeps RDS private and encrypted, exports PostgreSQL logs, retains automated backups,
requires a final snapshot, copies tags to snapshots, and enables deletion protection. Multi-AZ is an explicit
cost-bearing input and defaults off in this configuration-only baseline. The private S3 evidence bucket blocks
public access, denies non-TLS requests, versions objects, and has bounded incomplete/noncurrent object cleanup.
Application ingress is empty by default and rejects `0.0.0.0/0` and `::/0`.

See the [deployment-readiness runbook](../runbooks/cloud-deployment-readiness.md) before any separately
authorized plan or apply.
