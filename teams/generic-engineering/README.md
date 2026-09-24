# Generic Engineering Team

A coordinated, stack-neutral Hermes Kanban team:

- `engineering-manager`
- `backend-engineer`
- `frontend-engineer`
- `qa-engineer`

Install from the repository root:

```bash
./bin/install-team generic-engineering
```

The names are a routing contract. The manager config assigns work and reviews by these exact profile names. Project paths, models, provider credentials, messaging, and board data remain machine-local.

Only the manager profile should own gateway dispatch. Worker profiles have `kanban.dispatch_in_gateway: false`; task-scoped Kanban lifecycle tools are injected by the dispatcher.
