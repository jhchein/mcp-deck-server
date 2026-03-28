# Decision 017 — Agent Ergonomics Improvements

**Date:** 2026-03-28
**Status:** Accepted

## Context

This MCP server is consumed exclusively by LLM agents (via stdio in VS Code). The agent experience is the product UX. Today, 13 of 14 tools have no docstrings, no parameter descriptions, and return full 23-field Card objects. Agents routinely make avoidable mistakes: sending booleans for `done`, not knowing where to find `label_id`, making unnecessary round-trips, and burning context on irrelevant response fields.

FastMCP uses function docstrings as tool descriptions and `Annotated[type, Field(description=...)]` for parameter descriptions. Both are sent to the LLM in the tool schema. These are the primary levers.

## 1. Tool Descriptions

**Recommendation:** Add concise docstrings to all 14 tools. Each docstring answers: what it does, when to prefer it, key return content.

### Proposed docstrings

```
list_boards
    "List all boards the authenticated user can access.
    Returns board id, title, color, and labels. Use this to discover board IDs and available labels."

get_board
    "Get full details for a single board, including its labels and ACL.
    Use this to look up label IDs before calling assign_label_to_card."

list_stacks
    "List all stacks (columns) on a board. Returns stack id, title, and order.
    Prefer get_assigned_cards if you need cards for a specific user."

list_cards
    "List all cards in a specific stack. Returns cards with title, labels, assignees, and status.
    Requires both board_id and stack_id. Prefer get_assigned_cards to find a user's cards across boards."

get_assigned_cards
    "Find cards assigned to a user across boards. Filters by user, board, and done status.
    Returns cards with board/stack context. Defaults to the authenticated user's cards.
    Prefer this over list_stacks + manual filtering."

create_card
    "Create a new card in a stack. Returns the created card."

get_card
    "Get full details for a single card, including description, labels, and assignees."

update_card
    "Update card fields. Fetches current values first — only provided fields are changed.
    For text fields: None=keep current, ''=clear. For duedate/done: None=keep, ''=clear, or set an ISO-8601 datetime.
    Never send booleans for done — it must be a datetime string or empty."

move_card
    "Move a card to a different stack (column) on the same board.
    Stack name matching is case-insensitive. On mismatch, returns available stack names."

archive_card
    "Archive a card. Removes it from the active board view."

assign_label_to_card
    "Add a label to a card. Get available label IDs from get_board first."

remove_label_from_card
    "Remove a label from a card."

assign_user_to_card
    "Assign a user to a card by their Nextcloud user ID."

unassign_user_from_card
    "Remove a user assignment from a card."
```

### Rationale

- One to three sentences max — agents have limited context windows for tool schemas.
- Cross-references between tools reduce round-trips (e.g., "get_board returns labels").
- Warns against the #1 observed mistake (`done` is not a boolean).
- Steers toward efficient tools (`get_assigned_cards` over manual fan-out).
- No implementation details (removed the "no dedicated endpoint" note from `list_cards`).

### Trade-offs

- Docstrings are not versioned with the MCP schema — they can drift from implementation. Mitigated by keeping them adjacent to the function definition.
- Too-verbose descriptions waste context. Kept to ≤3 sentences.

## 2. Parameter Annotations

**Recommendation:** Add `Annotated[type, Field(description=...)]` to parameters where the type alone is ambiguous or where agents make observed errors.

### Parameters to annotate

