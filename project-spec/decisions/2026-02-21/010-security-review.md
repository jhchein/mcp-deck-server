# Decision: Security review

**Date:** 2026-02-21
**Status:** Accepted

## Context

The server handles Nextcloud credentials and proxies API calls on behalf of an AI agent. A security review is needed to identify and mitigate risks in the local stdio deployment.

## Decision

### Review scope

Conduct a security review covering these areas:

| Area                             | What to assess                                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Credential handling**          | How are `NC_URL`, `NC_USER`, `NC_APP_PASSWORD` loaded, stored in memory, and used? Can they leak via errors, logs, or MCP responses?              |
| **Input validation**             | Are tool parameters validated before being interpolated into API URLs? (e.g., path traversal via `board_id`, injection via `title`/`description`) |
| **Transport security**           | stdio is local-only. What process-level trust assumptions and exposure risks remain?                                                              |
| **Dependency audit**             | Are `httpx`, `mcp-server`, `pydantic`, `python-dotenv` pinned? Any known CVEs?                                                                    |
| **Error information leakage**    | Do error messages expose internal URLs, credentials, or stack traces to MCP clients?                                                              |
| **Nextcloud app password scope** | What permissions does an app password grant? Is it scoped to Deck only, or full account access?                                                   |
| **SSRF risk**                    | Can a malicious MCP client craft tool parameters that cause the server to hit arbitrary URLs?                                                     |

### Deliverables

1. **`docs/security.md`** — findings, risk ratings (low/medium/high), and recommendations.
2. **Code changes** — filed as items in `todos.md` for any issues requiring remediation.
3. **Dependency pinning** — ensure `uv.lock` is committed, and add `uv audit` or equivalent to CI.

### Key known risks to investigate

- `NC_URL` is user-provided and used in URL construction — validate it's a proper base URL at config time.
- `board_id`, `stack_id`, `card_id` are interpolated into f-strings for URLs — verify they're integers (type-checked by function signatures, but confirm Pydantic/FastMCP validates before calling).
- stdio transport is local-only but still proxies credentials — validate process-level trust boundary.

## Consequences

- Security findings become actionable todos.
- Blocking issues (if any) get added as P0s.
- Decision 004 (configurable transport) has been superseded by decision 017. No remote transport exists to gate.
- Produces a durable security doc that can be updated as the project evolves.
