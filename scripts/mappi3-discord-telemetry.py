#!/usr/bin/env python3
"""MapPI3 -> Discord telemetry bridge.

Runs from The Garden/Oracle VM (or any host that can SSH to NukeBox). It keeps
Discord credentials off the Raspberry Pi, collects truthful live state from the
Pi over the NukeBox hotspot bridge, and posts a compact privacy-safe snapshot to
Discord.

Default access path: Oracle -> nukebox -> mappi3@10.42.0.1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DISCORD_API = "https://discord.com/api/v10"
DEFAULT_CHANNEL_ID = "1517340758238036108"  # #maple
DEFAULT_STATE = pathlib.Path.home() / ".cache" / "mappi3-discord-telemetry-state.json"
DEFAULT_ENV_PATHS = [
    pathlib.Path.home() / ".hermes" / "profiles" / "maple" / ".env",
    pathlib.Path.home() / ".hermes" / ".env",
]

REMOTE_COLLECTOR = r'''
import json, subprocess, time, urllib.request, urllib.error, socket, os

def sh(cmd, timeout=12):
    try:
        r = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
        return {'rc': r.returncode, 'out': r.stdout.strip(), 'err': r.stderr.strip()}
    except Exception as e:
        return {'rc': -1, 'out': '', 'err': repr(e)}

def fetch(path, timeout=22):
    try:
        with urllib.request.urlopen('http://127.0.0.1:5050' + path, timeout=timeout) as resp:
            return {'ok': True, 'status': resp.status, 'json': json.loads(resp.read().decode(errors='replace'))}
    except Exception as e:
        return {'ok': False, 'error': repr(e)}

def first_line(s):
    return (s or '').splitlines()[0] if s else ''

payload = {
    'collector_schema': 'mappi3.telemetry.v1',
    'pi_epoch': int(time.time()),
    'pi_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'hostname': socket.gethostname(),
    'whoami': sh('whoami', 4)['out'],
    'uptime': sh('uptime -p', 6)['out'],
    'services': {
        'mappi3-web': first_line(sh('systemctl is-active mappi3-web.service 2>/dev/null || true', 6)['out']),
        'gpsd': first_line(sh('systemctl is-active gpsd.service 2>/dev/null || true', 6)['out']),
        'chrony': first_line(sh('systemctl is-active chrony.service 2>/dev/null || true', 6)['out']),
        'tailscaled': first_line(sh('systemctl is-active tailscaled.service 2>/dev/null || true', 6)['out']),
    },
    'clock': {
        'timedatectl': sh('timedatectl 2>/dev/null | sed -n "1,8p" || true', 8)['out'],
        'mappi3_clock_status': sh('mappi3-clock-status 2>/dev/null | head -120 || true', 25)['out'],
    },
    'tailscale_ip': sh('tailscale ip -4 2>/dev/null | head -1 || true', 6)['out'],
    'network': sh('ip route | sed -n "1,8p"', 6)['out'],
    'api_status': fetch('/api/status'),
    'api_sense': fetch('/api/sense'),
    # Deliberately do not collect /api/network/status here: it can include saved Wi-Fi labels/details.
}
print(json.dumps(payload, separators=(',', ':'), default=str))
'''


def load_env(paths: list[pathlib.Path]) -> dict[str, str]:
    env: dict[str, str] = {}
    for path in paths:
        try:
            for raw in path.read_text(errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        except FileNotFoundError:
            continue
    env.update({k: v for k, v in os.environ.items() if k.startswith("MAPPI3_") or k.startswith("DISCORD_")})
    return env


def run(cmd: list[str], timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, input=input_text, capture_output=True, timeout=timeout)


def _ssh_remote(nukebox_host: str, pi_host: str, pi_user: str, remote_command: str, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    remote = f"ssh -o BatchMode=yes -o ConnectTimeout=8 {pi_user}@{pi_host} {remote_command}"
    return run([
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", nukebox_host, remote
    ], timeout=timeout, input_text=input_text)


def collect_via_ssh(nukebox_host: str, pi_host: str, pi_user: str, timeout: int = 90) -> dict[str, Any]:
    proc = _ssh_remote(nukebox_host, pi_host, pi_user, "python3 -", timeout=timeout, input_text=REMOTE_COLLECTOR)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ssh collector failed")[-1600:])
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("ssh collector returned no JSON")
    return json.loads(lines[-1])


def sync_pi_clock_if_needed(nukebox_host: str, pi_host: str, pi_user: str, data: dict[str, Any], threshold_seconds: int = 60) -> dict[str, Any]:
    """Set Pi wall clock from the collector host when hotspot/offline time has drifted.

    This is intentionally bridge-driven: no internet/NTP credentials on the Pi, and GPS time is ignored unless gpsd has a real valid fix.
    """
    now = int(time.time())
    try:
        pi_epoch = int(float(data.get("pi_epoch")))
    except Exception:
        pi_epoch = 0
    skew = pi_epoch - now if pi_epoch else None
    if skew is not None and abs(skew) <= threshold_seconds:
        return {"attempted": False, "skew_seconds": skew, "reason": "within-threshold"}
    # Use sudo -n so telemetry never hangs at a password prompt.
    set_time = dt.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
    proc = _ssh_remote(
        nukebox_host,
        pi_host,
        pi_user,
        f"sudo -n /bin/date -u -s {shlex.quote(set_time)} && /bin/date -u +%Y-%m-%dT%H:%M:%SZ",
        timeout=30,
    )
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "skew_seconds": skew,
        "set_epoch": now,
        "stdout": proc.stdout.strip()[-300:],
        "stderr": proc.stderr.strip()[-300:],
    }


def safe_get(data: dict[str, Any], *keys: str, default=None):
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def fmt_bytes(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return "?"


def fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    sign = "behind" if seconds < 0 else "ahead"
    seconds = abs(seconds)
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days:
        return f"{days}d {hours}h {sign}"
    if hours:
        return f"{hours}h {minutes}m {sign}"
    return f"{minutes}m {sign}"


def gps_line(gps: dict[str, Any], privacy: str) -> str:
    if not gps:
        return "GPS: `missing`"
    mode = gps.get("mode")
    fix = bool(gps.get("fix"))
    sats = gps.get("satellites")
    lat, lon = gps.get("lat"), gps.get("lon")
    parts = [f"mode `{mode}`", f"fix `{fix}`", f"sats `{sats if sats is not None else '?'}`"]
    if fix and lat is not None and lon is not None:
        if privacy == "exact":
            parts.append(f"loc `{float(lat):.6f}, {float(lon):.6f}`")
        elif privacy == "rounded":
            parts.append(f"loc `~{float(lat):.3f}, {float(lon):.3f}`")
        elif privacy == "trail-name":
            parts.append("loc `hidden · trail-name mode`")
        else:
            parts.append("loc `hidden`")
    else:
        parts.append("loc `no current fix`")
    return "GPS: " + " | ".join(parts)


def clock_warning(pi_epoch: Any, collector_epoch: float) -> tuple[str, float | None]:
    try:
        pi = float(pi_epoch)
    except Exception:
        return "Clock: `unknown`", None
    skew = pi - collector_epoch
    # Treat >1 day skew as unsafe for schedules/cache timestamps.
    flag = "⚠️" if abs(skew) > 86400 else "✅"
    return f"Clock: {flag} Pi `{dt.datetime.utcfromtimestamp(pi).strftime('%Y-%m-%d %H:%MZ')}` ({fmt_age(skew)} collector)", skew


def build_message(data: dict[str, Any], env: dict[str, str]) -> str:
    collector_epoch = time.time()
    status = safe_get(data, "api_status", "json", default={}) or {}
    sense = safe_get(data, "api_sense", "json", default={}) or {}
    # /api/sense may either be the cache directly or wrapped under sense in older/newer builds.
    if "sense" in sense and isinstance(sense.get("sense"), dict):
        sense = sense.get("sense") or sense
    api_sense = status.get("sense") if isinstance(status.get("sense"), dict) else sense
    system = status.get("system") or {}
    power = status.get("power") or status.get("battery") or {}
    gps = status.get("gps") or {}
    state = status.get("state") or {}
    privacy = (env.get("MAPPI3_TELEMETRY_LOCATION_PRIVACY") or "rounded").lower()
    next_hike = env.get("MAPPI3_NEXT_HIKE") or state.get("next_hike") or state.get("next_location") or "not set"
    clock_line, skew = clock_warning(data.get("pi_epoch"), collector_epoch)
    services = data.get("services") or {}
    service_line = ", ".join(f"{k}:{v or '?'}" for k, v in services.items()) or "unknown"
    mem = system.get("memory") or {}
    disk = system.get("disk") or {}
    mode = status.get("connection_mode") or ("hotspot" if status.get("hotspot_active") else "unknown")
    temp_c = system.get("temperature_c")
    sense_mode = api_sense.get("mode") or status.get("sense_mode") or "?"
    orient = api_sense.get("orientation") or {}
    sensor_bits = []
    if api_sense:
        sensor_bits.append(f"mode `{sense_mode}`")
        if api_sense.get("sensor_fallback") is not None:
            sensor_bits.append(f"fallback `{api_sense.get('sensor_fallback')}`")
        if orient:
            sensor_bits.append(f"heading `{orient.get('cardinal') or '?'} {round(float(orient.get('north_heading') or orient.get('yaw') or 0), 1)}°`")
        if api_sense.get("humidity") is not None:
            sensor_bits.append(f"hum `{round(float(api_sense.get('humidity')),1)}%`")
        if api_sense.get("pressure") is not None:
            sensor_bits.append(f"press `{round(float(api_sense.get('pressure')),1)} hPa`")
    else:
        sensor_bits.append("unavailable")
    power_line = "Power: `unknown`"
    if isinstance(power, dict) and power:
        pct = power.get("percent") or power.get("battery_percent") or power.get("level")
        charging = power.get("charging") or power.get("plugged")
        model = power.get("model") or power.get("source") or "power"
        power_line = f"Power: `{model}` pct=`{pct if pct is not None else '?'}` charging=`{charging if charging is not None else '?'}`"
    lines = [
        "🍁 **MapPI3 telemetry**",
        f"Host: `{data.get('hostname') or status.get('host') or '?'}` | Mode: `{mode}` | Uptime: `{data.get('uptime') or '?'}`",
        f"Services: `{service_line}`",
        clock_line,
        gps_line(gps, privacy),
        f"System: CPU `{system.get('cpu_percent','?')}%` load `{system.get('load1','?')}` RAM `{mem.get('percent','?')}%` disk `{disk.get('percent','?')}%` temp `{temp_c if temp_c is not None else '?'}°C` throttled `{system.get('throttled','?')}`",
        power_line,
        "Sense: " + " | ".join(sensor_bits),
        f"Next hike/location: `{str(next_hike)[:120]}`",
        "Location privacy: `" + privacy + "` · exact coordinates stay hidden unless explicitly enabled.",
    ]
    if skew is not None and abs(skew) > 86400:
        lines.append("⚠️ Pi clock is unsafe for absolute schedules/cache timestamps; telemetry uses collector time for Discord freshness.")
    if not gps.get("fix"):
        lines.append("GPS note: no current fix; reporting mode/satellite state only, not a live location.")
    return "\n".join(lines)[:1900]


def post_discord_bot(token: str, channel_id: str, content: str, dry_run: bool = False):
    if dry_run:
        return {"dry_run": True, "content": content}
    payload = json.dumps({"content": content}).encode()
    req = urllib.request.Request(
        DISCORD_API + f"/channels/{channel_id}/messages",
        data=payload,
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "MapPI3-Telemetry/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode(errors="ignore") or "{}"
            return {"status": resp.status, "body": json.loads(body)}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[-800:]
        raise RuntimeError(f"Discord HTTP {e.code}: {detail}")


def atomic_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Post MapPI3 telemetry to Discord")
    ap.add_argument("--dry-run", action="store_true", help="collect and print, do not post")
    ap.add_argument("--json", action="store_true", help="print JSON result")
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--channel-id", default=None)
    ap.add_argument("--nukebox", default=os.environ.get("MAPPI3_NUKEBOX_HOST", "nukebox"))
    ap.add_argument("--pi-host", default=os.environ.get("MAPPI3_PI_HOST", "10.42.0.1"))
    ap.add_argument("--pi-user", default=os.environ.get("MAPPI3_PI_USER", "mappi3"))
    ap.add_argument("--env", action="append", default=[])
    args = ap.parse_args()

    env_paths = [pathlib.Path(p).expanduser() for p in args.env] + DEFAULT_ENV_PATHS
    env = load_env(env_paths)
    state_path = pathlib.Path(args.state).expanduser()
    result: dict[str, Any] = {"ok": False, "posted": False, "collected_at": int(time.time())}
    try:
        data = collect_via_ssh(args.nukebox, args.pi_host, args.pi_user)
        sync_enabled = (env.get("MAPPI3_TELEMETRY_SYNC_PI_CLOCK") or "1").strip().lower() not in ("0", "false", "no", "off")
        clock_sync = {"attempted": False, "reason": "disabled"}
        if sync_enabled:
            clock_sync = sync_pi_clock_if_needed(args.nukebox, args.pi_host, args.pi_user, data)
            if clock_sync.get("attempted") and clock_sync.get("ok"):
                # Re-sample after correcting the Pi clock so Discord shows the current post-sync state.
                data = collect_via_ssh(args.nukebox, args.pi_host, args.pi_user)
        message = build_message(data, env)
        result.update({"ok": True, "telemetry": data, "clock_sync": clock_sync, "message": message})
        token = env.get("DISCORD_BOT_TOKEN") or env.get("MAPPI3_DISCORD_BOT_TOKEN")
        channel_id = args.channel_id or env.get("MAPPI3_DISCORD_CHANNEL_ID") or DEFAULT_CHANNEL_ID
        if not token and not args.dry_run:
            raise RuntimeError("DISCORD_BOT_TOKEN or MAPPI3_DISCORD_BOT_TOKEN missing")
        # Suppress exact duplicate snapshots to avoid Discord spam, but always collect/cache.
        msg_hash = hashlib.sha256(message.encode()).hexdigest()
        previous = {}
        try:
            previous = json.loads(state_path.read_text())
        except Exception:
            pass
        if not args.dry_run and previous.get("last_message_hash") == msg_hash and time.time() - float(previous.get("last_post_at", 0)) < 300:
            result.update({"posted": False, "skipped": "duplicate-within-5m"})
        else:
            response = post_discord_bot(token or "", channel_id, message, dry_run=args.dry_run)
            result.update({"posted": not args.dry_run, "discord": {"status": response.get("status"), "id": safe_get(response, "body", "id")}})
        atomic_json(state_path, {"last_message_hash": msg_hash, "last_post_at": time.time(), "last_result": {k: v for k, v in result.items() if k != "telemetry"}})
    except Exception as e:
        result.update({"ok": False, "error": str(e)})
        atomic_json(state_path, result)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"MAPPI3_TELEMETRY_ERROR: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result.get("message", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
