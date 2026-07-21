#!/usr/bin/env bash
set -euo pipefail

# MapPI3 phone Bluetooth PAN tether helper.
# Purpose: use phone cellular internet over Bluetooth (bnep0) while keeping
# MapPI3 Wi-Fi hotspot on wlan0/10.42.0.1.
# Safe default: preflight only unless --prepare/--connect/--disconnect is chosen.

ACTION="status"
PHONE_MAC=""
SHARE_CLIENTS="0"
for arg in "$@"; do
  case "$arg" in
    --status) ACTION="status" ;;
    --prepare) ACTION="prepare" ;;
    --connect) ACTION="connect" ;;
    --disconnect) ACTION="disconnect" ;;
    --share-clients) SHARE_CLIENTS="1" ;;
    --phone=*) PHONE_MAC="${arg#--phone=}" ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING:$1"; return 1; }; }
mac_ok() { [[ "$1" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/opt/mappi3/backups/bluetooth-pan-$TS"
make_backup() {
  sudo install -d -m 0755 "$BACKUP"
  (systemctl is-enabled bluetooth.service 2>&1 || true) | sudo tee "$BACKUP/bluetooth.service.enabled.before" >/dev/null
  (systemctl is-active bluetooth.service 2>&1 || true) | sudo tee "$BACKUP/bluetooth.service.active.before" >/dev/null
  (nmcli -t -f NAME,UUID,TYPE,DEVICE,AUTOCONNECT con show 2>&1 || true) | sudo tee "$BACKUP/nm-connections.before" >/dev/null
  (ip route 2>&1 || true) | sudo tee "$BACKUP/ip-route.before" >/dev/null
  (sysctl net.ipv4.ip_forward 2>&1 || true) | sudo tee "$BACKUP/ip-forward.before" >/dev/null
  echo "BACKUP=$BACKUP"
}

status() {
  echo "== services =="
  systemctl is-active bluetooth.service NetworkManager.service 2>&1 || true
  echo "== boot bluetooth/UART config =="
  grep -nEi 'disable-bt|dtoverlay=.*bt|bluetooth|uart|serial|miniuart|pi3' /boot/firmware/config.txt /boot/config.txt 2>/dev/null || true
  echo "== bluetooth adapter =="
  timeout 8 bluetoothctl show 2>&1 || true
  echo "== bnep/network =="
  ip -br addr | grep -E '^bnep[0-9]+' || true
  nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device 2>&1 || true
  ip route || true
  echo "== hotspot preserved =="
  nmcli -t -f NAME,TYPE,DEVICE connection show --active | grep -E '^MapPI3-hotspot:.*:wlan0' || true
}

prepare() {
  need bluetoothctl; need nmcli; need ip
  make_backup
  sudo systemctl enable --now bluetooth.service
  sudo modprobe bnep || true
  bluetoothctl power on || true
  status
  if bluetoothctl show 2>&1 | grep -q 'No default controller'; then
    echo "BLOCKED: Bluetooth service is running but no controller exists. On this Pi, dtoverlay=disable-bt likely reserves the UART for GPS. Use a USB Bluetooth dongle, or redesign GPS/UART before using built-in Bluetooth." >&2
    exit 3
  fi
}

connect_pan() {
  [[ -n "$PHONE_MAC" ]] || { echo "--phone=AA:BB:CC:DD:EE:FF required" >&2; exit 2; }
  mac_ok "$PHONE_MAC" || { echo "Invalid MAC: $PHONE_MAC" >&2; exit 2; }
  prepare
  bluetoothctl trust "$PHONE_MAC" || true
  nmcli device connect "$PHONE_MAC" || true
  sleep 3
  if ! ip -br addr | grep -qE '^bnep[0-9]+'; then
    CON="MapPI3-phone-pan-${PHONE_MAC//:/}"
    CON="${CON:0:48}"
    nmcli connection delete "$CON" >/dev/null 2>&1 || true
    nmcli connection add type bluetooth con-name "$CON" ifname "$PHONE_MAC" bluetooth.type panu ipv4.method auto connection.autoconnect no
    nmcli connection up "$CON" || true
  fi
  if [[ "$SHARE_CLIENTS" == "1" ]]; then
    # Keep the hotspot as shared/NAT mode and never use wlan0 as default upstream.
    nmcli connection modify MapPI3-hotspot ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv4.never-default yes connection.autoconnect yes || true
  fi
  status
  curl -fsS --max-time 8 https://connectivitycheck.gstatic.com/generate_204 >/dev/null && echo "INTERNET_CHECK=PASS" || echo "INTERNET_CHECK=FAIL"
}

disconnect_pan() {
  make_backup
  if [[ -n "$PHONE_MAC" ]] && mac_ok "$PHONE_MAC"; then bluetoothctl disconnect "$PHONE_MAC" || true; fi
  while IFS=: read -r name type _; do
    [[ "$type" == "bluetooth" || "$name" == MapPI3-phone-pan* ]] || continue
    nmcli connection down "$name" || true
  done < <(nmcli -t -f NAME,TYPE connection show 2>/dev/null || true)
  status
}

case "$ACTION" in
  status) status ;;
  prepare) prepare ;;
  connect) connect_pan ;;
  disconnect) disconnect_pan ;;
esac
