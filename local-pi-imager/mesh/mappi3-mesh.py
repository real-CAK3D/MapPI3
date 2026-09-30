#!/usr/bin/env python3
"""MapPI3 mesh service: talks to a Meshtastic radio and shares the mesh with the rest of MapPI3.

Connects over USB serial (auto-detected) or Wi-Fi/TCP, keeps the node list, positions, signal and
text messages, adds distance/bearing from the Pi's own GPS, and serves it on a small local HTTP API:
  GET  /state          everything the Whisplay and the app need
  POST /send {text, to} send a text message (to = node id like "!8f501778", default broadcast)
Messages are kept across restarts. Reconnects on its own if the radio is unplugged.

Config (optional) in /etc/mappi3/mesh.env:
  MESH_PORT=auto | /dev/ttyACM0 | COM16     MESH_HOST=192.168.x.x (TCP instead of serial)
  MESH_HTTP_PORT=5061   MESH_STATE_DIR=/var/lib/mappi3   MAPPI3_API=http://127.0.0.1:5050
"""
import glob, json, math, os, threading, time, urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def load_env(path='/etc/mappi3/mesh.env'):
    out = {}
    try:
        for line in Path(path).read_text().splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1); out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


ENV = {**load_env(), **os.environ}
PORT = ENV.get('MESH_PORT', 'auto')
HOST = ENV.get('MESH_HOST', '')
HTTP_PORT = int(ENV.get('MESH_HTTP_PORT', '5061'))
STATE_DIR = Path(ENV.get('MESH_STATE_DIR', '/var/lib/mappi3'))
API = ENV.get('MAPPI3_API', 'http://127.0.0.1:5050')
MSG_FILE = STATE_DIR / 'mesh-messages.json'

lock = threading.Lock()
iface = None
conn = {'ok': False, 'via': None, 'port': None, 'since': None, 'error': 'starting'}
messages = deque(maxlen=100)
pi_fix = {'lat': None, 'lon': None, 'at': 0}

try:
    messages.extend(json.loads(MSG_FILE.read_text()))
except Exception:
    pass


def save_messages():
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MSG_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(list(messages))); tmp.replace(MSG_FILE)
    except OSError:
        pass


def find_serial():
    if PORT and PORT != 'auto':
        return PORT
    for pat in ('/dev/serial/by-id/*Seeed*', '/dev/serial/by-id/*Espressif*', '/dev/serial/by-id/*', '/dev/ttyACM*', '/dev/ttyUSB*'):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def node_name(num_or_id):
    try:
        nodes = iface.nodes or {}
        for n in nodes.values():
            if n.get('num') == num_or_id or n.get('user', {}).get('id') == num_or_id:
                u = n.get('user', {}); return u.get('longName') or u.get('shortName') or u.get('id')
    except Exception:
        pass
    return str(num_or_id)


def on_receive(packet, interface=None):
    try:
        d = packet.get('decoded') or {}
        if d.get('portnum') != 'TEXT_MESSAGE_APP':
            return
        text = d.get('text') or (d.get('payload') or b'').decode('utf-8', 'replace')
        me = (iface.myInfo.my_node_num if iface and iface.myInfo else None)
        msg = {'id': packet.get('id') or int(time.time() * 1000), 'from': packet.get('fromId') or packet.get('from'), 'fromName': node_name(packet.get('from')),
               'to': packet.get('toId') or packet.get('to'), 'direct': packet.get('to') == me, 'channel': packet.get('channel', 0), 'text': text[:240],
               'at': packet.get('rxTime') or int(time.time()), 'snr': packet.get('rxSnr'), 'rssi': packet.get('rxRssi'),
               'hops': (packet.get('hopStart', 0) - packet.get('hopLimit', 0)) if packet.get('hopStart') is not None else None, 'mine': False}
        # Meshtastic's alert bell (ASCII 7) or an SOS-style word marks an alert
        msg['alert'] = BELL in text or bool(ALERT_WORDS.search(text))
        msg['text'] = text.replace(BELL, '').strip()[:240] or '(alert)'
        is_new = False
        with lock:
            if not any(m.get('id') == msg['id'] for m in messages):
                messages.append(msg); save_messages(); is_new = True
        if is_new:
            who = (msg['fromName'] or str(msg['from'])).strip()
            herbie('hazard' if msg['alert'] else 'mesh-message', 180 if msg['alert'] else 45, f"{who}: {msg['text']}")
    except Exception as e:  # never let a bad packet kill the listener
        print('receive error', e, flush=True)


