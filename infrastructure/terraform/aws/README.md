# Optional AWS reference architecture

This configuration prepares, but does not deploy, a `cloudshift-parth` VPC with a narrowly exposed
ARM64 application host, private two-AZ RDS subnet group, encrypted PostgreSQL RDS target, encrypted and
versioned private S3 backup bucket, least-purpose instance role, and CloudWatch log group. PostgreSQL is
not publicly accessible. It maps the local source to an on-premises PostgreSQL source and the local
target to private RDS; actual private connectivity (VPN/Direct Connect), DMS alternatives, DNS/TLS,
container registry, and production identity remain deployment decisions.

The database uses encrypted gp3 storage, private security-group-only ingress, PostgreSQL log export,
automated backups, final snapshots, tag copying, and deletion protection. Multi-AZ is deliberately an
explicit cost-bearing variable and defaults to `false`; a production readiness review should normally
enable it. The S3 evidence bucket blocks all public access, denies non-TLS requests, versions objects,
aborts incomplete uploads, and expires noncurrent versions after 90 days. The application host has no
console ingress unless an explicit non-public-anywhere operator CIDR is supplied.

Validation only:

```sh
cd infrastructure/terraform/aws
terraform init -backend=false
terraform fmt -check
terraform validate
```

No `terraform plan` or `apply` is run autonomously because provider configuration can contact AWS and
the resources incur cost. Review current pricing for EC2, RDS, storage, backups, data transfer, and logs.
Before any authorized deployment, supply a 16+ character password through a secure environment/secret
store, restrict `allowed_console_cidrs`, replace the single EC2 host with the intended HA platform, enable
Multi-AZ when the availability requirement justifies its cost, and decide whether deletion protection,
retention, lifecycle rules, and final snapshots satisfy the organization's recovery policy.

Cleanup, only after explicit approval: remove deletion protection through reviewed configuration,
retain or export required backups, run a reviewed `terraform plan -destroy`, and then `terraform destroy`.
