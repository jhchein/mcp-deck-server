# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the **Security** tab of this repository and choose **Report a vulnerability**. Do not open a public issue for a security problem.

Include the affected version or commit, the steps to reproduce, and the impact you expect. This is a personal project, so there is no service-level agreement. Reports are answered on a best-effort basis.

## What is in scope

The server runs locally over stdio and acts with the Nextcloud credentials of the person who configured it. Relevant reports concern, for example, credential exposure in logs or errors, ways for tool input to reach a different host or path than the configured Deck API, and bypasses of `MCP_READ_ONLY` or `MCP_ENABLED_TOOLS`.

[docs/security.md](docs/security.md) describes the threat model and the controls.
