# Security Policy

CloudShift DB is currently a local engineering project, not a production service.

- Report vulnerabilities privately to the repository owner after a publication channel exists.
- Never submit real database credentials, customer data, cloud keys, tokens, private keys, or Terraform state.
- The local API binds to loopback, accepts only predefined database endpoints, and does not expose arbitrary SQL or shell access.
- `.env` is ignored. `.env.example` contains disposable local-only values and must not be reused in shared environments.
- Public replay mode must remain read-only and must never receive Docker or cloud control access.

## Threat model and controls

- **Browser to local console:** the console never embeds the operator token. Mutation controls require a
  runtime token; the static replay has no mutation path.
- **Control plane to databases:** only three predefined endpoints are accepted. SQL identifiers come from
  fixed allowlists and values are parameterized. No arbitrary SQL, shell, Docker socket, cloud metadata,
  or external endpoint registration is exposed.
- **Commerce write routing:** writes take an advisory transaction lock, re-read the durable route and
  version, and reject during a fence or route change.
- **Container boundary:** ports bind to loopback, services use project-scoped names/networks/volumes,
  application containers run non-root, and optional components remain profile-gated.
- **Evidence boundary:** captures are sanitized and scanned before replay generation. Database archives
  exclude subscriptions because subscription connection strings can contain credentials.
- **Cloud preparation:** Terraform has no embedded credentials, RDS is private, S3 public access is
  blocked, EC2 requires IMDSv2, and no plan/apply is autonomous.

Residual risks include a shared local static operator token, no production identity/rate-limiting layer,
single-instance local databases, and unverified Kubernetes/AWS deployment behavior. These controls are
development safeguards, not a production security certification.
