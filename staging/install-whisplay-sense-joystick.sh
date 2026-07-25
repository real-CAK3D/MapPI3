#!/usr/bin/env bash
set -euo pipefail

TS="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET=""
for p in \
  /opt/whisplay/Whisplay-main/daemon/internal_apps/keyboard.py \
  /opt/whisplay/daemon/internal_apps/keyboard.py \
  /usr/local/share/whisplay/daemon/internal_apps/keyboard.py \
  /home/mappi3/Whisplay/daemon/internal_apps/keyboard.py \
  /home/pi/Whisplay/daemon/internal_apps/keyboard.py
 do
  if [ -f "$p" ]; then TARGET="$p"; break; fi
done

if [ -z "$TARGET" ]; then
  echo "ERROR: could not find Whisplay daemon internal_apps/keyboard.py" >&2
  exit 1
fi

BACKUP_DIR="/opt/mappi3/backups/whisplay-sense-joystick-${TS}"
sudo mkdir -p "$BACKUP_DIR"
sudo cp -a "$TARGET" "$BACKUP_DIR/keyboard.py.before"

TMP="$(mktemp)"
python3 - "$TARGET" > "$TMP" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
text = text.replace(
'''KEY_SPACE = 57
KEY_UP = 103
KEY_DOWN = 108
INPUT_EVENT_FORMAT = "llHHI"
''',
'''KEY_SPACE = 57
KEY_UP = 103
KEY_DOWN = 108
KEY_LEFT = 105
KEY_RIGHT = 106
INPUT_EVENT_FORMAT = "llHHI"
''')
old = '''    def _candidate_paths(self) -> list[str]:
        paths = []
        by_id_dir = "/dev/input/by-id"
        try:
            for entry in sorted(os.listdir(by_id_dir)):
                if not entry.endswith("-kbd"):
                    continue
                full_path = os.path.join(by_id_dir, entry)
                try:
                    paths.append(os.path.realpath(full_path))
                except OSError:
                    continue
        except FileNotFoundError:
            pass
        if paths:
            return paths
        try:
            return sorted(
                os.path.join("/dev/input", entry)
                for entry in os.listdir("/dev/input")
                if entry.startswith("event")
            )
        except FileNotFoundError:
            return []
'''
new = '''    def _candidate_paths(self) -> list[str]:
        paths = []

        def add_path(path: str):
            try:
                resolved = os.path.realpath(path)
            except OSError:
                return
            if resolved and resolved not in paths:
                paths.append(resolved)

        by_id_dir = "/dev/input/by-id"
        try:
            for entry in sorted(os.listdir(by_id_dir)):
                if entry.endswith("-kbd"):
                    add_path(os.path.join(by_id_dir, entry))
        except FileNotFoundError:
            pass

        # The Sense HAT joystick is not exposed as a normal keyboard, but it emits
        # standard Linux key events: up/down/left/right/enter. Always include the
        # stable by-path joystick device so it can steer the Whisplay desktop even
        # when a USB/Bluetooth keyboard is also present.
        by_path_dir = "/dev/input/by-path"
        try:
            for entry in sorted(os.listdir(by_path_dir)):
                lower = entry.lower()
                if "sensehat" in lower and "joystick" in lower and lower.endswith("-event"):
                    add_path(os.path.join(by_path_dir, entry))
        except FileNotFoundError:
            pass

        if paths:
            return paths
        try:
            for entry in sorted(os.listdir("/dev/input")):
                if entry.startswith("event"):
                    add_path(os.path.join("/dev/input", entry))
            return paths
        except FileNotFoundError:
            return []
'''
if old not in text and '"sensehat" in lower and "joystick" in lower' not in text:
    raise SystemExit('ERROR: candidate path block did not match expected Whisplay keyboard.py')
text = text.replace(old, new)
old = '''        if code == KEY_UP:
            self._callback("up")
            return
        if code == KEY_DOWN:
            self._callback("down")
            return
        if code == KEY_ENTER:
            self._callback("submit")
            return
'''
new = '''        if code == KEY_UP:
            self._callback("up")
            return
        if code == KEY_DOWN:
            self._callback("down")
            return
        if code == KEY_LEFT:
            # Sense HAT joystick left acts like Escape/back for Whisplay.
            self._callback("cancel")
            return
        if code == KEY_RIGHT:
            # Sense HAT joystick right is an ergonomic select/launch action.
            self._callback("submit")
            return
        if code == KEY_ENTER:
            self._callback("submit")
            return
'''
if old not in text and 'KEY_LEFT' not in text and 'Sense HAT joystick left acts like Escape' not in text:
    raise SystemExit('ERROR: key mapping block did not match expected Whisplay keyboard.py')
text = text.replace(old, new)
print(text, end='')
PY

sudo cp "$TMP" "$TARGET"
rm -f "$TMP"
sudo python3 -m py_compile "$TARGET"

# Restart Whisplay daemon so its ExternalKeyboardReader rescans the Sense HAT stick.
sudo systemctl restart whisplay-daemon.service
systemctl is-active whisplay-daemon.service
python3 - <<'PY'
import socket, time
last = None
for attempt in range(1, 13):
    for sock in ['/run/whisplay/daemon.sock','/tmp/whisplay-daemon.sock','/var/run/whisplay/daemon.sock']:
        try:
            s=socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect(sock)
            s.sendall(b'{"version":1,"cmd":"health.ping","payload":{}}\n')
            print('WHISPLAY_HEALTH', attempt, sock, s.recv(4096).decode().strip())
            s.close(); raise SystemExit(0)
        except Exception as e:
            last = (sock, repr(e))
    time.sleep(1)
raise SystemExit(f'ERROR: Whisplay socket health.ping failed after retries: {last}')
PY
printf 'BACKUP_DIR=%s\n' "$BACKUP_DIR"
printf 'TARGET=%s\n' "$TARGET"
printf 'SENSE_JOYSTICK_MAPPING=up/down scroll, right/center select, left back/cancel\n'
