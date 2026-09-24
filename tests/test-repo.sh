#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT="$ROOT/bots/mac-ops"
WATCHDOG="$BOT/scripts/mac_health_watch.py"

/usr/bin/python3 -m py_compile "$WATCHDOG"
/usr/bin/python3 "$WATCHDOG" self-test

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT
HERMES_HOME="$TMP_HOME" hermes profile install "$BOT" --name mac-ops-test --yes

TEST_PROFILE="$TMP_HOME/profiles/mac-ops-test"
[[ -f "$TEST_PROFILE/distribution.yaml" ]]
[[ -f "$TEST_PROFILE/SOUL.md" ]]
[[ -f "$TEST_PROFILE/scripts/mac_health_watch.py" ]]
[[ ! -e "$TEST_PROFILE/auth.json" ]]
[[ ! -e "$TEST_PROFILE/state/mac-health-state.json" ]]

TEST_PROFILE="$TEST_PROFILE" /usr/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

profile = Path(os.environ["TEST_PROFILE"])
manifest = profile / "distribution.yaml"
assert "name: mac-ops-test" in manifest.read_text(encoding="utf-8")
json.loads((profile / "scripts" / "mac_health_config.json").read_text(encoding="utf-8"))
PY

ROOT="$ROOT" /usr/bin/python3 - <<'PY'
import os
import re
from pathlib import Path

root = Path(os.environ["ROOT"])
patterns = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
]
for path in root.rglob("*"):
    if not path.is_file() or ".git" in path.parts or path.name == "test-repo.sh":
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if any(pattern.search(text) for pattern in patterns):
        raise SystemExit(f"possible secret found: {path.relative_to(root)}")
PY

echo "All checks passed"
