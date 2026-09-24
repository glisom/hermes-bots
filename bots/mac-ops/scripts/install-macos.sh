#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 [--profile <name>]" >&2
  exit 2
}

PROFILE="mac-ops"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || usage
      PROFILE="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || {
  echo "mac-ops requires macOS" >&2
  exit 1
}

HERMES_BIN="${HERMES_BIN:-$(command -v hermes)}"
HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"
PROFILE_DIR="$HERMES_ROOT/profiles/$PROFILE"
WATCHDOG="$PROFILE_DIR/scripts/mac_health_watch.py"
CONFIG="$PROFILE_DIR/scripts/mac_health_config.json"
LABEL="ai.hermes.${PROFILE}-watchdog"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
JOB_NAME="[bot:$PROFILE] Health watchdog"

[[ -f "$WATCHDOG" ]] || {
  echo "watchdog not found: $WATCHDOG" >&2
  exit 1
}
[[ -f "$CONFIG" ]] || {
  echo "watchdog config not found: $CONFIG" >&2
  exit 1
}

mkdir -p "$PROFILE_DIR/logs" "$PROFILE_DIR/state" "$HOME/Library/LaunchAgents"
chmod 700 "$WATCHDOG"

PROFILE="$PROFILE" PROFILE_DIR="$PROFILE_DIR" LABEL="$LABEL" PLIST="$PLIST" /usr/bin/python3 - <<'PY'
import os
import plistlib
from pathlib import Path

profile_dir = Path(os.environ["PROFILE_DIR"])
plist = Path(os.environ["PLIST"])
payload = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": [
        "/usr/bin/python3",
        str(profile_dir / "scripts" / "mac_health_watch.py"),
        "watchdog",
    ],
    "EnvironmentVariables": {
        "HOME": str(Path.home()),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    },
    "RunAtLoad": True,
    "StartInterval": 120,
    "ProcessType": "Background",
    "LowPriorityIO": True,
    "StandardOutPath": str(profile_dir / "logs" / "watchdog.stdout.log"),
    "StandardErrorPath": str(profile_dir / "logs" / "watchdog.stderr.log"),
}
with plist.open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY

plutil -lint "$PLIST" >/dev/null
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

while IFS= read -r job_id; do
  [[ -n "$job_id" ]] && "$HERMES_BIN" -p "$PROFILE" cron remove "$job_id"
done < <(PROFILE_DIR="$PROFILE_DIR" JOB_NAME="$JOB_NAME" /usr/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["PROFILE_DIR"]) / "cron" / "jobs.json"
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
    for job in data.get("jobs", []):
        if job.get("name") == os.environ["JOB_NAME"]:
            print(job["id"])
PY
)

"$HERMES_BIN" -p "$PROFILE" cron create 'every 5m' \
  --name "$JOB_NAME" \
  --script mac_health_watch.py \
  --no-agent \
  --deliver bot-chat \
  --failure-deliver bot-chat

/usr/bin/python3 -m py_compile "$WATCHDOG"
/usr/bin/python3 "$WATCHDOG" self-test
/usr/bin/python3 "$WATCHDOG" snapshot >/dev/null
launchctl print "$DOMAIN/$LABEL" >/dev/null
"$HERMES_BIN" -p "$PROFILE" cron list --all

echo "Installed and activated $PROFILE"
