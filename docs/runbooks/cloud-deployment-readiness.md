# Cloud deployment readiness runbook

Status: **configuration only — no cloud resources created**.

## Approval gate

Before any plan or apply, obtain explicit authorization for the provider account, region, expected monthly
cost, resource owner, data classification, change window, rollback authority, and cleanup deadline. Confirm
budget alerts separately in the provider account. CloudShift DB never provisions automatically.

## Source readiness

1. Inventory the PostgreSQL version, extensions, primary keys, replica identity, large objects, tablespaces,
   sequences, roles, and unsupported objects.
2. Measure database size, write rate, WAL generation, retention headroom, and available transfer bandwidth.
3. Enable logical replication only through the managed provider's documented parameter mechanism. AWS RDS
   uses `rds.logical_replication`; Azure Flexible Server requires logical WAL settings and worker capacity;
   Cloud SQL uses `cloudsql.logical_decoding`. Parameter changes can require a restart.
4. Create a least-purpose replication identity and verify its permissions without exposing the database to
   the public internet.
5. Rehearse schema creation and DDL freeze/evolution policy. Native logical replication does not replicate
   schema changes automatically.

## Network and security gate

1. Validate non-overlapping VPC/VNet CIDRs and two database subnets in distinct availability zones.
2. Use private connectivity (VPN, interconnect, or an approved equivalent). RDS remains private and accepts
   PostgreSQL only from the application/migration-worker security group.
3. Require TLS in transit, encrypted storage, private backup storage, IMDSv2, least-privilege IAM, centralized
   audit logs, and an approved secret manager. Never commit credentials or Terraform state.
4. Replace the single reference application instance with the approved highly available runtime and ingress
   design. The reference's empty console CIDR list is intentional.

## Reliability and recovery gate

1. Select Multi-AZ and backup retention from explicit RTO/RPO requirements and current cost, not defaults.
2. Test restore into a disposable isolated destination and validate table counts, content checksums, roles,
   extensions, and absence of unintended subscriptions.
3. Define WAL/slot alert thresholds, lag escalation, write-fence timeout, cutover abort criteria, fail-forward
   policy, and replication-slot retirement.
4. Rehearse target failure, worker restart, network partition, backup restore, and operator rollback before a
   production migration. Preserve evidence for each trial.

## Configuration review

```sh
terraform -chdir=infrastructure/terraform/aws init -backend=false -input=false
terraform -chdir=infrastructure/terraform/aws fmt -check
terraform -chdir=infrastructure/terraform/aws validate
kubectl kustomize infrastructure/kubernetes/base >/tmp/cloudshift-kubernetes.yaml
```

These commands are non-deploying structural checks. A separately authorized `terraform plan` must be reviewed
for every resource, replacement, public route, secret path, and recurring charge. Never use `apply` as a
validation command.

## Official references

- [AWS Regions and Availability Zones](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-regions.html)
- [RDS PostgreSQL logical replication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.FeatureSupport.LogicalReplication.html)
- [RDS in a VPC](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html)
- [RDS backup retention](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.BackupRetention.html)
- [AWS security-group referencing](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)
- [AWS RDS PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Azure PostgreSQL logical replication](https://learn.microsoft.com/azure/postgresql/configure-maintain/concepts-logical)
- [Azure availability-zone region support](https://learn.microsoft.com/azure/reliability/availability-zones-region-support)
- [Cloud SQL logical replication](https://docs.cloud.google.com/sql/docs/postgres/replication/configure-logical-replication)
- [Google Cloud regions and zones](https://docs.cloud.google.com/compute/docs/regions-zones)
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing)
