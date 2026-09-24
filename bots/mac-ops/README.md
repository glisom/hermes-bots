# Mac Ops

A Hermes profile distribution plus a deterministic, script-only macOS watchdog.

## What it monitors

- root volume free space
- memory pressure and host load
- selected user launch agents
- recent macOS crash and resource reports
- oversized Hermes logs
- Hermes gateway responsiveness

Healthy checks stay silent. Incidents are sent to the profile's Bot Chat, where the Mac Ops agent investigates and may apply only safe, reversible remediations.

## Install

From the repository root:

```bash
./bin/install-bot mac-ops
```

This explicitly activates two machine-local schedules:

- `ai.hermes.mac-ops-watchdog`, a launchd job every two minutes
- `[bot:mac-ops] Health watchdog`, a script-only Hermes cron job every five minutes

Edit `~/.hermes/profiles/mac-ops/scripts/mac_health_config.json` after installation for machine-specific launch agents and thresholds.

## Safety

The deterministic watchdog may restart only explicitly allowlisted launch agents. The agent charter prohibits sudo, reboots, upgrades, credential changes, security changes, deleting user data, or sending messages to other people.
