#!/usr/bin/env bash
set -euo pipefail
WHISPLAY_DIR="${WHISPLAY_DIR:-/opt/whisplay/Whisplay-main}"
APP_DIR="${APP_DIR:-/home/mappi3/.whisplay-daemon/app}"
EXAMPLE_DIR="$WHISPLAY_DIR/example"

for f in \
  "$EXAMPLE_DIR/mappi3_whisplay_common.py" \
  "$EXAMPLE_DIR/mappi3_whisplay_dashboard.py" \
  "$EXAMPLE_DIR/mappi3_whisplay_ai_chat.py" \
  "$APP_DIR/whisplay-mappi3-dashboard.json" \
  "$APP_DIR/whisplay-mappi3-ai-chat.json" \
  /usr/local/bin/mappi3-bt-pan-client.sh \
  /etc/systemd/system/mappi3-bt-pan-client.service; do
  test -f "$f" || { echo "missing=$f"; exit 1; }
done

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import json, pathlib
base=pathlib.Path('/opt/whisplay/Whisplay-main/example')
for script in ['mappi3_whisplay_common.py','mappi3_whisplay_dashboard.py','mappi3_whisplay_ai_chat.py']:
    compile((base/script).read_text(encoding='utf-8'), str(base/script), 'exec')
    print(script + '=COMPILE_PASS')
appdir=pathlib.Path('/home/mappi3/.whisplay-daemon/app')
for name in ['whisplay-mappi3-dashboard.json','whisplay-mappi3-ai-chat.json']:
    data=json.loads((appdir/name).read_text())
    assert data['app_id'].startswith('whisplay-mappi3')
    assert data.get('launch_command')
    print(name + '=JSON_PASS')
PY

python3 - <<'PY'
import json, os, socket, time
sock='/tmp/whisplay-daemon.sock'
for _ in range(20):
    if os.path.exists(sock):
        break
    time.sleep(0.5)
assert os.path.exists(sock), 'daemon socket missing'
def req(cmd, payload=None):
    s=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(5); s.connect(sock)
    s.sendall((json.dumps({'version':1,'cmd':cmd,'payload':payload or {}})+'\n').encode())
    data=s.recv(65535).decode(errors='replace').strip(); s.close(); print(cmd, data); return json.loads(data)
health=req('health.ping')
assert health.get('ok')
apps=req('app.list')
ids={a['app_id'] for a in apps['payload']['apps']}
assert 'whisplay-mappi3-dashboard' in ids, ids
assert 'whisplay-mappi3-ai-chat' in ids, ids
print('WHISPLAY_MAPPI3_APPS_REGISTERED=PASS')
PY

if systemctl is-active --quiet whisplay-daemon.service; then
  echo WHISPLAY_DAEMON_ACTIVE=PASS
else
  echo WHISPLAY_DAEMON_ACTIVE=FAIL
  exit 1
fi

if grep -qE '^dtoverlay=disable-bt' /boot/firmware/config.txt; then
  echo BLUETOOTH_STILL_DISABLED=YES
elif grep -qE '^# Maple enabled BT PAN .*dtoverlay=disable-bt' /boot/firmware/config.txt; then
  echo BLUETOOTH_CONFIG_ENABLED=YES
else
  echo BLUETOOTH_CONFIG_ENABLED=YES
fi

bt_info="$(bluetoothctl show 2>/dev/null || true)"
echo "$bt_info" | grep -q 'Controller ' && echo BLUETOOTH_CONTROLLER_PRESENT=YES || echo BLUETOOTH_CONTROLLER_PRESENT=NO
echo "$bt_info" | grep -q 'Powered: yes' && echo BLUETOOTH_POWERED=YES || echo BLUETOOTH_POWERED=NO
if [ -d /sys/class/rfkill ]; then
  for soft in /sys/class/rfkill/rfkill*/soft; do
    [ -e "$soft" ] || continue
    type_file="$(dirname "$soft")/type"
    if grep -qx bluetooth "$type_file" 2>/dev/null; then
      printf 'BLUETOOTH_RFKILL_SOFT=%s\n' "$(cat "$soft")"
    fi
  done
fi

systemctl is-enabled mappi3-bt-pan-client.service >/dev/null 2>&1 && echo BT_PAN_SERVICE_ENABLED=PASS || echo BT_PAN_SERVICE_ENABLED=NOT_ENABLED

echo MAPPI3_WHISPLAY_APPS_BT_VERIFY=PASS
