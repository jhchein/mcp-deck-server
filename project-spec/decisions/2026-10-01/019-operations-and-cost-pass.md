# Decision 019 — Resilience, Token Cost and Operations Pass

**Date:** 2026-10-01
**Status:** Accepted
**Delivery:** Four stacked PRs — (1) resilience and security, (2) token cost, (3) CI and operations, (4) code structure.

## Context

A second review after decision 018 found the code sound but the operating model thin. The server is a personal tool: one user, one Nextcloud instance, an agent that is trusted. That shapes what is worth doing.

1. **Failure behaviour is bounded per request, not per tool call.** Each HTTP request has a timeout and GETs retry, but a search over many boards has no overall limit. With 30 s timeouts, three attempts and boards fetched five at a time, a degraded server can hold one tool call for minutes. Retries use fixed delays, so the five concurrent requests of one search retry in lockstep. A wrong password surfaces only at the first tool call as a bare `HTTP error 401`, and a connection failure does not say whether it was a timeout or a TLS problem.
2. **Tool schemas cost tokens.** FastMCP derives an `outputSchema` for every tool from its return type. Measured on the 14 tools: about 56 KB of output schemas against about 8.5 KB of input schemas and descriptions. Clients that forward output schemas to the model pay roughly 14k tokens per session for information the model does not need, and every response additionally carries its payload twice (text content and `structuredContent`).
3. **Operations are manual.** The CI audit job blocks every PR the moment a new advisory is published, which is how PRs #22–#24 were blocked by unrelated Dependabot findings. Actions are referenced by tag, workflows have no `permissions` block, and CI installs without `--locked`. The live integration tests never run in CI because no secrets are configured, so a stale test (fixed in #27) went unnoticed. The package has no entry point, so it cannot be started with `uvx`. There is no structured log of what a tool call did.
4. **Security posture was framed too broadly.** Decision 018 treats prompt injection from card text as the main risk. That holds for boards that other people can write to. For boards only the owner writes to, the risk is close to zero, and making the default restrictive would make the tool less useful for its actual use.

## Decision

### Phase 1 — Resilience and security

- **Overall tool deadline.** Every tool runs under `asyncio.timeout(MCP_TOOL_TIMEOUT)` (default 120 s). Expiry raises `DeckTimeoutError` naming the tool and the setting. The check distinguishes the deadline from a `TimeoutError` raised inside the call.
- **Separate connect timeout.** Connecting is capped at 10 s (or `MCP_REQUEST_TIMEOUT` if smaller). A dead host fails fast instead of consuming the full request timeout.
- **Jittered backoff and `Retry-After` dates.** Backoff waits 50–100 % of `0.5 · 2^attempt`. `Retry-After` is honoured as seconds or HTTP date, capped at 5 s.
- **Actionable errors.** HTTP 401 adds `check NC_USER and NC_APP_PASSWORD`. `DeckConnectionError` names the exception class (`ConnectTimeout`, `ConnectError`) but never its text, which can embed URLs.
- **`main.py --check`.** Validates the configuration, lists disabled tools, calls `/boards` once and reports latency. Exit code 0 or 1. The password is never printed.
- **`MCP_ENABLED_TOOLS` allowlist.** Comma-separated tool names. Unset means every tool. Unknown names fail at startup. Tools outside the list are removed from the tool list and refused if called. `MCP_READ_ONLY` wins over the list.
- **Defaults stay permissive.** All tools are on by default. The threat model in `docs/security.md` states when the opt-in controls matter: boards that others can write to. It also states that only a dedicated Nextcloud user with read-only board shares enforces limits on the Nextcloud side.

### Phase 2 — Token cost

- Tools register with `structured_output=False`. Clients keep receiving the JSON text content, but no `outputSchema` or duplicated `structuredContent`. Return annotations stay for type checking.
- `get_assigned_cards` accepts `limit` (default 200) and reports `total_matches` and `truncated`, so a flood of cards cannot fill the agent context unnoticed.

### Phase 3 — CI and operations

- Actions are pinned to commit SHAs; workflows declare `permissions: contents: read`; CI installs with `uv sync --locked`; PR runs are cancelled when superseded.
- CI runs for pull requests against any branch, so stacked PRs get checks.
- **Audit gate.** The `audit` job remains a required check. On a pull request that does not change `pyproject.toml` or `uv.lock`, advisories are reported as a warning and do not fail the job. On pushes to `main`, on the weekly schedule and on PRs that touch dependencies, they fail it. Unrelated PRs are no longer held up by new advisories, and nothing ships with a known advisory.
- A weekly scheduled run also executes the live integration tests when the repository has the secrets configured.
- Dependabot groups updates (one PR per ecosystem and week) and covers GitHub Actions.
- The package gets a build system and a `mcp-deck-server` entry point, so `uvx --from git+<repo> mcp-deck-server` works.
- Each tool call logs one structured line on stderr (tool, outcome, duration), and each retried GET logs a warning with method, path, reason and wait. httpx already logs one line per request. Never content or credentials.
- An automated stdio protocol test starts the server as a subprocess and checks the advertised tools for default, read-only and allowlist configurations.
- `SECURITY.md` describes private reporting.

### Phase 4 — Code structure

- `DeckRuntime.request()` replaces the repeated `make_nc_request(runtime.client, runtime.config, …)` call, and one helper replaces the four copies of the `success`/`raw` result handling.
- `update_card`: the owner handling moves into a small tested helper. Behaviour is unchanged.
- `server.py` stays one module. A split would put the runtime and tool registration in a module that every tool module imports, and the unit tests patch `server.get_runtime`, so every test module would have to change for a purely structural gain. Revisit when the file keeps growing.

## Rejected alternatives

- **Read-only or restricted tool set as the default.** Safer on paper, but it would make the default setup unusable for the primary scenario, an agent managing the owner's own boards. Opt-in controls plus an honest threat model cover the shared-board case.
- **Marking card text as untrusted in tool output.** Wrapping or prefixing every title and description adds tokens to every response and does not stop a model that decides to follow the text. Revisit if clients gain a standard way to tag untrusted content.
- **Response caching (the review's first suggestion).** Decisions 011 and 018 already rejected it: Deck sends `no-store` and stacks expose no ETag, so a cache could serve stale cards to an agent.
- **Circuit breaker.** One user and one server. The overall deadline and bounded retries give the same protection with less state.
- **Per-tool timeouts.** One deadline is easier to reason about; the slow tool is `get_assigned_cards`, and it is the one that benefits.
- **Making `audit` non-required.** That would let a vulnerable lock file reach `main` unnoticed. The path-aware gate keeps the check meaningful.
- **Validating `card_type` and `owner` in `update_card`.** Deck documents `plain` as the only card type "for now" and does not document the owner payload (decisions 013 and 016). A strict schema would guess and could reject values Deck accepts.
- **Choosing a licence.** That is the repository owner's decision and is not made here.

## Consequences

- Worst-case latency of a tool call is now bounded by `MCP_TOOL_TIMEOUT`. A slow but working server can hit the deadline; raise it if that happens.
- Clients that read `structuredContent` instead of the text content lose it after Phase 2. VS Code and the other clients in use read the text content.
- `get_assigned_cards` gains fields and a default cap of 200 cards; callers that need more pass a larger `limit`.
- A weekly advisory run can fail on `main` without a code change. That is intended: it is the signal to relock.
- `docs/security.md` records the threat model, so the allowlist is documented as a policy of this server and not as an access control of Nextcloud.
