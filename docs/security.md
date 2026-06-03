# Security review

This review covers the local stdio MCP server that proxies Nextcloud Deck API calls for an agent. We reviewed credential handling, request construction, local transport assumptions, dependency audit status, and error exposure against the implementation and project decisions.

## Summary

We found no blocking security issue for the current local-only deployment. The main operating rule is simple: treat the configured Nextcloud app password as an account credential, not as a Deck-only token. The code now validates the configured base URL and keeps low-level connection details out of MCP-visible errors.

| Area | Risk | Assessment | Recommendation |
| --- | --- | --- | --- |
| Credential handling | Low | `NC_APP_PASSWORD` is loaded from environment or `.env`, excluded from dataclass `repr`, and not logged by project code. `.env` is ignored by git. | Keep `.env` out of source control. Rotate app passwords after suspected exposure. |
| Nextcloud app password scope | Medium | Nextcloud documents device-specific passwords as client credentials that can be revoked individually. They are not Deck-only tokens. | Use a dedicated low-privilege Nextcloud user for the MCP server when possible. |
| Input validation | Low | Tool path parameters are typed as `int` in the MCP schema. Text fields are sent in JSON payloads, not interpolated into URLs. | Keep numeric IDs typed as integers. Add tests if new string path parameters are introduced. |
| Base URL validation | Low | `NC_URL` is validated as an absolute HTTP(S) URL with a host, and query or fragment components are rejected. | Keep this validation in place for any future config-loading changes. |
| SSRF | Low | Tool parameters only control path segments under the configured Deck API base URL. Clients cannot choose arbitrary hosts through tool calls. | Keep the remote host config-only. Do not add tools that accept full URLs without a separate review. |
| Transport boundary | Low | `main.py` hardcodes stdio transport. There is no network listener in the server. | Treat the local MCP host and any connected agent as trusted process-level callers. |
| Error information exposure | Low | `DeckHTTPError` exposes status and body. `DeckConnectionError` now returns a generic connection-failure message instead of low-level request details. | Keep low-level connection details out of MCP-visible exceptions. |
| Dependency audit | Low | `uv.lock` is committed, CI runs `uv audit`, and the current audit reports no known vulnerabilities. | Keep the audit job required on protected branches. |

## Evidence

Credentials are loaded in `mcp_deck_server/config.py` through `load_dotenv()` and environment variables. The `DeckConfig` dataclass marks `nc_app_password` with `repr=False`, which reduces accidental printing of secrets during debugging.

Requests are constructed in `mcp_deck_server/client.py` by appending fixed Deck API paths to the configured `NC_URL`. Tool functions in `mcp_deck_server/server.py` interpolate integer IDs into path segments and send mutable card fields as JSON request bodies.

The transport boundary is narrow. `main.py` runs `mcp.run(transport="stdio")`, and project decisions record stdio as the supported transport. This keeps the server off the network, but any local process that can invoke the MCP server can act with the configured Nextcloud credentials.

Nextcloud's user documentation describes device-specific passwords under connected devices. The generated password is used to configure a client, and the user can disconnect each device individually. The documentation does not describe app passwords as Deck-scoped credentials, so we should treat `NC_APP_PASSWORD` as a credential with the authenticated user's normal account permissions.

## Dedicated user guidance

For day-to-day use, the safest setup is a dedicated Nextcloud user for this MCP server. Give that user access only to the Deck boards the agent should manage, then generate a device-specific password for the MCP client. If the token leaks or the agent behaves badly, the blast radius is the dedicated user's board access rather than the owner's full account.

This is operational guidance rather than a code requirement. The server cannot make a Nextcloud app password Deck-scoped on its own. Access has to be limited in Nextcloud by choosing the account and board shares carefully.

## Remediation items

We do not need to block current use on these items. They should be handled as normal follow-up work because they reduce sharp edges without changing the operating model.

| Priority | Item | Owner | Expected outcome |
| --- | --- | --- | --- |
| Done | Validate `NC_URL` at config load. | Maintainer | Invalid or surprising base URLs fail before the server starts. |
| Done | Redact `DeckConnectionError` messages. | Maintainer | MCP clients receive actionable connection failures without full low-level request details. |
| Done | Document dedicated-user setup guidance. | Maintainer | Users understand that the app password should belong to a least-privilege Nextcloud account where possible. |

## Current position

We consider the current deployment acceptable for a trusted local MCP environment. The server does not expose a network port, does not log secrets in project code, validates its configured base URL, redacts connection failures, and has a clean dependency audit. The remaining security work is routine maintenance.
