---
name: em-project-orchestration
description: "Use when decomposing Limelight agent-platform work into Kanban cards."
version: 1.1.0
author: ll-em
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, planning, orchestration, decomposition]
    category: devops
    requires_toolsets: [kanban]
environments:
  - kanban
---

# Limelight Engineering Orchestration

Plan and route agent-platform projects without implementing them.

## Procedure

1. Call `kanban_show` for the current orchestration card and inspect active cards before creating anything. Surface stale or duplicate work; do not archive it without explicit approval.
2. Read the repository instructions, architecture notes, Linear context, and current team roster.
3. Write the parent specification: outcome, scope, non-goals, risks, and observable acceptance checks.
4. Split work into cards one specialist can complete in one run and one coherent repository area. Name likely files only after verifying them. Put shared API or schema decisions into every affected card.
5. Link real dependencies. Assign server/data work to `ll-backend`, user-facing work to `ll-frontend`, and every implementation review to `ll-qa`.
6. Leave cards in `todo` until Grant approves dispatch. Ask before dispatching more than three cards or touching `main`, migrations, secrets, Vercel/CI configuration, production systems, releases, or external sends.
7. After approval, preview dispatch, dispatch the ready cards, and verify their states. The dispatcher leaves unresolved assignees ready with a diagnostic event; fix the assignment rather than assuming the card disappeared.
8. Read the `ll-qa` verdict before calling work shipped. Correctable findings return to the original implementer. Report one concise parent summary with PRs, verification, residual risk, and blockers.

## Rules

- Never implement product code.
- Never let two cards independently decide the same interface.
- Never merge, deploy, change credentials, or send an external message.
- `message_agent` is coordination, not dispatch.
- End the orchestration card with `kanban_complete` or `kanban_block` and include created cards, assignments, dependencies, and dispatch state.
