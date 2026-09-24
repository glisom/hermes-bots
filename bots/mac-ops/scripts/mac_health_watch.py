#!/usr/bin/env python3
"""Low-cost macOS health collector and launchd watchdog for Mac Ops."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROFILE_HOME = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).with_name("mac_health_config.json")
STATE_DIR = PROFILE_HOME / "state"
STATE_PATH = STATE_DIR / "mac-health-state.json"
LOCK_PATH = STATE_DIR / "mac-health-state.lock"
WATCHDOG_LOG = PROFILE_HOME / "logs" / "mac-health-watchdog.log"
HERMES = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "hermes"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
CRASH_DIRS = (
    Path.home() / "Library" / "Logs" / "DiagnosticReports",
    Path("/Library/Logs/DiagnosticReports"),
)
CRASH_SUFFIXES = (".ips", ".crash", ".spin", ".panic", ".hang")
RESOURCE_REPORT_MARKERS = ("cpu_resource.diag", "gpu_resource.diag", "memory_resource.diag")

DEFAULT_CONFIG: Dict[str, Any] = {
    "disk_warning_free_gb": 50,
    "disk_critical_free_gb": 20,
    "disk_warning_free_percent": 8,
    "disk_critical_free_percent": 4,
    "memory_warning_free_percent": 10,
    "memory_critical_free_percent": 5,
    "load_warning_per_core": 2.0,
    "load_critical_per_core": 3.0,
    "oversized_log_mb": 500,
    "repeat_alert_seconds": 3600,
    "remediation_cooldown_seconds": 1800,
    "watched_launch_agents": [],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(
    argv: List[str],
    timeout: float = 15,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, stdout, stderr or f"timed out after {timeout}s"
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


def load_config() -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config.update(raw)
    except (OSError, ValueError, TypeError):
        pass
    return config


def load_state() -> Dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, STATE_PATH)


@contextlib.contextmanager
def state_lock():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def append_watchdog_log(event: Dict[str, Any]) -> None:
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    if WATCHDOG_LOG.exists() and WATCHDOG_LOG.stat().st_size > 5 * 1024 * 1024:
        rotated = WATCHDOG_LOG.with_suffix(".log.1")
        with contextlib.suppress(OSError):
            rotated.unlink()
        WATCHDOG_LOG.replace(rotated)
    with WATCHDOG_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def launch_agent_plist(label: str) -> Path:
    return LAUNCH_AGENTS / f"{label}.plist"


def launch_agent_disabled(label: str) -> bool:
    rc, stdout, _ = run(["/bin/launchctl", "print-disabled", f"gui/{os.getuid()}"], timeout=8)
    if rc != 0:
        return False
    match = re.search(rf'"{re.escape(label)}"\s*=>\s*(enabled|disabled)', stdout)
    return bool(match and match.group(1) == "disabled")


def launch_agent_status(label: str, tcp_port: Optional[int] = None) -> Dict[str, Any]:
    target = f"gui/{os.getuid()}/{label}"
    rc, stdout, stderr = run(["/bin/launchctl", "print", target], timeout=8)
    text = stdout + "\n" + stderr
    state_match = re.search(r"^\s*state\s*=\s*([^\n]+)", text, re.MULTILINE)
    pid_match = re.search(r"^\s*pid\s*=\s*(\d+)", text, re.MULTILINE)
    exit_match = re.search(r"^\s*last exit code\s*=\s*([^\n]+)", text, re.MULTILINE)
    loaded = rc == 0
    status: Dict[str, Any] = {
        "label": label,
        "disabled": launch_agent_disabled(label),
        "loaded": loaded,
        "state": state_match.group(1).strip() if state_match else "unloaded",
        "pid": int(pid_match.group(1)) if pid_match else None,
        "last_exit": exit_match.group(1).strip() if exit_match else None,
    }
    if tcp_port and loaded and status["state"] == "running":
        status["tcp_port"] = tcp_port
        status["tcp_listening"] = tcp_listening(tcp_port)
    return status


def tcp_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1):
            return True
    except OSError:
        return False


def service_healthy(status: Dict[str, Any]) -> bool:
    # A launchctl disabled override is explicit operator intent, not an outage.
    if status.get("disabled"):
        return True
    if not status.get("loaded") or status.get("state") != "running":
        return False
    return status.get("tcp_listening", True) is not False


def restart_launch_agent(spec: Dict[str, Any]) -> Dict[str, Any]:
    label = str(spec["label"])
    plist = launch_agent_plist(label)
    before = launch_agent_status(label, spec.get("tcp_port"))
    actions: List[Dict[str, Any]] = []
    target = f"gui/{os.getuid()}/{label}"

    if not plist.is_file():
        return {
            "label": label,
            "before": before,
            "actions": [],
            "after": before,
            "success": False,
            "error": f"launch agent plist missing: {plist}",
        }

    if not before["loaded"]:
        rc, stdout, stderr = run(
            ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)],
            timeout=15,
        )
        actions.append({"command": "bootstrap", "exit_code": rc, "detail": (stderr or stdout).strip()[-500:]})

    rc, stdout, stderr = run(["/bin/launchctl", "kickstart", "-k", target], timeout=15)
    actions.append({"command": "kickstart", "exit_code": rc, "detail": (stderr or stdout).strip()[-500:]})
    time.sleep(8 if spec.get("tcp_port") else 3)
    after = launch_agent_status(label, spec.get("tcp_port"))
    return {
        "label": label,
        "before": before,
        "actions": actions,
        "after": after,
        "success": service_healthy(after),
    }


def watched_specs(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    specs = config.get("watched_launch_agents")
    if not isinstance(specs, list):
        return []
    return [spec for spec in specs if isinstance(spec, dict) and spec.get("label")]


def run_watchdog(config: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = time.time()
    cooldown = float(config.get("remediation_cooldown_seconds", 1800))
    attempts = state.setdefault("service_attempts", {})
    events = state.setdefault("events", [])
    new_events: List[Dict[str, Any]] = []

    for spec in watched_specs(config):
        label = str(spec["label"])
        status = launch_agent_status(label, spec.get("tcp_port"))
        if service_healthy(status) or not spec.get("auto_restart"):
            continue
        last_attempt = float(attempts.get(label, 0) or 0)
        if now - last_attempt < cooldown:
            continue
        attempts[label] = now
        result = restart_launch_agent(spec)
        event = {
            "id": hashlib.sha256(f"{label}:{now}:{os.getpid()}".encode()).hexdigest()[:16],
            "observed_at": utc_now(),
            "type": "launch_agent_remediation",
            "severity": "critical" if spec.get("critical") else "warning",
            "reported": False,
            **result,
        }
        events.append(event)
        new_events.append(event)
        append_watchdog_log(event)

    state["watchdog_heartbeat"] = now
    state["watchdog_heartbeat_at"] = utc_now()
    state["events"] = events[-50:]
    return new_events


def issue(code: str, severity: str, summary: str, details: Dict[str, Any]) -> Dict[str, Any]:
    return {"code": code, "severity": severity, "summary": summary, "details": details}


def resource_snapshot(config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    snapshot: Dict[str, Any] = {}
    issues: List[Dict[str, Any]] = []
    volume = Path("/System/Volumes/Data") if Path("/System/Volumes/Data").exists() else Path("/")

    try:
        usage = shutil.disk_usage(volume)
        free_gb = usage.free / (1024 ** 3)
        free_percent = usage.free * 100 / usage.total
        snapshot["disk"] = {
            "volume": str(volume),
            "free_gb": round(free_gb, 1),
            "free_percent": round(free_percent, 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
        }
        severity = None
        if free_gb < float(config["disk_critical_free_gb"]) or free_percent < float(config["disk_critical_free_percent"]):
            severity = "critical"
        elif free_gb < float(config["disk_warning_free_gb"]) or free_percent < float(config["disk_warning_free_percent"]):
            severity = "warning"
        if severity:
            issues.append(issue("disk_space_low", severity, "Data volume free space is low", snapshot["disk"]))
    except OSError as exc:
        issues.append(issue("disk_check_failed", "warning", "Could not read disk usage", {"error": str(exc)}))

    rc, stdout, stderr = run(["/usr/bin/memory_pressure", "-Q"], timeout=10)
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", stdout + stderr)
    if rc == 0 and match:
        free_percent = int(match.group(1))
        snapshot["memory_free_percent"] = free_percent
        if free_percent < int(config["memory_critical_free_percent"]):
            issues.append(issue("memory_pressure", "critical", "Memory pressure is critical", {"free_percent": free_percent}))
        elif free_percent < int(config["memory_warning_free_percent"]):
            issues.append(issue("memory_pressure", "warning", "Memory pressure is elevated", {"free_percent": free_percent}))
    else:
        snapshot["memory_check_error"] = (stderr or stdout).strip()[-300:]

    cores = os.cpu_count() or 1
    load1, load5, load15 = os.getloadavg()
    snapshot["load"] = {
        "logical_cores": cores,
        "one_minute": round(load1, 2),
        "five_minute": round(load5, 2),
        "fifteen_minute": round(load15, 2),
    }
    critical = float(config["load_critical_per_core"]) * cores
    warning = float(config["load_warning_per_core"]) * cores
    if load1 > critical and load5 > critical:
        issues.append(issue("load_high", "critical", "Sustained system load is critical", snapshot["load"]))
    elif load1 > warning and load5 > warning:
        issues.append(issue("load_high", "warning", "Sustained system load is high", snapshot["load"]))

    rc, stdout, _ = run(["/bin/ps", "-axo", "stat="], timeout=10)
    if rc == 0:
        zombies = sum(1 for line in stdout.splitlines() if line.lstrip().startswith("Z"))
        snapshot["zombie_processes"] = zombies
        if zombies >= 5:
            issues.append(issue("zombie_processes", "warning", "Multiple zombie processes are present", {"count": zombies}))

    rc, stdout, stderr = run(["/usr/bin/pmset", "-g", "therm"], timeout=10)
    if rc == 0:
        limits = {
            key: int(value)
            for key, value in re.findall(r"(CPU_Speed_Limit|CPU_Available_CPUs|Scheduler_Limit)\s*=\s*(\d+)", stdout)
        }
        if limits:
            snapshot["thermal_limits"] = limits
            speed = limits.get("CPU_Speed_Limit", 100)
            scheduler = limits.get("Scheduler_Limit", 100)
            if speed < 80 or scheduler < 80:
                issues.append(issue("thermal_throttling", "warning", "macOS is thermally throttling the system", limits))
    elif stderr.strip():
        snapshot["thermal_check_error"] = stderr.strip()[-300:]

    return snapshot, issues


def default_gateway_health() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not HERMES.is_file():
        return {}, [issue("hermes_missing", "critical", "Hermes executable is missing", {"path": str(HERMES)})]
    env = dict(os.environ)
    for key in ("HERMES_HOME", "HERMES_PROFILE", "HERMES_ACTIVE_PROFILE"):
        env.pop(key, None)
    rc, stdout, stderr = run([str(HERMES), "gateway", "status"], timeout=30, env=env)
    text = (stdout + "\n" + stderr).strip()
    summary = {"exit_code": rc, "running": "Gateway is supervised" in text or "Gateway is running" in text}
    issues: List[Dict[str, Any]] = []
    if rc != 0 or not summary["running"]:
        issues.append(issue("hermes_gateway_down", "critical", "Hermes gateway health check failed", {"exit_code": rc, "output": text[-1000:]}))
    if "Service definition is stale" in text:
        issues.append(issue("hermes_gateway_service_stale", "warning", "Hermes launchd service definition is stale", {"remedy_hint": "hermes gateway start"}))
    return summary, issues


def launch_agent_health(config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    statuses: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for spec in watched_specs(config):
        status = launch_agent_status(str(spec["label"]), spec.get("tcp_port"))
        statuses.append(status)
        if service_healthy(status):
            continue
        severity = "critical" if spec.get("critical") else "warning"
        details = dict(status)
        details["plist"] = str(launch_agent_plist(str(spec["label"])))
        issues.append(issue(
            f"launch_agent:{spec['label']}",
            severity,
            f"Launch agent {spec['label']} is not healthy",
            details,
        ))
    return statuses, issues


def pm2_health() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if shutil.which("pm2") is None:
        return [], []
    rc, stdout, _ = run(["pm2", "jlist"], timeout=15)
    if rc != 0 or not stdout.strip():
        return [], []
    try:
        rows = json.loads(stdout)
    except ValueError:
        return [], []
    statuses: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return statuses, issues
    for row in rows:
        env = row.get("pm2_env") or {}
        status = {
            "name": row.get("name"),
            "pid": row.get("pid"),
            "status": env.get("status"),
            "restarts": env.get("restart_time"),
        }
        statuses.append(status)
        if status["status"] not in (None, "online"):
            issues.append(issue("pm2_process_down", "warning", f"PM2 process {status['name']} is {status['status']}", status))
    return statuses, issues


def oversized_logs(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    threshold = float(config["oversized_log_mb"]) * 1024 * 1024
    issues: List[Dict[str, Any]] = []
    roots = (Path.home() / ".hermes" / "logs", PROFILE_HOME / "logs")
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.log"):
            try:
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                size = path.stat().st_size
            except OSError:
                continue
            if size > threshold:
                issues.append(issue(
                    "oversized_log",
                    "warning",
                    f"Log file {path.name} is oversized",
                    {"path": str(path), "size_mb": round(size / 1024 / 1024, 1)},
                ))
    return issues


def new_crash_reports(state: Dict[str, Any], mutate: bool) -> Tuple[List[Dict[str, Any]], float]:
    now = time.time()
    last_scan = float(state.get("last_crash_scan", now) or now)
    newest = last_scan
    reports: List[Dict[str, Any]] = []
    for root in CRASH_DIRS:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            name_lower = path.name.lower()
            is_crash = name_lower.endswith(CRASH_SUFFIXES) or any(
                marker in name_lower for marker in RESOURCE_REPORT_MARKERS
            )
            if not path.is_file() or not is_crash:
                continue
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            newest = max(newest, modified)
            if modified <= last_scan or modified > now + 60:
                continue
            reports.append({
                "name": path.name,
                "path": str(path),
                "modified_at": datetime.fromtimestamp(modified, timezone.utc).isoformat(),
            })
    reports.sort(key=lambda row: row["modified_at"], reverse=True)
    if mutate:
        state["last_crash_scan"] = max(now, newest)
    return reports[:20], newest


def top_processes() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, order in (("cpu", "-r"), ("memory", "-m")):
        rc, stdout, _ = run(
            ["/bin/ps", "-axo", "pid=,pcpu=,pmem=,etime=,comm=", order],
            timeout=10,
        )
        if rc == 0:
            result[key] = [line.strip() for line in stdout.splitlines()[:8]]
    return result


def collect(config: Dict[str, Any], state: Dict[str, Any], mutate: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    snapshot, issues = resource_snapshot(config)
    services, service_issues = launch_agent_health(config)
    gateway, gateway_issues = default_gateway_health()
    pm2, pm2_issues = pm2_health()
    crashes, _ = new_crash_reports(state, mutate=mutate)

    snapshot["launch_agents"] = services
    snapshot["hermes_gateway"] = gateway
    if pm2:
        snapshot["pm2"] = pm2
    issues.extend(service_issues)
    issues.extend(gateway_issues)
    issues.extend(pm2_issues)
    issues.extend(oversized_logs(config))

    if crashes:
        issues.append(issue("new_crash_reports", "warning", "New macOS crash or resource reports were written", {"reports": crashes}))

    heartbeat = float(state.get("watchdog_heartbeat", 0) or 0)
    snapshot["watchdog_heartbeat_at"] = state.get("watchdog_heartbeat_at")
    if heartbeat and time.time() - heartbeat > 600:
        issues.append(issue(
            "watchdog_stale",
            "warning",
            "The independent launchd watchdog heartbeat is stale",
            {"heartbeat_at": state.get("watchdog_heartbeat_at")},
        ))

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda row: (severity_order.get(row["severity"], 9), row["code"]))
    if issues:
        snapshot["top_processes"] = top_processes()
    return snapshot, issues


def issue_fingerprint(issues: List[Dict[str, Any]]) -> str:
    stable = [
        {
            "code": row.get("code"),
            "severity": row.get("severity"),
            "subject": (row.get("details") or {}).get("label") or (row.get("details") or {}).get("path"),
        }
        for row in issues
    ]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def emit_report(config: Dict[str, Any], state: Dict[str, Any]) -> bool:
    snapshot, issues = collect(config, state, mutate=True)
    pending = [event for event in state.get("events", []) if not event.get("reported")]
    now = time.time()

    if not issues and not pending:
        state["last_report_fingerprint"] = ""
        state["last_report_at"] = now
        save_state(state)
        return False

    fingerprint = issue_fingerprint(issues)
    repeat_after = float(config.get("repeat_alert_seconds", 3600))
    unchanged = fingerprint == state.get("last_report_fingerprint")
    recent = now - float(state.get("last_report_at", 0) or 0) < repeat_after
    if unchanged and recent and not pending:
        save_state(state)
        return False

    payload = {
        "type": "mac_health_incident",
        "observed_at": utc_now(),
        "issues": issues,
        "watchdog_events": pending,
        "snapshot": snapshot,
        "requested_action": "Verify each issue live, investigate the root cause, apply only safe reversible remediation, and prove recovery.",
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))

    pending_ids = {event.get("id") for event in pending}
    for event in state.get("events", []):
        if event.get("id") in pending_ids:
            event["reported"] = True
    state["last_report_fingerprint"] = fingerprint
    state["last_report_at"] = now
    save_state(state)
    return True


def self_test() -> None:
    assert service_healthy({"loaded": True, "state": "running"})
    assert not service_healthy({"loaded": False, "state": "unloaded"})
    assert not service_healthy({"loaded": True, "state": "running", "tcp_listening": False})
    first = issue_fingerprint([issue("x", "warning", "a", {"label": "svc", "value": 1})])
    second = issue_fingerprint([issue("x", "warning", "b", {"label": "svc", "value": 2})])
    assert first == second
    assert PROFILE_HOME.name == "mac-ops"
    print("self-test: ok")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", nargs="?", default="report", choices=("watchdog", "report", "snapshot", "self-test"))
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
        return 0

    config = load_config()
    with state_lock():
        state = load_state()
        if args.mode == "watchdog":
            run_watchdog(config, state)
            save_state(state)
            return 0
        if args.mode == "snapshot":
            snapshot, issues = collect(config, state, mutate=False)
            print(json.dumps({"observed_at": utc_now(), "issues": issues, "snapshot": snapshot}, indent=2, sort_keys=True))
            return 1 if any(row.get("severity") == "critical" for row in issues) else 0
        emit_report(config, state)
        return 0


if __name__ == "__main__":
    sys.exit(main())