| Tool                   | Parameter           | Annotation                                                                                          |
| ---------------------- | ------------------- | --------------------------------------------------------------------------------------------------- |
| `update_card`          | `done`              | `"ISO-8601 datetime string to mark done, '' to clear, None to keep current. Never send a boolean."` |
| `update_card`          | `duedate`           | `"ISO-8601 datetime string, '' to clear, None to keep current."`                                    |
| `update_card`          | `description`       | `"New description text, '' to clear, None to keep current."`                                        |
| `update_card`          | `title`             | `"New title. None to keep current."`                                                                |
| `update_card`          | `order`             | `"Sort position within the stack. None to keep current."`                                           |
| `get_assigned_cards`   | `user_id`           | `"Nextcloud user ID. Defaults to the authenticated user if omitted."`                               |
| `get_assigned_cards`   | `done`              | `"Filter: True=only done cards, False=only open cards, None=all."`                                  |
| `get_assigned_cards`   | `board_ids`         | `"Restrict search to these board IDs. Omit to search all accessible boards."`                       |
| `move_card`            | `target_stack_name` | `"Name of the destination stack. Case-insensitive."`                                                |
| `assign_label_to_card` | `label_id`          | `"Label ID from the board's labels list (see get_board)."`                                          |
| `assign_user_to_card`  | `user_id`           | `"Nextcloud user ID of the user to assign."`                                                        |
| `create_card`          | `description`       | `"Card description. Defaults to empty."`                                                            |

### Parameters NOT annotated (self-evident from name + type)

`board_id`, `stack_id`, `card_id`, `card_type`, `owner` — the name and type signature are sufficient. Over-annotating wastes schema tokens.

### Rationale

- Targets observed agent mistakes: `done` type confusion, `None` vs `""` semantics, not knowing where `label_id` comes from.
- `Annotated[str | None, Field(description=...)]` is the FastMCP-native mechanism; no framework workarounds.
- Descriptions are terse to avoid bloating the JSON schema the LLM receives.

### Trade-offs

- Every annotation adds ~10-20 tokens to the tool schema sent to the agent per invocation. 12 annotations ≈ 150-240 extra tokens — negligible.
- Annotations duplicate docstring information in some cases (`done` semantics). This is intentional — agents see parameter descriptions and tool descriptions in different parts of the schema, and the parameter-level hint is closer to the decision point.

## 3. Response Shape

**Recommendation: Option A — keep full models, no changes now.**

### Options considered

| Option                       | Description                                        | Pros                                                                      | Cons                                                                                                                                                                   |
| ---------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A. Full models (current)     | Return all fields as-is                            | Zero implementation cost. Agent picks what it needs. No model divergence. | 23 fields per card, ~15 are noise for typical agent tasks.                                                                                                             |
| B. Slim models               | New `CardSummary` / `BoardSummary` with 6-8 fields | Minimal context waste                                                     | Two parallel model hierarchies. Must track which API fields agents actually need — speculative. Breaks structured output schemas consumers may rely on.                |
| C. `model_dump(exclude=...)` | Return full model but exclude known-noise fields   | Middle ground — still one model set                                       | FastMCP serializes return type annotations, not the runtime dict. The schema still shows all fields. Confusing: schema says field X exists but it's absent at runtime. |

### Rationale for Option A

1. **Premature optimization.** Agent context waste from verbose responses is real but low-severity. A 10-card listing with 23 fields/card ≈ 600 tokens. This is noise but not the bottleneck — tool descriptions and parameter schemas dominate.
2. **`extra="allow"` risk.** Our models absorb undocumented Deck API fields. Slim models would silently drop them; full models preserve them. If a future Deck version adds a useful field, full models surface it automatically.
3. **Schema fidelity.** FastMCP generates JSON schema from return type annotations. If we `exclude=` at runtime, the schema and reality diverge — agents may reference fields that aren't returned. Worse than verbose.
4. **Revisit trigger.** If response size becomes a measurable issue (e.g., boards with 100+ cards), introduce pagination or summary models then. Not now.

### Open question

If slim responses become needed, the cleanest path is a new `CardSummary` model as the return type for listing tools, with `get_card` still returning full `Card`. This preserves schema honesty. Deferred.

## 4. Workflow Hints

**Recommendation: Docstring cross-references only. No dedicated help tool or prompt resource.**

### Options considered

