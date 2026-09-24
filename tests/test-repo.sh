#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCHDOG="$ROOT/bots/mac-ops/scripts/mac_health_watch.py"

bash -n \
  "$ROOT/bin/install-bot" \
  "$ROOT/bin/update-bot" \
  "$ROOT/bin/install-team" \
  "$ROOT/bin/update-team" \
  "$ROOT/bots/mac-ops/scripts/install-macos.sh" \
  "$0"
/usr/bin/python3 -m py_compile "$WATCHDOG"
/usr/bin/python3 "$WATCHDOG" self-test

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

for manifest in "$ROOT"/bots/*/distribution.yaml; do
  bot_dir="$(dirname "$manifest")"
  bot_name="$(basename "$bot_dir")"
  HERMES_HOME="$TMP_HOME" hermes profile install "$bot_dir" --yes
  test_profile="$TMP_HOME/profiles/$bot_name"
  [[ -f "$test_profile/distribution.yaml" ]]
  [[ -f "$test_profile/SOUL.md" ]]
  [[ -f "$test_profile/config.yaml" ]]
  [[ -f "$test_profile/profile.yaml" ]]
  [[ ! -e "$test_profile/auth.json" ]]
  [[ ! -e "$test_profile/.env" ]]
done

ROOT="$ROOT" /usr/bin/python3 - <<'PY'
import os
import re
from pathlib import Path

root = Path(os.environ["ROOT"])
expected = {
    "mac-ops",
    "ll-backend", "ll-em", "ll-frontend", "ll-qa",
    "backend-engineer", "engineering-manager", "frontend-engineer", "qa-engineer",
}
actual = {p.parent.name for p in (root / "bots").glob("*/distribution.yaml")}
assert actual == expected, (actual, expected)

secret_patterns = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"whsec_[A-Za-z0-9_-]{10,}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
]
for path in root.rglob("*"):
    assert not path.is_symlink(), f"symlink is not distributable: {path.relative_to(root)}"
    if not path.is_file() or ".git" in path.parts or path.name == "test-repo.sh":
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    assert "/Users/grantisom" not in text, f"machine path found: {path.relative_to(root)}"
    if any(pattern.search(text) for pattern in secret_patterns):
        raise AssertionError(f"possible secret found: {path.relative_to(root)}")

generic_root = root / "bots"
for name in ("backend-engineer", "engineering-manager", "frontend-engineer", "qa-engineer"):
    for path in (generic_root / name).rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("limelight", "agent-platform", "ll-backend", "ll-frontend", "ll-qa", "ll-em", "localhost:9000", "localhost:9001"):
            assert forbidden not in text, f"{forbidden!r} found in generic bot {path.relative_to(root)}"

for manager, members in {
    "ll-em": ("ll-em", "ll-backend", "ll-frontend", "ll-qa"),
    "engineering-manager": ("engineering-manager", "backend-engineer", "frontend-engineer", "qa-engineer"),
}.items():
    config = (generic_root / manager / "config.yaml").read_text(encoding="utf-8")
    for member in members:
        assert f"    - {member}" in config
    assert "dispatch_in_gateway: true" in config

for worker in expected - {"mac-ops", "ll-em", "engineering-manager"}:
    config = (generic_root / worker / "config.yaml").read_text(encoding="utf-8")
    assert "dispatch_in_gateway: false" in config
PY

echo "All checks passed"
