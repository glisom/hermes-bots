---
name: mcp-surface-work
version: 1.0.0
description: "Use when adding agents to the MCP live surface."
tags: [mcp, agent-platform, golden-test, capability, governance]
category: agent-platform
---

# MCP Surface Work

Workflow for bringing a new agent's tools onto the live MCP surface: three-file change, golden test, and procedure gate tests.

## Files involved

| File | Purpose |
|---|---|
| `apps/web/src/app/api/mcp/registry/route.ts` | `REGISTRY_AGENTS` — flip `status: 'soon'` → `'live'` |
| `apps/web/src/lib/chat-agent/tools/mcp/mcp.golden.test.ts` | Pinned tool-surface golden contract per agent |
| `apps/web/src/lib/chat-agent/tools/mcp/mcp-governance.procedure.test.ts` | Pure (no-DB) capability gating invariants |

## Procedure

### 1. Map the agent's tool surface before writing any tests

Run these searches in parallel before writing a single line of test:

```bash
# All tools with the agent's capabilities (adjust cap names)
grep -r "capabilities: \['<cap>'" apps/web/src/lib/chat-agent/tools --include='*.ts' -l

# Per tool: effect, requiresApproval, excludeFromMcp
grep -n "requiresApproval\|  effect:\|excludeFromMcp" apps/web/src/lib/chat-agent/tools/<tool>.ts
```

For each tool record: capability, `effect`, `requiresApproval`, `excludeFromMcp`. This is the ground truth for the golden array.

### 2. Derive the staged tool count

With `allowStagedWrites: true` the surface is:
- All reads (any capability, no `excludeFromMcp`)
- All `requiresApproval: true` writes
- `list_pending_actions` + `approve_pending_action` (approval surface)

With staging off, approval-gated writes AND the approval surface are both absent.

### 3. Flip the registry and add the golden block

Registry change: one-liner in `REGISTRY_AGENTS`. In the golden test file, add ABOVE the first `describe` block:
1. `AGENT_MCP_TOOLS_WITH_STAGING` const (`.sort()` the array)
2. `agentGrant(allowStagedWrites)` helper with the agent's capabilities
3. `describe.runIf(DATABASE_URL)('GOLDEN: MCP surface for an entitled <Agent> team', ...)` with the three standard cases

### 4. Add procedure gate tests

In `mcp-governance.procedure.test.ts`, append after the last existing `describe` block:
1. `agentGrant` helper
2. `AGENT_APPROVAL_GATED_WRITES` array
3. Describe with the 5 standard tests

See `references/golden-test-patterns.md` for copy-paste templates.

### 5. Run procedure tests (pure, no DB)

```bash
cd apps/web && pnpm exec vitest run src/lib/chat-agent/tools/mcp/mcp-governance.procedure.test.ts
```

All existing tests + new ones must pass before opening the PR.

## Pitfalls

- **`callMcpTool` validates args BEFORE governance checks.** `invalid_args` fires when Zod rejects the args; `approval_required` / `staging_unavailable` are only reachable when args pass the schema. Always supply schema-valid args in governance tests. `send_nudge` requires `employeeId: z.string().uuid()` — use `'00000000-0000-0000-0000-000000000001'`, not a string like `'emp_test'`.

- **Apostrophes in `it(...)` single-quoted strings cause parse errors.** Use double-quoted strings for names containing possessives: `it("Elliot's tools...")`. Single-quoted strings with apostrophes tokenize as unterminated literals and produce cascading TS errors.

- **`preview_nudge` is `capabilities: ['social_posting']` but `effect: 'read'`.** Do not assume capability name implies write effect. Always check the `effect` field; `preview_nudge` belongs in the reads count, not the approval-gated writes.

- **Tools with `excludeFromMcp: true` are absent from `listMcpTools`** even if the capability matches. Check each tool file individually before including it in the golden array.

- **The approval surface appears ONLY when `allowStagedWrites: true`.** Assert its absence in the staging-off test case.

- **Run vitest from `apps/web/`**, not the repo root. `cd apps/web && pnpm exec vitest run <file>` always works; `pnpm --filter web vitest run` may find no vitest script.

## Elliot tool surface (pinned)

`employee_voice` reads (6): `get_content_queue`, `get_elliot_status`, `get_team_activity`, `get_team_roster`, `get_voice_profile`, `preview_nudge`

`social_posting` approval-gated writes (3): `draft_employee_post`, `schedule_employee_post`, `send_nudge`

Total with staging: **11** (6 + 3 + 2 approval surface).
