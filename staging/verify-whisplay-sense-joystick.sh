#!/usr/bin/env bash
set -euo pipefail
echo SERVICE
systemctl is-active whisplay-daemon.service mappi3-web.service || true
echo PATCH
python3 - <<'PY'
from pathlib import Path
candidates = [
    Path('/opt/whisplay/Whisplay-main/daemon/internal_apps/keyboard.py'),
    Path('/opt/whisplay/daemon/internal_apps/keyboard.py'),
    Path('/usr/local/share/whisplay/daemon/internal_apps/keyboard.py'),
    Path('/home/mappi3/Whisplay/daemon/internal_apps/keyboard.py'),
    Path('/home/pi/Whisplay/daemon/internal_apps/keyboard.py'),
]
p = next((x for x in candidates if x.exists()), None)
if p is None:
    raise SystemExit('FAIL:no Whisplay keyboard.py found in expected paths')
text=p.read_text(errors='ignore')
checks={
 'target_found': True,
 'KEY_LEFT': 'KEY_LEFT = 105' in text,
 'KEY_RIGHT': 'KEY_RIGHT = 106' in text,
 'sensehat_path': '"sensehat" in lower and "joystick" in lower' in text,
 'left_cancel': 'Sense HAT joystick left acts like Escape/back' in text and 'self._callback("cancel")' in text,
 'right_submit': 'Sense HAT joystick right is an ergonomic select/launch action' in text and 'self._callback("submit")' in text,
}
print(f'TARGET={p}')
print(','.join(f'{k}:{"PASS" if v else "FAIL"}' for k,v in checks.items()))
if not all(checks.values()):
    raise SystemExit(3)
PY
TARGET="$(python3 - <<'PY'
from pathlib import Path
for p in [
    Path('/opt/whisplay/Whisplay-main/daemon/internal_apps/keyboard.py'),
    Path('/opt/whisplay/daemon/internal_apps/keyboard.py'),
    Path('/usr/local/share/whisplay/daemon/internal_apps/keyboard.py'),
    Path('/home/mappi3/Whisplay/daemon/internal_apps/keyboard.py'),
    Path('/home/pi/Whisplay/daemon/internal_apps/keyboard.py'),
]:
    if p.exists():
        print(p)
        break
PY
)"
if [ -n "$TARGET" ]; then python3 -m py_compile "$TARGET"; fi
echo SOCKETS
ls -l /tmp/whisplay-daemon.sock /run/whisplay/daemon.sock /var/run/whisplay/daemon.sock 2>/dev/null || true
echo HEALTH
python3 - <<'PY'
import socket, time
last=None
for attempt in range(1, 10):
    for sock in ['/tmp/whisplay-daemon.sock','/run/whisplay/daemon.sock','/var/run/whisplay/daemon.sock']:
        try:
            s=socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect(sock)
            s.sendall(b'{"version":1,"cmd":"health.ping","payload":{}}\n')
            print('OK', attempt, sock, s.recv(4096).decode().strip())
            s.close(); raise SystemExit(0)
        except Exception as e:
            last=(sock,repr(e))
    time.sleep(1)
print('FAIL', last)
raise SystemExit(2)
PY
echo INPUT_PATHS
ls -l /dev/input/by-path 2>/dev/null | sed -n '1,80p' || true
echo JOURNAL_TAIL
journalctl -u whisplay-daemon.service --no-pager -n 80 || true