ALERT_WORDS = __import__('re').compile(r'\b(sos|mayday|emergency|help me|injured|hurt|lost)\b', __import__('re').I)
BELL = chr(7)

def herbie(event, ttl, reason):
    """Let Herbie react on the Whisplay and in the app (agent herbie-event)."""
    try:
        body = json.dumps({'event': event, 'ttl': ttl, 'reason': reason[:60]}).encode()
        urllib.request.urlopen(urllib.request.Request(API + '/api/command/herbie-event', data=body, headers={'Content-Type': 'application/json'}), timeout=3).read()
    except Exception:
        pass


def on_lost(interface=None, **_):
    with lock:
        conn.update(ok=False, error='radio disconnected')


def find_wifi_radio():
    """A Meshtastic radio that joined the MapPI3 hotspot: any hotspot device answering on port 4403."""
    import socket, subprocess
    try:
        out = subprocess.run(['ip', 'neigh', 'show', 'dev', ENV.get('MESH_WIFI_DEV', 'wlan0')], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return None
    for line in out.splitlines():
        ip = line.split()[0] if line.split() else ''
        if not ip.count('.') == 3 or 'FAILED' in line:
            continue
        try:
            with socket.create_connection((ip, 4403), timeout=0.6):
                return ip
        except OSError:
            continue
    return None


def connect_loop():
    """Keep a connection to the radio; retry every 10 s when it is missing or unplugged."""
    global iface
    from pubsub import pub
    import meshtastic.serial_interface, meshtastic.tcp_interface
    pub.subscribe(on_receive, 'meshtastic.receive.text')
    pub.subscribe(on_lost, 'meshtastic.connection.lost')
    while True:
        if conn['ok'] and iface is not None:
            time.sleep(5); continue
        try:
            if iface is not None:
                try: iface.close()
                except Exception: pass
                iface = None
            # USB first (keeps the radio's Bluetooth free for the phone), then a radio on the hotspot's Wi-Fi.
            port = find_serial()
            host = None if port else (HOST or find_wifi_radio())
            if port:
                iface = meshtastic.serial_interface.SerialInterface(devPath=port); via = 'usb'
            elif host:
                iface = meshtastic.tcp_interface.TCPInterface(hostname=host); via, port = 'wifi', host
            else:
                with lock: conn.update(ok=False, via=None, port=None, error='no radio on USB or the hotspot')
                time.sleep(10); continue
            with lock: conn.update(ok=True, via=via, port=port, since=time.time(), error=None)
            print('connected', via, port, flush=True)
        except Exception as e:
            with lock: conn.update(ok=False, error=str(e)[:160])
            print('connect failed', e, flush=True)
            time.sleep(10)


def gps_loop():
    """Pi's own position, for distance and bearing to each node."""
    while True:
        try:
            with urllib.request.urlopen(API + '/api/gps', timeout=3) as r:
                g = json.loads(r.read().decode())
            fix = g.get('fix') if isinstance(g.get('fix'), dict) else g
            lat, lon = fix.get('lat') or fix.get('latitude'), fix.get('lon') or fix.get('longitude')
            if lat is not None and lon is not None and (g.get('fix') not in (False, None) or fix is not g):
                pi_fix.update(lat=float(lat), lon=float(lon), at=time.time())
        except Exception:
            pass
        time.sleep(10)


def dist_bearing(a_lat, a_lon, b_lat, b_lon):
    r = math.radians
    dlat, dlon = r(b_lat - a_lat), r(b_lon - a_lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a_lat)) * math.cos(r(b_lat)) * math.sin(dlon / 2) ** 2
    miles = 7917.6 * math.asin(math.sqrt(h))
    y = math.sin(dlon) * math.cos(r(b_lat)); x = math.cos(r(a_lat)) * math.sin(r(b_lat)) - math.sin(r(a_lat)) * math.cos(r(b_lat)) * math.cos(dlon)
    return miles, (math.degrees(math.atan2(y, x)) + 360) % 360


