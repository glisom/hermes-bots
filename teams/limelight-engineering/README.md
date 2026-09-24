# Limelight Engineering Team

Portable definitions for the existing Limelight agent-platform team:

- `ll-em`
- `ll-backend`
- `ll-frontend`
- `ll-qa`

Install on a new machine:

```bash
./bin/install-team limelight-engineering
```

Convert existing live profiles to repository-managed distributions only after inspecting their local config:

```bash
./bin/install-team limelight-engineering --force
```

The conversion preserves profile-owned credentials and runtime data but replaces `config.yaml` with a portable baseline. Models, provider authentication, the local agent-platform checkout, board state, Linear OAuth, and messaging configuration remain machine-local.
