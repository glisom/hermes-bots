# Hermes Bots

Reusable Hermes profile distributions and machine bootstrap scripts.

This repository stores bot definitions, not live Hermes state. Each machine keeps its own credentials, memories, sessions, databases, logs, caches, and local overrides.

## Bots

| Bot | Purpose | Platforms |
| --- | --- | --- |
| [`mac-ops`](bots/mac-ops/) | Monitor a Mac, recover allowlisted services, and investigate incidents | macOS |

## Install

Prerequisites:

- Hermes Agent installed and authenticated
- A supervised Hermes gateway running on the target machine
- GitHub access to this private repository

```bash
git clone git@github.com:glisom/hermes-bots.git
cd hermes-bots
./bin/install-bot mac-ops
```

The installer creates the Hermes profile from the local distribution, installs the independent macOS launchd watchdog, and creates the five-minute script-only Hermes cron job. Cron and launchd activation are explicit bootstrap steps rather than hidden profile-install hooks.

Configure machine-specific settings after installation:

```bash
$EDITOR ~/.hermes/profiles/mac-ops/scripts/mac_health_config.json
hermes -p mac-ops auth add copilot
hermes gateway start
```

## Update

```bash
cd hermes-bots
git pull --ff-only
./bin/update-bot mac-ops
```

`hermes profile update` replaces distribution-owned files while preserving credentials, memories, sessions, state, and the installed profile's `config.yaml` by default. Re-run the platform installer to refresh launchd and cron definitions.

## Repository rules

Never commit:

- `.env`, `auth.json`, API keys, OAuth data, or messaging tokens
- memories, sessions, state databases, logs, caches, backups, or workspaces
- generated launchd plists containing machine-specific paths
- machine-local configuration under `local/`

Bots should ship conservative defaults. Host paths, service allowlists, notification targets, bot tokens, and thresholds belong to each installed machine.

## Adding a bot

Create `bots/<name>/` with `distribution.yaml`, `SOUL.md`, `profile.yaml`, and `config.yaml`, then add any authored skills or scripts. Remote Hermes profile installs require a distribution at the repository root, so this monorepo is installed through `bin/install-bot`, which passes the selected bot directory as a local distribution source.