| Option                 | Description                                             | Pros                                        | Cons                                                                                                                                |
| ---------------------- | ------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| A. Docstring hints     | Cross-tool references in docstrings (proposed in §1)    | Zero overhead. Hints shown at point of use. | Limited space; can't teach multi-step workflows.                                                                                    |
| B. `deck_help` tool    | Dedicated tool returning a workflow guide               | Agent can self-serve. Comprehensive.        | Agents must discover and choose to call it. Extra tool in the schema (14→15). If agents call it every turn, it wastes a round-trip. |
| C. MCP prompt resource | Static prompt template exposed via MCP prompt primitive | System-prompt injection — always present.   | Not all MCP clients support prompts. Cargo-culting a feature for one server. Stale if workflows change.                             |

### Rationale for Option A

- The observed mistakes (§Context) are all solvable with 1-sentence cross-references:
  - "Get label IDs from `get_board`" → fixes mistake #1.
  - "`done` is ISO-8601, not boolean" → fixes mistake #2.
  - "`None`=keep, `''`=clear" → fixes mistake #3.
  - "`list_boards` already returns labels" → fixes mistake #4.
  - "Prefer `get_assigned_cards`" → fixes mistake #5.
- A `deck_help` tool adds complexity for an uncertain benefit. If docstrings prove insufficient after deployment, a help tool can be added later with zero breaking changes.
- MCP prompt resources are not reliably consumed by all clients (Claude Desktop, VS Code Copilot, Continue — varying support).

### Trade-off

Docstring hints cannot teach long workflows like "to triage a board: list_boards → get_board → get_assigned_cards → update_card for each." If this proves needed, a `deck_help` tool is the escape hatch. The incremental cost of adding it later is near-zero.

## 5. SSE Transport Removal

**Recommendation: Remove SSE support.**

### Current state

- `config.py`: `MCP_TRANSPORT` env var, validated as `"stdio" | "sse"`.
- `config.py`: `DeckConfig.transport` field typed `Literal["stdio", "sse"]`.
- `main.py`: `mcp.run(transport=config.transport)`.
- Decision 004 introduced this for "hosting scenarios beyond local MCP clients."

### Rationale for removal

1. **SSE is not used.** The server runs exclusively via stdio in VS Code. No hosting scenario has materialized.
2. **FastMCP's SSE story is deprecated.** The MCP spec moved to Streamable HTTP. FastMCP's SSE transport is a compatibility shim, not a forward path.
3. **Dead code costs.** The transport config adds a validation branch, a test path, and a Literal type union for zero users. It's speculative generality.
4. **Reversibility.** Re-adding transport selection is a 5-line change if ever needed.

### Changes

- Remove `MCP_TRANSPORT` from `config.py` and environment variable documentation.
- Remove `transport` field from `DeckConfig`.
- Hardcode `mcp.run(transport="stdio")` in `main.py`.
- Update `python.instructions.md` to remove `MCP_TRANSPORT` from the config section.
- Supersedes decision 004.

### Trade-off

If a remote transport need arises, it must be re-implemented. The cost is ~5 minutes of work and one decision document. Acceptable given zero current users.

## Consequences

1. **All 14 tools get docstrings** — agents see purpose, alternatives, and return shape context.
2. **12 parameter annotations added** — targets observed mistakes at the point of decision.
3. **Response shapes unchanged** — full models preserved; revisit if verbosity becomes measurable bottleneck.
4. **No new tools** — workflow guidance lives in docstrings, not a help tool.
5. **SSE transport removed** — simplifies config and eliminates dead code. Supersedes decision 004.
6. **`python.instructions.md` updated (local only)** — MCP Tools section expanded to reflect docstring and annotation conventions. `MCP_TRANSPORT` removed from Config section. Note: this file is in `.github/instructions/` which is gitignored; the conventions are also captured in `project-spec/interfaces.md`.
7. **Test impact** — `test_config.py` tests for SSE transport validation must be removed/updated. No other test changes (docstrings and annotations don't affect behavior).
