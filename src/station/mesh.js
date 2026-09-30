// Meshtastic in MapPI3: one store fed either by the Pi's mesh service (radio plugged into the Pi) or
// straight from the phone to the radio over Bluetooth (Chrome on Android, https). Messages and the
// last-known nodes are kept on this device so the chat is there when you reopen the app.
import { useEffect, useState } from 'react';

const MSG_KEY = 'mappi3.meshMessages', NODE_KEY = 'mappi3.meshNodes';
const load = (k, f) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : f; } catch { return f; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage full or blocked */ } };
export const nodeId = num => '!' + (Number(num) >>> 0).toString(16).padStart(8, '0');

const S = {
  source: null,          // 'pi' | 'ble' | null
  status: 'idle',        // idle | connecting | connected | error
  error: '', me: null, radio: null,
  nodes: load(NODE_KEY, {}),            // id -> node
  messages: load(MSG_KEY, []),          // oldest first
  unread: 0
};
const listeners = new Set();
const emit = () => { const snap = { ...S, nodes: { ...S.nodes }, messages: [...S.messages] }; listeners.forEach(fn => fn(snap)); };
const persist = () => { save(MSG_KEY, S.messages.slice(-300)); save(NODE_KEY, S.nodes); };

// Meshtastic's alert bell (ASCII 7) or an SOS-style word marks an alert (same rule as the Pi).
const ALERT_WORDS = /\b(sos|mayday|emergency|help me|injured|hurt|lost)\b/i;
const BELL = String.fromCharCode(7);
const isAlert = (text = '', flag) => Boolean(flag) || String(text).includes(BELL) || ALERT_WORDS.test(String(text));

// New incoming messages, for the app-wide toast and phone notification.
const newMsgListeners = new Set();
export const onNewMessage = (fn) => { newMsgListeners.add(fn); return () => newMsgListeners.delete(fn); };
let primed = false;   // messages already on the Pi when the app opens are not re-announced

function addMessage(m) {
  if (S.messages.some(x => x.id === m.id && x.from === m.from)) return;
  const msg = { ...m, text: String(m.text || '').split(BELL).join('').trim() || '(alert)', alert: isAlert(m.text, m.alert) };
  S.messages.push(msg);
  S.messages.sort((a, b) => a.at - b.at);
  if (!msg.mine) { S.unread += 1; if (primed && Date.now() - msg.at < 10 * 60 * 1000) newMsgListeners.forEach(fn => fn(msg)); }
  persist();
}
function upsertNode(id, patch) {
  if (!id || (S.me && id === S.me.id)) return;
  S.nodes[id] = { ...(S.nodes[id] || { id }), ...patch };
}

// ---------- Through the Pi ----------
let piTimer = null;
async function pollPi() {
  try {
    const r = await fetch('/api/mesh/status', { cache: 'no-store' });
    const d = r.ok ? await r.json() : null;
    if (!d || d.ok === false && !d.connection) throw new Error(d?.error || 'MapPI3 mesh service not reachable');
    if (!d.ok) { if (S.source === 'pi') { S.status = 'error'; S.error = d.connection?.error || d.error || 'radio not connected to the Pi'; emit(); } return false; }
    S.source = 'pi'; S.status = 'connected'; S.error = '';
    S.me = d.me ? { id: d.me.id, long: (d.me.long || '').trim(), short: d.me.short, battery: d.me.battery } : S.me;
    S.radio = d.radio || S.radio;
    (d.nodes || []).forEach(n => upsertNode(n.id, { long: (n.long || '').trim(), short: n.short, hw: n.hw, snr: n.snr, hops: n.hops, battery: n.battery, lastHeard: n.lastHeard ? n.lastHeard * 1000 : null, lat: n.lat, lon: n.lon }));
    (d.messages || []).forEach(m => addMessage({ id: m.id, from: m.from, fromName: (m.fromName || '').trim(), to: m.to, direct: !!m.direct, channel: m.channel || 0, text: m.text, at: (m.at || 0) * 1000, snr: m.snr, mine: !!m.mine, alert: !!m.alert }));
    primed = true;
    persist(); emit();
    return true;
  } catch (e) {
    if (S.source === 'pi') { S.status = 'error'; S.error = String(e.message || e); emit(); }
    return false;
  }
}
export function startPi() {
  if (piTimer) return;
  pollPi();
  piTimer = setInterval(() => { if (S.source !== 'ble') pollPi(); }, 3000);
}
export function stopPi() { clearInterval(piTimer); piTimer = null; }

// ---------- Straight to the radio over Bluetooth ----------
let device = null, transport = null;
export const bluetoothSupported = () => typeof navigator !== 'undefined' && !!navigator.bluetooth && typeof window !== 'undefined' && window.isSecureContext;

