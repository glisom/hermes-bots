# Hermes Bots

Reusable Hermes profile distributions and machine bootstrap scripts.

This repository stores bot definitions, not live Hermes state. Each machine keeps its own credentials, memories, sessions, databases, logs, caches, model selection, project paths, and activation state.

## Bots

### Operations

| Bot | Purpose | Platforms |
| --- | --- | --- |
| [`mac-ops`](bots/mac-ops/) | Monitor a Mac, recover allowlisted services, and investigate incidents | macOS |

### Limelight engineering team

| Bot | Purpose |
| --- | --- |
| [`ll-em`](bots/ll-em/) | Plan, decompose, route, and monitor agent-platform work |
| [`ll-backend`](bots/ll-backend/) | Implement backend, runtime, tool, database, and migration work |
| [`ll-frontend`](bots/ll-frontend/) | Implement Next.js, React, packages/ui, chat, and entity work |
| [`ll-qa`](bots/ll-qa/) | Independently verify acceptance checks and review every handoff |

### Generic engineering team

| Bot | Purpose |
| --- | --- |
| [`engineering-manager`](bots/engineering-manager/) | Plan and route repository work without implementing it |
| [`backend-engineer`](bots/backend-engineer/) | Implement stack-neutral server, domain, persistence, and integration work |
| [`frontend-engineer`](bots/frontend-engineer/) | Implement stack-neutral user-facing application work |
| [`qa-engineer`](bots/qa-engineer/) | Independently verify implementation handoffs without editing the candidate |

The generic profiles contain no Limelight, agent-platform, framework, database, port, person, or internal-service assumptions.

## Install

Prerequisites:

- Hermes Agent `>=0.21.3`
- Provider authentication configured separately on each machine
- GitHub access to this private repository

```bash
git clone git@github.com:glisom/hermes-bots.git
cd hermes-bots

# One bot
./bin/install-bot mac-ops

# A coordinated team
./bin/install-team generic-engineering
# or
./bin/install-team limelight-engineering
```

The engineering profile names are a routing contract. Install teams with their default names unless you also rewrite every manager roster and reviewer reference.

For an existing live profile that was not installed from this repository, use `--force` once to convert it while preserving credentials, memories, sessions, and runtime data:

```bash
./bin/install-team limelight-engineering --force
```

This overwrites the profile's `config.yaml` with the repository's portable baseline. Inspect local settings first and reapply machine-specific model, provider, and project configuration afterward.

## Configure an engineering team

The distributions intentionally omit models, credentials, absolute repository paths, messaging destinations, and project state.

1. Configure each profile's model and provider locally.
2. Bind a Kanban board to the local repository:

```bash
hermes kanban boards create project-name \
  --name "Project Name" \
  --default-workdir /absolute/path/to/repository \
  --switch
```

3. Run the engineering-manager gateway as the team's only embedded dispatcher. Worker configs disable gateway dispatch and notifications so multiple profiles cannot race for the same card.

New cards stay undispatched until the human gate in the manager charter is satisfied.

## Update

```bash
cd hermes-bots
git pull --ff-only
./bin/update-bot mac-ops
./bin/update-team generic-engineering
```

`hermes profile update` replaces distribution-owned files while preserving credentials, memories, sessions, state, and the installed profile's `config.yaml` by default. Use `--force-config` directly only when you intentionally want the repository baseline to replace local config.

## Repository rules

Never commit:

- `.env`, `auth.json`, API keys, OAuth data, or messaging tokens
- memories, sessions, state databases, logs, caches, backups, or workspaces
- generated cron databases or launchd plists containing machine-specific paths
- absolute machine paths, active gateway state, or local project configuration
- machine-local customization under `local/`

Bots ship conservative defaults and explicit `distribution_owned` allowlists. Schedules and gateways activate only through an installer or a machine-local command.

## Adding a bot

Create `bots/<name>/` with `distribution.yaml`, `SOUL.md`, `profile.yaml`, and `config.yaml`, then add only authored skills or scripts. Remote Hermes profile installs require a distribution at the repository root, so this monorepo installs each bot through `bin/install-bot`, which passes the selected bot directory as a local distribution source.
