#!/usr/bin/env bash
set -euo pipefail
SSID="MapPI3"
PASS="Adventure"
STATE=/var/lib/mappi3/state.json
LOG=/var/log/mappi3-hotspot.log
CONN="MapPI3-hotspot"
mkdir -p /var/lib/mappi3
exec >>"$LOG" 2>&1
log(){ echo "[$(date -Is)] $*"; }
hotspot_enabled(){ python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/var/lib/mappi3/state.json')
try: s=json.loads(p.read_text())
except Exception: s={}
print('1' if s.get('hotspot_enabled', True) else '0')
PY
}
wifi_dev(){ nmcli -t -f DEVICE,TYPE device status 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}'; }
hotspot_healthy(){
  local dev="${1:-wlan0}"
  nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | grep -Fxq "$CONN:$dev" || return 1
  ip -4 addr show "$dev" 2>/dev/null | grep -q '10\.42\.0\.1/24' || return 1
  ss -ltn 2>/dev/null | grep -q ':5050 ' || return 1
  ss -ltn 2>/dev/null | grep -q ':80 ' || return 1
  return 0
}
ensure_profile(){
  local dev="$1"
  if ! nmcli -t -f NAME connection show | grep -Fxq "$CONN"; then
    nmcli connection add type wifi ifname "$dev" con-name "$CONN" autoconnect yes ssid "$SSID"
  fi
  nmcli connection modify "$CONN" \
    connection.autoconnect yes \
    connection.autoconnect-priority 999 \
    connection.autoconnect-retries 0 \
    connection.wait-device-timeout 0 \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 1 \
    802-11-wireless.ssid "$SSID" \
    802-11-wireless.powersave 2 \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASS" \
    ipv4.method shared \
    ipv4.addresses 10.42.0.1/24 \
    ipv4.never-default yes \
    ipv6.method ignore
}
ensure_hotspot(){
  rfkill unblock wifi || true
  command -v raspi-config >/dev/null 2>&1 && raspi-config nonint do_wifi_country US || true
  if [ "$(hotspot_enabled)" != "1" ]; then nmcli connection down "$CONN" || true; log "hotspot disabled by state"; return 0; fi
  if ! command -v nmcli >/dev/null 2>&1; then log "ERROR nmcli missing"; return 1; fi
  systemctl start NetworkManager || true
  nmcli radio wifi on || true
  local dev=""
  for i in $(seq 1 45); do
    dev="$(wifi_dev || true)"
    [ -n "$dev" ] && break
    log "waiting for Wi-Fi device ($i/45)"
    sleep 2
  done
  if [ -z "$dev" ]; then log "ERROR no Wi-Fi device found"; nmcli device status || true; return 1; fi
  ensure_profile "$dev"
  if hotspot_healthy "$dev"; then
    log "hotspot healthy on $dev; leaving active connection untouched"
    return 0
  fi
  log "hotspot unhealthy on $dev; activating $CONN"
  nmcli connection up "$CONN" || nmcli device wifi hotspot ifname "$dev" ssid "$SSID" password "$PASS" con-name "$CONN"
  systemctl restart mappi3-captive.service || true
  nmcli -f NAME,DEVICE,TYPE,STATE connection show --active || true
  ip addr show "$dev" || true
  log "hotspot recovery attempt complete"
}
if [ "${1:-}" = "watch" ]; then
  while true; do ensure_hotspot || true; sleep 30; done
else
  ensure_hotspot
fi