export async function connectBluetooth() {
  if (!bluetoothSupported()) throw new Error('Bluetooth needs Chrome on Android (or desktop Chrome) and the https app.');
  S.status = 'connecting'; S.error = ''; primed = true; emit();
  try {
    // the Meshtastic logger reads process.env / process.cwd(), which browsers do not have
    if (typeof globalThis.process === 'undefined') globalThis.process = { env: {}, cwd: () => '/' };
    const [{ MeshDevice }, { TransportWebBluetooth }] = await Promise.all([import('@meshtastic/core'), import('@meshtastic/transport-web-bluetooth')]);
    transport = await TransportWebBluetooth.create();
    device = new MeshDevice(transport);
    const ev = device.events;
    ev.onMyNodeInfo.subscribe(info => { S.me = { ...(S.me || {}), id: nodeId(info.myNodeNum), num: info.myNodeNum }; emit(); });
    ev.onNodeInfoPacket.subscribe(n => {
      const id = nodeId(n.num);
      if (S.me && S.me.num === n.num) { S.me = { ...S.me, long: n.user?.longName?.trim(), short: n.user?.shortName, battery: n.deviceMetrics?.batteryLevel }; emit(); return; }
      upsertNode(id, { long: n.user?.longName?.trim(), short: n.user?.shortName, hw: n.user?.hwModel, snr: n.snr, hops: n.hopsAway, battery: n.deviceMetrics?.batteryLevel,
        lastHeard: n.lastHeard ? n.lastHeard * 1000 : null,
        lat: n.position?.latitudeI ? n.position.latitudeI / 1e7 : undefined, lon: n.position?.longitudeI ? n.position.longitudeI / 1e7 : undefined });
      persist(); emit();
    });
    ev.onUserPacket.subscribe(p => { upsertNode(nodeId(p.from), { long: p.data.longName?.trim(), short: p.data.shortName, hw: p.data.hwModel, lastHeard: Date.now() }); persist(); emit(); });
    ev.onPositionPacket.subscribe(p => { if (p.data.latitudeI) { upsertNode(nodeId(p.from), { lat: p.data.latitudeI / 1e7, lon: p.data.longitudeI / 1e7, lastHeard: Date.now() }); persist(); emit(); } });
    ev.onTelemetryPacket.subscribe(p => { const b = p.data?.variant?.value?.batteryLevel; if (b != null) { upsertNode(nodeId(p.from), { battery: b }); emit(); } });
    ev.onConfigPacket.subscribe(c => { if (c.payloadVariant?.case === 'lora') { const l = c.payloadVariant.value; S.radio = { ...(S.radio || {}), presetNum: l.modemPreset, regionNum: l.region }; emit(); } });
    ev.onMessagePacket.subscribe(p => {
      const from = nodeId(p.from), mine = S.me && p.from === S.me.num;
      addMessage({ id: p.id, from, fromName: mine ? 'you' : (S.nodes[from]?.long || S.nodes[from]?.short || from), to: p.type === 'direct' ? nodeId(p.to) : '^all', direct: p.type === 'direct', channel: p.channel || 0, text: p.data, at: +p.rxTime || Date.now(), mine });
      upsertNode(from, { lastHeard: Date.now() }); emit();
    });
    ev.onDeviceStatus.subscribe(st => {
      if (st === 7) { S.status = 'connected'; S.source = 'ble'; }
      else if (st === 2) { S.status = 'idle'; if (S.source === 'ble') S.source = null; }
      emit();
    });
    await device.configure();
    S.source = 'ble'; S.status = 'connected'; emit();
  } catch (e) {
    S.status = 'error';
    S.error = /cancel|chooser/i.test(String(e?.message || e)) ? 'No radio picked.' : String(e?.message || e);
    device = null; emit();
    throw e;
  }
}
export async function disconnectBluetooth() {
  try { await device?.disconnect(); } catch { /* already gone */ }
  device = null; transport = null;
  if (S.source === 'ble') { S.source = null; S.status = 'idle'; }
  emit();
}

// ---------- Sending ----------
export async function sendText(text, to = '^all') {
  const body = String(text || '').trim();
  if (!body) return;
  if (new TextEncoder().encode(body).length > 200) throw new Error('Too long for one mesh message (200 bytes max).');
  if (S.source === 'ble' && device) {
    const dest = to === '^all' ? 'broadcast' : parseInt(String(to).slice(1), 16);
    const id = await device.sendText(body, dest, true, 0);
    addMessage({ id, from: S.me?.id, fromName: 'you', to, direct: to !== '^all', channel: 0, text: body, at: Date.now(), mine: true });
    emit(); return;
  }
  if (S.source === 'pi') {
    const r = await fetch('/api/command/mesh-send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: body, to: to === '^all' ? null : to }) });
    const d = await r.json().catch(() => ({}));
    if (!d.ok) throw new Error(d.error || 'The Pi could not send it.');
    await pollPi(); return;
  }
  throw new Error('Connect to the radio first.');
}

export function markRead() { if (S.unread) { S.unread = 0; emit(); } }
export function clearHistory() { S.messages = []; S.unread = 0; persist(); emit(); }

export function useMesh() {
  const [snap, setSnap] = useState(() => ({ ...S }));
  useEffect(() => { listeners.add(setSnap); startPi(); return () => { listeners.delete(setSnap); }; }, []);
  return snap;
}
