#!/usr/bin/env bash
set -euo pipefail
WHISPLAY_DIR="${WHISPLAY_DIR:-/opt/whisplay/Whisplay-main}"
EXAMPLE_DIR="$WHISPLAY_DIR/example"
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import importlib.util, pathlib, sys
base = pathlib.Path('/opt/whisplay/Whisplay-main/example')
helper = base / 'whisplay_input.py'
jump = base / 'jump_game.py'
flappy = base / 'flappy_bird.py'
for path in (helper, jump, flappy):
    if not path.exists():
        raise SystemExit(f'MISSING {path}')
text = helper.read_text()
checks = {
    'shared_helper_exists': helper.exists(),
    'sensehat_path': '"sensehat" in lower and "joystick" in lower' in text,
    'space_supported': 'KEY_SPACE = 57' in text,
    'enter_supported': 'KEY_ENTER = 28' in text,
    'kpenter_supported': 'KEY_KPENTER = 96' in text,
    'right_supported': 'KEY_RIGHT = 106' in text,
    'default_codes': 'DEFAULT_BUTTON_CODES = {KEY_SPACE, KEY_ENTER, KEY_KPENTER, KEY_RIGHT}' in text,
}
for game in (jump, flappy):
    gtext = game.read_text()
    checks[f'{game.name}_uses_helper'] = 'from whisplay_input import start_button_listener' in gtext
    checks[f'{game.name}_legacy_space_only_removed'] = 'code == KEY_SPACE' not in gtext
sys.path.insert(0, str(base))
spec = importlib.util.spec_from_file_location('whisplay_input_verify', helper)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
paths = mod.candidate_input_paths(include_fallback=False)
checks['candidate_paths_callable'] = isinstance(paths, list)
checks['default_button_codes_runtime'] = {57, 28, 96, 106}.issubset(set(mod.DEFAULT_BUTTON_CODES))
failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f'{name}={ok}')
if failed:
    raise SystemExit('FAILED ' + ','.join(failed))
print('WHISPLAY_GAME_INPUT_HELPER_VERIFY=PASS')
PY
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import pathlib
for p in ['/opt/whisplay/Whisplay-main/example/whisplay_input.py','/opt/whisplay/Whisplay-main/example/jump_game.py','/opt/whisplay/Whisplay-main/example/flappy_bird.py']:
    text = pathlib.Path(p).read_text(encoding='utf-8')
    compile(text, p, 'exec')
    print(f'{p}=COMPILE_PASS')
PY
systemctl is-active --quiet whisplay-daemon.service && echo 'WHISPLAY_DAEMON_ACTIVE=PASS' || echo 'WHISPLAY_DAEMON_ACTIVE=FAIL'
