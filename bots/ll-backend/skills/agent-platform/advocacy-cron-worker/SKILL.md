---
name: advocacy-cron-worker
version: 1.0.0
description: "Use when building advocacy cron workers or transitions."
tags: [advocacy, cron, post-service, audit, agent-platform]
category: agent-platform
---

# Advocacy Cron / Worker Development

Workflow for adding a new cron worker or post-service transition in the Elliot Advocacy vertical.

## File map

| File | Purpose |
|---|---|
| `packages/db/src/schema/advocacy.ts` | `ADVOCACY_POST_EVENT_KINDS` array + `AdvocacyPostStatus` |
| `apps/web/src/lib/advocacy/post-service.ts` | Guarded transitions + `PostTransitionName` union |
| `apps/web/src/lib/advocacy/post-audit.ts` | `KIND_BY_TRANSITION` map + audited wrappers |
| `apps/web/src/queries/advocacy.ts` | `ADVOCACY_EVENT_KIND_LABEL` — exhaustive human-readable map |
| `apps/web/src/lib/advocacy/<worker>.ts` | New worker logic with injectable deps |
| `apps/web/src/app/api/cron/advocacy/<name>/route.ts` | Cron entrypoint |
| `apps/web/vercel.json` | Cron schedule entry |

## Procedure

### 1. Add a new transition (if needed)

All three files are exhaustiveness-checked and must change together:

1. **`post-service.ts` → `PostTransitionName`**: add the new string literal to the union.
2. **`packages/db/src/schema/advocacy.ts` → `ADVOCACY_POST_EVENT_KINDS`**: add the new kind. No migration needed — the column is free text with no CHECK constraint, by design.
3. **`post-audit.ts` → `KIND_BY_TRANSITION`**: add the transition → kind mapping. `Record<PostTransitionName, AdvocacyPostEventKind>`; a missing arm is a compile error.
4. **`apps/web/src/queries/advocacy.ts` → `ADVOCACY_EVENT_KIND_LABEL`**: add the human-readable label. Also exhaustive; missing it is caught only by `tsc` (not eslint), so it surfaces at the pre-push hook, not commit.

Then add the audited wrapper to `post-audit.ts`: import the new transition and export `auditedXxx` following the SYSTEM_ACTOR or human actor pattern.

### 2. Write the worker

Follow the `publish-worker.ts` pattern:
- Injectable deps interface (all fields optional; production calls with `{}`).
- Export individual query functions (`listXxx`) for procedure test isolation.
- Export the main entry (`runXxx(deps = {})`).
- Per-row error isolation: one row throwing must never stall the batch. Wrap in try/catch, collect into `errors[]`.
- Origin-scope in the SQL predicate (not post-fetch). Foreign rows fetched inside the limit starve the eligible batch.
- Best-effort observability passes (foreign rows, refused counts) each get their own try/catch so a diagnostic query cannot take down the work path.

### 3. Write the cron route

Follow `apps/web/src/app/api/cron/advocacy/publish/route.ts`:
- 404 (not 401) on a missing or bad bearer — `timingSafeEqual` on `CRON_SECRET`.
- Use `process.env.CRON_SECRET` directly (NOT the validated `env` proxy) so tests load the module without a full env seed.
- Dispatch to the worker entry function.
- Surface notable outcomes and per-row errors to Sentry as `captureMessage` warnings — the tick always returns 200.
- Return `Response.json(result)`.

### 4. Register the cron

- Add to `apps/web/vercel.json` `crons` array.
- The staging Cloud Scheduler reads `vercel.json` via `scripts/staging/render-cron-scheduler.mjs` — no separate staging entry needed.

### 5. Write tests

**Route unit test** (`route.test.ts`): mock the worker module and `@sentry/nextjs`. Cover: 404 on missing bearer, 404 on wrong token, 404 when CRON_SECRET is unset, clean tick returns summary, Sentry warned on notable outcomes, Sentry warned on per-row errors.

**Procedure test** (`<worker>.procedure.test.ts`): `describe.runIf(DATABASE_URL)`. Namespaced team/user/key constants. `beforeEach` + `afterEach` wipe. Filter list-queries to your team. Cover: SQL predicate for eligible rows, SQL predicate for excluded rows, a successful recovery, concurrent-worker no-op (inject the row id directly when a prior status move drops it from the list-query).

## References

- `references/turbo-env-drift-check.md` — the pattern for writing a Node.js CI check that detects missing `turbo.json globalEnv` entries for a namespace (LINKEDIN_*/ADVOCACY_*).

## Pitfalls

- **`ADVOCACY_EVENT_KIND_LABEL` in `queries/advocacy.ts` must be updated whenever a new event kind is added.** It is exhaustive over `AdvocacyPostEventKind`. NOT checked by eslint — only `tsc` catches a missing key. The failure surfaces at the pre-push type-check hook. Add the label entry before pushing.

- **`PostTransitionName` union and `KIND_BY_TRANSITION` map are both exhaustive.** Add a new transition to BOTH in the same commit. An intermediate state where one has the new arm and the other doesn't fails the pre-push type-check.

- **The cron route reads `process.env.CRON_SECRET` directly, never through the validated `env` proxy.** The proxy throws when the full schema is not seeded; the route must load in tests without a full env. This is intentional and consistent across all cron routes.

- **Origin-scope in the SQL WHERE clause, never post-fetch.** Fetching excluded rows inside the per-tick limit starves the eligible batch — foreign rows never advance their retry counters and stay stuck indefinitely.

- **Guarded `tryTransition` UPDATE is the concurrency primitive.** Two concurrent callers for the same row: one wins, the other gets `INVALID_STATE` back, never a double-execution. No additional locking needed.

- **For procedure tests covering the concurrent-worker path:** if a prior UPDATE removes the row from the list-query predicate, the real list-query won't return it. Inject the row id directly into worker deps (e.g., `listStuck: async () => [{ id, teamId }]`) to drive the guarded UPDATE against an already-moved row.

- **A pre-existing gate failure is not permission to bypass hooks.** Reproduce the failure on `main`, record the evidence in the card and PR, and ask for explicit human approval before bypassing any repository gate.

- **Procedure tests that create rows without `originEnv` get `'test'` in vitest (NODE_ENV=test → `resolveDeploymentEnv()` returns `'test'`).** Any query hardcoded to `'production'` will find zero rows. Fix: pass `originEnv: 'production'` explicitly in `makeXxxPost()` calls for tests that query under a specific env. The cross-deployment isolation test (which posts `staging` and queries `production`) is the correct model — always be explicit on both sides.

- **Adding a new field with `z.string().default('')` to the env.ts Zod schema also requires updating `VALID_PROD_BASE` in `apps/web/src/lib/env.test.ts`.** That fixture is typed as `EnvShape` (exhaustive); `tsc` fails with a TS2741 missing-property error. Add `FIELD_NAME: ''` immediately after the neighboring field in the existing Plexus/LinkedIn block to preserve alphabetical/grouping order. Only caught at the pre-push type-check hook, not at commit.

- **The `patch` tool's `old_string` must contain real newline characters, not `\n` literals.** When patching a multi-line TypeScript union type (e.g., adding a member to `PostTransitionName`), the `old_string` field must use actual newlines in the JSON, not the escape sequence `\n`. Providing `\n` makes the tool insert a literal backslash-n into the file and the match fails on the second attempt. Write the `old_string` across multiple lines in the tool call.
