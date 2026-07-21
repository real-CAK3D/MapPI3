#!/usr/bin/env bash
set -euo pipefail
WHISPLAY_DIR="${WHISPLAY_DIR:-/opt/whisplay/Whisplay-main}"
EXAMPLE_DIR="$WHISPLAY_DIR/example"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/opt/whisplay/backups/game-input-helper-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
for f in "$EXAMPLE_DIR/jump_game.py" "$EXAMPLE_DIR/flappy_bird.py"; do
  test -f "$f"
  cp -a "$f" "$BACKUP_DIR/$(basename "$f")"
done

cat > "$EXAMPLE_DIR/whisplay_input.py" <<'PY'
"""Shared Whisplay external-app input helper.

Normalizes button-style controls for simple games/apps:
- Whisplay/USB/Bluetooth keyboard Space
- Enter / keypad Enter
- Sense HAT joystick center button
- optional Sense HAT joystick right as select/flap/jump

The Whisplay daemon already uses the Sense HAT joystick for desktop/menu
navigation. Foreground external apps do not receive daemon menu actions, so
those apps need to read Linux input events directly. This helper keeps that
logic in one place instead of duplicating fragile listeners per game.
"""
from __future__ import annotations

import os
import select
import struct
import threading
import time
from typing import Callable, Iterable

EV_KEY = 0x01
KEY_PRESS = 1
KEY_RELEASE = 0
KEY_REPEAT = 2

KEY_ENTER = 28
KEY_SPACE = 57
KEY_KPENTER = 96
KEY_RIGHT = 106

INPUT_EVENT_FORMAT = "llHHI"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FORMAT)

DEFAULT_BUTTON_CODES = {KEY_SPACE, KEY_ENTER, KEY_KPENTER, KEY_RIGHT}


def _add_resolved(paths: list[str], path: str) -> None:
    try:
        resolved = os.path.realpath(path)
    except OSError:
        return
    if resolved and resolved not in paths:
        paths.append(resolved)


def candidate_input_paths(include_fallback: bool = True) -> list[str]:
    """Return likely keyboard/Sense HAT input event devices.

    Prefer normal keyboard symlinks and the stable Sense HAT by-path joystick
    entry. Fall back to all event devices only if no preferred device exists.
    """
    paths: list[str] = []

    by_id_dir = "/dev/input/by-id"
    try:
        for entry in sorted(os.listdir(by_id_dir)):
            if entry.endswith("-kbd"):
                _add_resolved(paths, os.path.join(by_id_dir, entry))
    except FileNotFoundError:
        pass

    by_path_dir = "/dev/input/by-path"
    try:
        for entry in sorted(os.listdir(by_path_dir)):
            lower = entry.lower()
            if "sensehat" in lower and "joystick" in lower and lower.endswith("-event"):
                _add_resolved(paths, os.path.join(by_path_dir, entry))
    except FileNotFoundError:
        pass

    if paths or not include_fallback:
        return paths

    try:
        for entry in sorted(os.listdir("/dev/input")):
            if entry.startswith("event"):
                _add_resolved(paths, os.path.join("/dev/input", entry))
    except FileNotFoundError:
        pass
    return paths


def start_button_listener(
    on_press: Callable[[], None],
    on_release: Callable[[], None],
    *,
    button_codes: Iterable[int] | None = None,
    include_fallback: bool = True,
    rescan_interval: float = 2.0,
) -> threading.Thread:
    """Start a daemon thread that turns selected input key events into button callbacks."""
    codes = set(DEFAULT_BUTTON_CODES if button_codes is None else button_codes)

    def _loop() -> None:
        fds: dict[int, str] = {}
        last_scan = 0.0

        def close_fd(fd: int) -> None:
            try:
                os.close(fd)
            except OSError:
                pass
            fds.pop(fd, None)

        def close_all() -> None:
            for fd in list(fds):
                close_fd(fd)

        while True:
            now = time.monotonic()
            if now - last_scan >= rescan_interval:
                last_scan = now
                paths = set(candidate_input_paths(include_fallback=include_fallback))
                stale = [fd for fd, path in fds.items() if path not in paths]
                for fd in stale:
                    close_fd(fd)
                open_paths = set(fds.values())
                for path in paths - open_paths:
                    try:
                        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    except OSError:
                        continue
                    fds[fd] = path

            if not fds:
                time.sleep(1.0)
                continue

            try:
                ready, _, _ = select.select(list(fds), [], [], 0.02)
            except (ValueError, OSError):
                close_all()
                continue

            for fd in ready:
                try:
                    data = os.read(fd, INPUT_EVENT_SIZE * 32)
                except OSError:
                    close_fd(fd)
                    continue
                offset = 0
                while offset + INPUT_EVENT_SIZE <= len(data):
                    _, _, event_type, code, value = struct.unpack(
                        INPUT_EVENT_FORMAT, data[offset : offset + INPUT_EVENT_SIZE]
                    )
                    if event_type == EV_KEY and code in codes:
                        if value == KEY_PRESS:
                            on_press()
                        elif value == KEY_RELEASE:
                            on_release()
                    offset += INPUT_EVENT_SIZE

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread
PY
chmod 0644 "$EXAMPLE_DIR/whisplay_input.py"

