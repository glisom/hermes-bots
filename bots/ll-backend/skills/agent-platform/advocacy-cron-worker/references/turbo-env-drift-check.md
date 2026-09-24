# turbo.json globalEnv Drift Check Pattern

Guards LINKEDIN_*/ADVOCACY_*/ELLIOT_LINKEDIN_* vars — any key in env.ts but absent from globalEnv silently breaks Turborepo cache keying.

## Files

| File | Purpose |
|---|---|
| `scripts/check-turbo-env-vars.mjs` | `extractEnvKeys(envTsPath, pattern)`, `loadTurboGlobalEnv(turboPath)`, `check()` |
| `scripts/check-turbo-env-vars.test.mjs` | 5 tests incl. live acceptance against real files |
| `package.json` | `check:turbo-env-vars:test` script + added to `validate:pr` |
| `turbo.json` | `"//#check:turbo-env-vars:test": { "cache": false }` task |

## Script shape

```js
// Extract keys matching a regex pattern from env.ts Zod schema
export function extractEnvKeys(envTsPath, pattern) {
  const re = new RegExp(`^  (${pattern}):`, 'gm');
  // returns Set<string>
}

// Load globalEnv from turbo.json
export function loadTurboGlobalEnv(turboPath) {
  // returns Set<string>
}

// Returns array of missing vars (empty = passing)
export function check(turboPath?, envTsPath?) { ... }
```

The text-scan approach (line regex) works because the env.ts schema is a flat `z.object({ KEY: z. })` with one key per line. Structural changes require developer intent anyway.

## Adding new var groups

To extend the check to a new namespace (e.g. `PLEXUS_*`):
1. Update `CHECKED_PATTERN` in `check-turbo-env-vars.mjs` to include the new regex arm.
2. Add the vars to `turbo.json` `globalEnv`.
3. The acceptance test (`check: passes for the REAL turbo.json + env.ts`) will fail until both are done.

## Pitfalls

- The check only fires for vars that appear as `KEY:` at the top level of the Zod object (two-space indent). Nested objects or multiline keys would evade the regex — acceptable for this codebase's flat schema convention.
- When adding to `validate:pr`, insert the new task **after** `check:vercel-config:test` to keep the order consistent with declaration order in `turbo.json`.
