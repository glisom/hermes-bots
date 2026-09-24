# Golden Test Patterns

Copy-paste templates for the two test files that guard the MCP surface.
Substitute `<Agent>`, `<AGENT>`, `capabilities`, and the tool lists.

## mcp.golden.test.ts — new agent block

Add the const + grant helper ABOVE the first `describe` block, then append the describe at the END of the file.

```ts
/**
 * The exact MCP tool surface an entitled <Agent> team sees with staged writes on:
 * <Agent>'s N reads + the M approval-gated writes + the 2 approval-surface tools.
 */
const <AGENT>_MCP_TOOLS_WITH_STAGING = [
  // <cap1> reads
  'tool_a',
  'tool_b',
  // <cap2> approval-gated writes
  'write_tool_c',
  // ENG-2920 — the MCP approval surface
  'list_pending_actions',
  'approve_pending_action',
].sort();

const <agent>Grant = (allowStagedWrites: boolean): McpCapabilityGrant => ({
  teamId: TEAM_ID,
  userId: USER_ID,
  capabilities: ['cap1', 'cap2'],
  allowStagedWrites,
});

// --- append at END of file ---

describe.runIf(DATABASE_URL)('GOLDEN: MCP surface for an entitled <Agent> team', () => {
  it("tools/list returns EXACTLY <Agent>'s N tools when staged writes are enabled", () => {
    const names = listMcpTools(<agent>Grant(true))
      .map((t) => t.name)
      .sort();
    expect(names).toEqual(<AGENT>_MCP_TOOLS_WITH_STAGING);
  });

  it('the approval surface is ABSENT when staged writes are off', () => {
    const names = listMcpTools(<agent>Grant(false)).map((t) => t.name);
    expect(names).not.toContain('approve_pending_action');
    expect(names).not.toContain('list_pending_actions');
  });

  it('an approval-gated write is STAGED (one pending action, source:mcp), never executed', async () => {
    const grant = <agent>Grant(true);
    const res = await callMcpTool(
      '<approval_gated_tool>',
      { /* valid schema args — must pass Zod before governance checks run */ },
      grant,
      { stagePendingAction: createMcpStager(grant) },
    );
    expect(res).toMatchObject({ ok: true, status: 'pending' });
    const pendingActionId = res.ok && res.status === 'pending' ? res.pendingActionId : '';
    expect(pendingActionId).toBeTruthy();

    const rows = await db
      .select({ id: chatPendingActions.id, actionType: chatPendingActions.actionType, sessionId: chatPendingActions.sessionId })
      .from(chatPendingActions)
      .where(eq(chatPendingActions.id, pendingActionId));
    expect(rows).toHaveLength(1);
    expect(rows[0]!.actionType).toBe('<approval_gated_tool>');

    const sessions = await db
      .select({ metadata: chatSessions.metadata })
      .from(chatSessions)
      .where(inArray(chatSessions.id, [rows[0]!.sessionId]));
    expect(sessions).toHaveLength(1);
    expect((sessions[0]!.metadata as { source?: string }).source).toBe('mcp');
  });
});
```

## mcp-governance.procedure.test.ts — new agent block

Append at the END of the file. No `beforeAll`/`afterAll` needed (pure, no DB).

```ts
/** An <Agent>-shaped grant (<cap1> + <cap2>). */
const <agent>Grant = (allowStagedWrites: boolean): McpCapabilityGrant => ({
  teamId: 't_proc',
  userId: 'u_proc',
  capabilities: ['cap1', 'cap2'],
  allowStagedWrites,
});

const <AGENT>_APPROVAL_GATED_WRITES = ['write_tool_c', 'write_tool_d'];

describe('PROCEDURE: <Agent> MCP capability gating — <cap1> + <cap2>', () => {
  it('approval-gated writes are ABSENT from tools/list when staged writes are off', () => {
    const names = listMcpTools(<agent>Grant(false)).map((t) => t.name);
    for (const w of <AGENT>_APPROVAL_GATED_WRITES) {
      expect(names, `${w} must be excluded when allowStagedWrites=false`).not.toContain(w);
    }
  });

  it('approval-gated writes APPEAR only when staged writes are opted in', () => {
    const names = listMcpTools(<agent>Grant(true)).map((t) => t.name);
    for (const w of <AGENT>_APPROVAL_GATED_WRITES) {
      expect(names, `${w} must be listed when allowStagedWrites=true`).toContain(w);
    }
  });

  it('<cap1> reads are always present regardless of staged-writes flag', () => {
    const reads = ['tool_a', 'tool_b', 'tool_c_read'];
    for (const staged of [true, false]) {
      const names = listMcpTools(<agent>Grant(staged)).map((t) => t.name);
      for (const r of reads) {
        expect(names, `${r} must be listed regardless of allowStagedWrites=${staged}`).toContain(r);
      }
    }
  });

  it('an approval-gated write is refused with approval_required when staging is off', async () => {
    // Args MUST be schema-valid (Zod validates before governance checks).
    const res = await callMcpTool('<write_tool>', { /* valid args */ }, <agent>Grant(false));
    expect(res).toMatchObject({ ok: false, reason: 'approval_required' });
  });

  it('an approval-gated write is refused with staging_unavailable when opted in but no stager wired', async () => {
    const res = await callMcpTool('<write_tool>', { /* valid args */ }, <agent>Grant(true));
    expect(res).toMatchObject({ ok: false, reason: 'staging_unavailable' });
  });

  it('an unentitled grant sees no <Agent> tools', () => {
    const names = listMcpTools({
      teamId: 't_proc', userId: 'u_proc',
      capabilities: ['some_other_cap'],
      allowStagedWrites: true,
    }).map((t) => t.name);
    const agentTools = [...<AGENT>_APPROVAL_GATED_WRITES, 'tool_a', 'tool_b'];
    for (const t of agentTools) {
      expect(names, `${t} must not appear under a non-<Agent> grant`).not.toContain(t);
    }
  });
});
```

## Key arg requirements for schema-valid governance test calls

| Tool | Required valid arg |
|---|---|
| `send_nudge` | `{ employeeId: '00000000-0000-0000-0000-000000000001' }` (must be UUID) |
| `send_outreach` | `{ creatorId: 'c1', draftId: 'd1' }` |
| `update_negotiation` | `{ dealId: 'deal_x', action: 'counter', amount: 500 }` |
| `add_creator_to_campaign` | `{ creatorId: 'c1' }` |

Always check the tool's `inputSchema` before writing the args — `invalid_args` will shadow the governance error.
