#!/usr/bin/env bash
set -euo pipefail
HOSTNAME_TARGET="MapPI3"
BOOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_TAR="$BOOT_DIR/mappi3-dist.tar.gz"

log(){ echo "[MapPI3 firstboot] $*"; }
if [ "$(id -u)" -ne 0 ]; then echo "Run as root: sudo bash $0"; exit 1; fi
log "setting hostname $HOSTNAME_TARGET"
hostnamectl set-hostname "$HOSTNAME_TARGET" || true

log "enabling USB gadget overlay"
CONFIG="/boot/firmware/config.txt"; [ -f "$CONFIG" ] || CONFIG="/boot/config.txt"
CMDLINE="/boot/firmware/cmdline.txt"; [ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"
grep -q '^dtoverlay=dwc2' "$CONFIG" || echo 'dtoverlay=dwc2' >> "$CONFIG"
if ! grep -q 'modules-load=dwc2,g_ether' "$CMDLINE"; then
  sed -i 's/rootwait/rootwait modules-load=dwc2,g_ether/' "$CMDLINE"
fi

log "installing packages"
timeout 45 apt-get update || log 'apt update failed; continuing with built-in packages and retry later from app Settings'
timeout 180 env DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-sense-hat sense-hat python3-pygame python3-dbus python3-evdev i2c-tools gpsd gpsd-clients network-manager git curl ca-certificates || log 'package install failed; MapPI3 web installs anyway, Sense HAT/GPS/Whisplay game helpers can be installed later'
systemctl enable ssh || true
systemctl enable gpsd || true

log "installing MapPI3 app"
install -d /opt/mappi3/app /var/lib/mappi3 /usr/local/bin
if [ -f "$APP_TAR" ]; then
  rm -rf /opt/mappi3/app/*
  tar -xzf "$APP_TAR" -C /opt/mappi3/app --strip-components=1
else
  log "WARNING: $APP_TAR missing; app files not installed"
fi
install -m 0755 "$BOOT_DIR/mappi3-agent.py" /usr/local/bin/mappi3-agent.py
install -m 0755 "$BOOT_DIR/mappi3-hotspot.sh" /usr/local/bin/mappi3-hotspot.sh
if [ -f "$BOOT_DIR/mappi3-home-wifi.json" ]; then
  log "installing saved home Wi-Fi config for first-boot LAN/SSH access"
  install -m 0600 "$BOOT_DIR/mappi3-home-wifi.json" /var/lib/mappi3/home-wifi.json
  python3 - <<'PY'
import json, pathlib, time
state_path=pathlib.Path('/var/lib/mappi3/state.json')
try: state=json.loads(state_path.read_text())
except Exception: state={}
try: cfg=json.loads(pathlib.Path('/var/lib/mappi3/home-wifi.json').read_text())
except Exception: cfg={}
if cfg.get('ssid'):
    state['home_wifi_ssid']=cfg.get('ssid')
    state['home_wifi_saved_at']=time.time()
    state['hotspot_enabled']=cfg.get('hotspot_fallback', True)
state_path.write_text(json.dumps(state, indent=2))
PY
fi
cat >/usr/local/bin/mappi3-update-app.sh <<'UPD'
#!/usr/bin/env bash
set -euo pipefail
if [ -n "${MAPPI3_UPDATE_SRC:-}" ]; then SRC="$MAPPI3_UPDATE_SRC"; elif [ -f /boot/firmware/mappi3-dist.tar.gz ]; then SRC=/boot/firmware/mappi3-dist.tar.gz; elif [ -f /boot/mappi3-dist.tar.gz ]; then SRC=/boot/mappi3-dist.tar.gz; else echo "No mappi3-dist.tar.gz source found"; exit 1; fi
STAMP=/var/lib/mappi3/app-bundle.sha256
NEW_SHA="$(sha256sum "$SRC" | awk '{print $1}')"
if [ "${1:-}" = "--if-newer" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null || true)" = "$NEW_SHA" ]; then echo "MapPI3 app bundle already current"; exit 0; fi
rm -rf /opt/mappi3/app/*
tar -xzf "$SRC" -C /opt/mappi3/app --strip-components=1
install -d /var/lib/mappi3
printf '%s\n' "$NEW_SHA" > "$STAMP"
systemctl restart mappi3-web.service
UPD
chmod +x /usr/local/bin/mappi3-update-app.sh

cat >/usr/local/bin/mappi3-hourly-online-refresh.sh <<'REFRESH'
#!/usr/bin/env bash
set -euo pipefail
LOG=/var/lib/mappi3/hourly-online-refresh.log
install -d /var/lib/mappi3
exec >>"$LOG" 2>&1
echo "=== hourly refresh $(date -Is) ==="
if ! ip route | grep -q '^default '; then echo 'offline: no default route; keeping cached data'; exit 0; fi
curl -fsS --max-time 45 -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:5050/api/command/hourly-online-refresh || true
echo "=== done $(date -Is) ==="
REFRESH
chmod +x /usr/local/bin/mappi3-hourly-online-refresh.sh

cat >/etc/systemd/system/mappi3-web.service <<'EOF'
[Unit]
Description=MapPI3 local web app and command API
After=multi-user.target

[Service]
Type=simple
Environment=MAPPI3_PORT=5050
ExecStart=/usr/local/bin/mappi3-agent.py
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/mappi3-hotspot.service <<'EOF'
[Unit]
Description=MapPI3 Wi-Fi hotspot/access fallback
After=NetworkManager.service
Wants=NetworkManager.service

[Service]
Type=simple
ExecStart=/usr/local/bin/mappi3-hotspot.sh watch
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/mappi3-hourly-online-refresh.service <<'EOF'
[Unit]
Description=MapPI3 safe hourly online refresh
After=network-online.target mappi3-web.service
Wants=mappi3-web.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mappi3-hourly-online-refresh.sh
EOF

cat >/etc/systemd/system/mappi3-hourly-online-refresh.timer <<'EOF'
[Unit]
Description=Run MapPI3 online refresh hourly when network is available

[Timer]
OnBootSec=7min
OnUnitActiveSec=1h
AccuracySec=3min
Persistent=true

[Install]
WantedBy=timers.target
EOF

log "configuring boot splash text"
cat >/etc/motd <<'EOF'
MapPI3 Trail OS
- Web: http://MapPI3.local:5050 or http://10.42.0.1:5050 on hotspot
- Hostname: MapPI3
- GPS: GT-U7 expected at /dev/ttyACM0
- Sense HAT: enabled target
EOF

systemctl daemon-reload
systemctl disable mappi3-firstboot.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/mappi3-firstboot.service 2>/dev/null || true
systemctl enable mappi3-web.service mappi3-hotspot.service mappi3-hourly-online-refresh.timer
systemctl restart mappi3-hotspot.service || true
systemctl restart mappi3-hourly-online-refresh.timer || true
systemctl restart mappi3-web.service
log "complete. Browse to http://MapPI3.local:5050 after reboot. Reboot recommended for USB gadget mode."
