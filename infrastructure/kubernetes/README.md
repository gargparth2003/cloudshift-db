# Kubernetes deployment preparation

These manifests describe a private `cloudshift-parth` namespace with three PostgreSQL StatefulSets,
internal services, application deployments, health probes, PVCs, resource bounds, secret references,
and default-deny networking. They are manifest-validation artifacts, not evidence of a running cluster.

Before deployment, build reviewed database bootstrap ConfigMaps or pinned internal PostgreSQL images
from `database/*/init`, create `cloudshift-database-secrets` and `cloudshift-application-secrets` through
the target secret manager, and replace the un-published GHCR image references with authorized digests.
Do not commit Secret objects or plaintext credentials.

Validate locally:

```sh
kubectl kustomize infrastructure/kubernetes/base > /tmp/cloudshift-kubernetes.yaml
kubectl apply --dry-run=client --validate=false -f /tmp/cloudshift-kubernetes.yaml
```

No `kubectl apply` against a cluster is part of the autonomous local workflow.
