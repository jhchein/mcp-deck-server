# Branch Protection

Recommended protection settings for the `main` branch:

- Require a pull request before merging
- Require at least 1 approving review
- Dismiss stale approvals when new commits are pushed
- Require conversation resolution before merge (optional, but recommended)
- Require branches to be up to date before merging

Required status checks (must match GitHub Actions job names in `.github/workflows/ci.yml`):

- `lint`
- `test`
- `audit`

Checks that should **not** be required:

- `integration` (main/manual + secrets-gated)
- `benchmarks` (informational, non-blocking)
