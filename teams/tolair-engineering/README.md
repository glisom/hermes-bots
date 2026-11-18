# Tolair Engineering Team — Tinker

Tinker is the Slack-facing coordinator; the four profile IDs are a routing contract:

| Profile | Role |
| --- | --- |
| `tolair-em` | Tinker: plan, route, monitor, read QA verdicts |
| `tolair-backend` | NestJS, Prisma, ingestion, metrics, lineage, tenant isolation |
| `tolair-frontend` | Next.js, Tailwind, cockpit UX, accessibility, pack vocabulary |
| `tolair-qa` | Independent acceptance and regression verification |

```bash
./bin/install-team tolair-engineering
# Later:
./bin/update-team tolair-engineering
```

These profiles are verified against the installed Hermes source build `6b21d0564de0`, which reports `0.19.0+56123.g6b21d05` and includes distribution install, Kanban review dispatch, and per-profile dispatch allowlists. The manifest minimum permits that build; it does not establish compatibility with every earlier 0.19 build. Verify those capabilities before activating on a different runtime. Existing generic and Limelight requirements remain unchanged.

Configure models/providers locally, bind a `tolair` board to a stable local Tolair checkout, and use exactly one dispatcher. When adopting the existing default Slack gateway, merge the manager's Kanban configuration into its local config, copy the manager charter, and disable gateway dispatch/notifications on the installed `tolair-em` profile. Do not run two gateways with the same Slack credentials. Keep provider auth, Slack tokens, paths, board state, and runtime settings out of this repository. Worker profiles never dispatch.

Only dispatch tasks authorized by the user or their completion contract. No scheduled work is installed. Link execution cards to canonical Linear issues. Read current repository instructions rather than treating the charters as a frozen architecture specification.

## Slack branding

App and bot display name: **Tinker**. Short description: “Tolair’s engineering sidekick. Plans, builds, checks, and connects the dots.” Preserve existing `/hermes` commands and app permissions. Use `assets/tinker-icon.png` for the app icon. Apply branding through the existing app's Basic Information and App Home settings; do not create a second app or replace its manifest/scopes just to change branding.

The icon was created with the built-in ImageGen tool. Prompt: square Slack icon for Tinker, Tolair's friendly engineering teammate; teal robot, warm ivory expressive face, orange spark antenna, deep navy background, bold geometric illustration, readable at 32 pixels, generous rounded-crop padding, no text or watermark.