def state():
    with lock:
        c = dict(conn); msgs = list(messages)[-30:]
    out = {'ok': c['ok'], 'connection': c, 'me': None, 'radio': None, 'nodes': [], 'messages': msgs, 'pi': dict(pi_fix), 'time': time.time()}
    if not (c['ok'] and iface is not None):
        return out
    try:
        my = iface.getMyNodeInfo() or {}
        u = my.get('user', {})
        out['me'] = {'id': u.get('id'), 'long': u.get('longName'), 'short': u.get('shortName'), 'hw': u.get('hwModel'),
                     'battery': (my.get('deviceMetrics') or {}).get('batteryLevel')}
        lc = iface.localNode.localConfig
        from meshtastic.protobuf import config_pb2
        preset = config_pb2.Config.LoRaConfig.ModemPreset.Name(lc.lora.modem_preset).replace('_', ' ').title()
        region = config_pb2.Config.LoRaConfig.RegionCode.Name(lc.lora.region)
        out['radio'] = {'preset': preset, 'region': region, 'firmware': getattr(iface.metadata, 'firmware_version', None)}
        now = time.time()
        for n in (iface.nodes or {}).values():
            uu = n.get('user', {})
            if uu.get('id') == u.get('id'):
                continue
            pos = n.get('position') or {}
            dm = n.get('deviceMetrics') or {}
            item = {'id': uu.get('id'), 'long': uu.get('longName'), 'short': uu.get('shortName'), 'hw': uu.get('hwModel'),
                    'lastHeard': n.get('lastHeard'), 'ago': (now - n['lastHeard']) if n.get('lastHeard') else None,
                    'snr': n.get('snr'), 'hops': n.get('hopsAway'), 'battery': dm.get('batteryLevel'),
                    'lat': pos.get('latitude'), 'lon': pos.get('longitude'), 'alt': pos.get('altitude'), 'miles': None, 'bearing': None}
            if item['lat'] is not None and pi_fix['lat'] is not None:
                item['miles'], item['bearing'] = [round(v, 2) for v in dist_bearing(pi_fix['lat'], pi_fix['lon'], item['lat'], item['lon'])]
            out['nodes'].append(item)
        out['nodes'].sort(key=lambda x: (x['ago'] is None, x['ago'] or 0))
    except Exception as e:
        out['error'] = str(e)[:160]
    return out


def send(text, to=None):
    text = str(text or '').strip()[:200]
    if not text:
        return {'ok': False, 'error': 'empty message'}
    if not (conn['ok'] and iface is not None):
        return {'ok': False, 'error': 'radio not connected'}
    dest = to if to and str(to).startswith('!') else '^all'
    iface.sendText(text, destinationId=dest)
    me = (iface.getMyNodeInfo() or {}).get('user', {})
    with lock:
        messages.append({'id': int(time.time() * 1000), 'from': me.get('id'), 'fromName': me.get('longName') or 'MapPI3', 'to': dest, 'direct': dest != '^all', 'channel': 0,
                         'text': text, 'at': int(time.time()), 'snr': None, 'rssi': None, 'hops': 0, 'mine': True}); save_messages()
    return {'ok': True}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/state'): self._json(state())
        else: self._json({'ok': False, 'error': 'not found'}, 404)
    def do_POST(self):
        if not self.path.startswith('/send'): return self._json({'ok': False, 'error': 'not found'}, 404)
        try:
            n = min(int(self.headers.get('Content-Length') or 0), 4096)
            p = json.loads(self.rfile.read(n) or b'{}')
            self._json(send(p.get('text'), p.get('to')))
        except Exception as e:
            self._json({'ok': False, 'error': str(e)[:120]}, 400)
    def log_message(self, *a):
        pass


if __name__ == '__main__':
    threading.Thread(target=connect_loop, daemon=True).start()
    threading.Thread(target=gps_loop, daemon=True).start()
    print(f'mesh service on 127.0.0.1:{HTTP_PORT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', HTTP_PORT), Handler).serve_forever()
