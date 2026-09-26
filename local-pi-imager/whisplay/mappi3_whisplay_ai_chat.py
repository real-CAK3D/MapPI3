#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from urllib import request
from mappi3_whisplay_common import *

running = True
idx = 0
busy = False
last_answer = 'Press to ask home AI.'
PROMPTS = [
    ('Trail check', 'Give a very short MapPI3 trail readiness checklist. Mention that MapPI3 assists but does not replace real navigation/emergency tools.'),
    ('Hotspot help', 'In 3 short bullets, explain how MapPI3 can use hotspot at home and offline mode on trail.'),
    ('Battery saver', 'Give 4 concise low-power tips for a Raspberry Pi trail device with screen, GPS, and hotspot.'),
    ('Whisplay idea', 'Suggest one tiny Whisplay screen layout for MapPI3: face, GPS, network, and safety.'),
]

def ollama_config():
    env = load_env('/etc/mappi3/whisplay-ai.env')
    host = os.environ.get('OLLAMA_HOST') or env.get('OLLAMA_HOST') or 'http://10.42.0.38:11434'
    model = os.environ.get('OLLAMA_MODEL') or env.get('OLLAMA_MODEL') or ''
    timeout = float(os.environ.get('OLLAMA_TIMEOUT') or env.get('OLLAMA_TIMEOUT') or 35)
    return host.rstrip('/'), model, timeout

def pick_model(host, timeout=4):
    try:
        data = http_json(host + '/api/tags', timeout=timeout)
        models = [m.get('name') for m in data.get('models', []) if m.get('name')]
        for pref in ('llama3.2', 'llama3.1', 'gemma3', 'qwen', 'mistral'):
            for name in models:
                if name.startswith(pref): return name
        return models[0] if models else ''
    except Exception:
        return ''

def ask_ai(prompt):
    host, model, timeout = ollama_config()
    model = model or pick_model(host)
    if not model:
        return 'Home AI not found. Start Ollama/model on NukeBox, or set /etc/mappi3/whisplay-ai.env.'
    body = json.dumps({'model': model, 'prompt': prompt, 'stream': False, 'options': {'num_predict': 90}}).encode()
    req = request.Request(host + '/api/generate', data=body, headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8'))
        return data.get('response','').strip() or 'AI returned empty response.'
    except Exception as e:
        return 'AI request failed: ' + str(e)[:120]

def render(title=None, body=None, accent=BLUE):
    title = title or PROMPTS[idx % len(PROMPTS)][0]
    body = body if body is not None else last_answer
    lines = wrap(body, 24)[:10]
    lines.insert(0, '~' + PROMPTS[idx % len(PROMPTS)][0])
    return draw_card('MapPI3 AI', lines, accent, 'press = ask/next · exit gesture backs out')

def main():
    global running, idx, busy, last_answer
    hw = create_hw('whisplay-mappi3-ai-chat', 'MapPI3 AI', 'AI', 90)
    def on_press():
        global idx, busy, last_answer
        if busy: return
        busy = True
        title, prompt = PROMPTS[idx % len(PROMPTS)]
        show(hw, draw_card('MapPI3 AI', ['~asking NukeBox...', title], AMBER))
        last_answer = ask_ai(prompt)
        show(hw, render(title, last_answer, GREEN if not last_answer.startswith('AI request failed') else RED))
        idx += 1
        busy = False
    def exit_req():
        global running
        running = False
    hw.on_button_press(on_press)
    hw.on_exit_request(exit_req)
    show(hw, render())
    try:
        while running:
            time.sleep(0.5)
    finally:
        hw.cleanup()

if __name__ == '__main__':
    main()
