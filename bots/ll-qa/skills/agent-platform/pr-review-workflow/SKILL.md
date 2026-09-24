---
name: pr-review-workflow
version: 1.1.0
description: "Use when reviewing agent-platform PRs as ll-qa."
when_to_use: "Use for same-card review of work handed off by ll-backend or ll-frontend."
---

# PR Review Workflow (ll-qa)

End-to-end procedure for reviewing agent-platform PRs as ll-qa. The goal is a numbered, reproducible finding list with file:line citations and a clear PASS or REQUEST CHANGES verdict.

## Step 0 — Orient

Gather context in parallel before touching anything:

```bash
gh pr view <N> --json title,body,state,headRefName,baseRefName,files
gh pr checks <N>
git log --oneline origin/main..<branch>
```

Read the PR body fully — it lists what changed, the test approach, and any declared pre-existing failures.

## Step 1 — Check out the branch

```bash
git checkout <branch>
git log --oneline origin/main..<branch>   # confirm on PR head
```

If `main` is checked out as a worktree (common in this repo), `git checkout main` fails with "already used by worktree". Use the worktree path directly for baseline comparisons.

## Step 2 — Run validate:pr

```bash
pnpm validate:pr 2>&1 | tail -20
```

Turbo short-circuits at the first failing task — all subsequent tasks are cancelled. The reported error is only the first. When `check:codex-skills` fails, run individual scripts to find the real failure set:

```bash
pnpm run check:codex-skills 2>&1 | tail -10
pnpm run check:em-dash 2>&1 | tail -5
pnpm run check:tokens 2>&1 | tail -5
pnpm --filter @agent-platform/db run check 2>&1 | tail -5
```

### Distinguishing local noise from PR-introduced failures

Before counting a validate:pr failure against a PR, confirm it doesn't exist on main:

```bash
git diff origin/main -- .agents/skills/          # should be empty if PR didn't touch it
git ls-tree origin/main .agents/skills/ | wc -l  # count on main
ls .agents/skills/ | wc -l                       # count in worktree
```

If `check:codex-skills` reports a count mismatch and `git diff origin/main -- .agents/skills/` is empty, the extra skills are untracked local files not introduced by the PR. Do not count these against the PR. Confirm by running the check in a main worktree.

CI is authoritative over local runs. A check that fails locally but passes on CI is local noise. A check that passes locally but fails on CI requires investigation.

## Step 3 — Read CI failure logs

When `gh pr checks` shows a failing job:

```bash
gh run view <run-id> --log-failed 2>&1 | head -100
# Extract meaningful lines:
gh run view <run-id> --log-failed 2>&1 | grep -E "(error TS|FAIL|AssertionError|expected)" | head -30
```

The run ID is the numeric portion of the URL in `gh pr checks` output.

### Common CI failure patterns

**TS2741 — EnvShape fixture not updated after schema change:**
When a PR adds a field to the Zod env schema (`env.ts`), it joins `EnvShape`. Any `VALID_PROD_BASE` or similar fixture in `env.test.ts` that omits the field breaks type-check:
```
src/lib/env.test.ts(14,7): error TS2741: Property 'NEW_VAR' is missing
```
Fix: add `NEW_VAR: ''` (or appropriate default) to every fixture object in `env.test.ts`.

**Procedure test origin_env mismatch:**
When row-creation helpers like `createDraft` are called without an explicit `originEnv`, they call `resolveDeploymentEnv()` which returns `'test'` in vitest (NODE_ENV=test). If the test then queries with a hardcoded `'production'`, the SQL predicate finds zero rows. Symptom: `expected [] to have a length of 1 but got +0`.

Fix: pass `originEnv` explicitly when creating test rows — use the same value you plan to query under. Never rely on the `resolveDeploymentEnv()` default in procedure tests that scope by origin env.

## Step 4 — Run targeted tests

When `pnpm run test:unit` or the `--filter` variant times out, run vitest directly:

```bash
cd apps/web
pnpm exec vitest run --reporter=verbose <path/to/specific.test.ts>
```

For procedure tests requiring Postgres:

```bash
lsof -i :9001 -sTCP:LISTEN -P | head -1   # check DB is up; if empty: docker compose up -d
DATABASE_URL=postgres://postgres:postgres@localhost:9001/agent_platform \
  pnpm exec vitest run --reporter=verbose <procedure.test.ts>
```

Procedure tests use `describe.runIf(DATABASE_URL)` and silently skip without a live DB. A passing-but-skipped suite is not a valid gate. Confirm CI's golden+procedure gate actually executed the tests (check logs for no `numPending` > 0).

## Step 5 — Read the diff for scope creep

```bash
gh pr view <N> --json files
git diff origin/main..<branch> --name-only
```

Flag any files changed outside the PR's stated scope.

## Step 6 — Issue the Kanban verdict

- **PASS:** only when `validate:pr` is green or every failure is proven baseline noise, required CI gates pass, and every acceptance check was exercised. Call `kanban_complete` with exact commands, manual checks, CI state, and residual risk.
- **REQUEST CHANGES:** first call `kanban_comment` with one numbered finding per issue: reproduction, expected, actual, severity, and file/line when known. Then call `kanban_request_changes(reason)`.
- **BLOCKED:** call `kanban_block(reason, kind)` only for a missing fixture, unavailable dependency, external outage, or human decision.

Do not edit the candidate during review. Tests or fixtures may be changed only on a separate QA implementation card. `message_agent` may coordinate, but it never replaces the terminal Kanban transition. Never merge or deploy. End every run with exactly one terminal Kanban action.

## Pitfalls

- Do not count `check:codex-skills` local failures as PR-introduced without checking `git diff origin/main -- .agents/skills/` and running the check in a main worktree. Untracked stripe-* skill dirs in `.agents/skills/` are a known local noise source in this repo.
- Never accept a procedure suite as valid without confirming CI executed it (not silently skipped via `describe.runIf`).
- `pnpm run test:unit` times out on large test trees — use `pnpm exec vitest run <specific-file>` instead.
- `resolveDeploymentEnv()` returns `'test'` in vitest. Advocacy row-creation helpers that call it without an explicit `originEnv` stamp rows as `'test'`, causing mismatches when queried as `'production'`. Always pass `originEnv` explicitly in procedure test fixtures.
- Turbo's error cascade means the first failing task cancels all others. Run individual check scripts to find the full failure set.
- When `main` is checked out as a worktree, `git checkout main` fails — use the worktree path at `.claude/worktrees/<name>` directly.
- `gh run view --log-failed` outputs ANSI escape codes — pipe through `grep` for readability.