python3 - <<'PY'
from pathlib import Path
base = Path('/opt/whisplay/Whisplay-main/example')
files = [base/'jump_game.py', base/'flappy_bird.py']
old = '''import select\n\nEV_KEY = 0x01\nKEY_SPACE = 57\n_INPUT_EVENT_FORMAT = "llHHI"\n_INPUT_EVENT_SIZE = struct.calcsize(_INPUT_EVENT_FORMAT)\n\n\ndef _start_keyboard_listener(on_press, on_release):\n    """Listen for space key on external keyboards, trigger callbacks."""\n    def _loop():\n        import os as _os\n        fds: dict[int, str] = {}\n        last_scan = 0.0\n        while True:\n            now = time.monotonic()\n            if now - last_scan >= 2.0:\n                last_scan = now\n                paths = set()\n                by_id = "/dev/input/by-id"\n                try:\n                    for e in _os.listdir(by_id):\n                        if e.endswith("-kbd"):\n                            paths.add(_os.path.realpath(_os.path.join(by_id, e)))\n                except FileNotFoundError:\n                    pass\n                if not paths:\n                    try:\n                        paths = {\n                            _os.path.join("/dev/input", e)\n                            for e in _os.listdir("/dev/input")\n                            if e.startswith("event")\n                        }\n                    except FileNotFoundError:\n                        pass\n                stale = [fd for fd, p in fds.items() if p not in paths]\n                for fd in stale:\n                    try:\n                        _os.close(fd)\n                    except OSError:\n                        pass\n                    del fds[fd]\n                for p in paths - set(fds.values()):\n                    try:\n                        fds[_os.open(p, _os.O_RDONLY | _os.O_NONBLOCK)] = p\n                    except OSError:\n                        pass\n            if not fds:\n                time.sleep(1)\n                continue\n            try:\n                ready, _, _ = select.select(list(fds), [], [], 0.02)\n            except (ValueError, OSError):\n                for fd in list(fds):\n                    try:\n                        _os.close(fd)\n                    except OSError:\n                        pass\n                fds.clear()\n                continue\n            for fd in ready:\n                try:\n                    data = _os.read(fd, _INPUT_EVENT_SIZE * 16)\n                except OSError:\n                    try:\n                        _os.close(fd)\n                    except OSError:\n                        pass\n                    fds.pop(fd, None)\n                    continue\n                off = 0\n                while off + _INPUT_EVENT_SIZE <= len(data):\n                    _, _, ev_type, code, value = struct.unpack(\n                        _INPUT_EVENT_FORMAT, data[off:off + _INPUT_EVENT_SIZE]\n                    )\n                    if ev_type == EV_KEY and code == KEY_SPACE:\n                        if value == 1:\n                            on_press()\n                        elif value == 0:\n                            on_release()\n                    off += _INPUT_EVENT_SIZE\n\n    t = threading.Thread(target=_loop, daemon=True)\n    t.start()\n    return t\n'''
new = '''from whisplay_input import start_button_listener\n\n\ndef _start_keyboard_listener(on_press, on_release):\n    """Listen for Space/Enter/Sense HAT joystick button via shared helper."""\n    return start_button_listener(on_press, on_release)\n'''
for path in files:
    text = path.read_text()
    if 'from whisplay_input import start_button_listener' in text:
        continue
    if old not in text:
        raise SystemExit(f'ERROR: expected legacy listener block not found in {path}')
    text = text.replace(old, new)
    path.write_text(text)
PY

python3 -m py_compile "$EXAMPLE_DIR/whisplay_input.py" "$EXAMPLE_DIR/jump_game.py" "$EXAMPLE_DIR/flappy_bird.py"
echo "WHISPLAY_GAME_INPUT_HELPER_INSTALL=PASS backup=$BACKUP_DIR"
