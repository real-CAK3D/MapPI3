// Phone side of the MapPI3 Bluetooth LE link (Chrome on Android, desktop Chrome/Edge).
// Reads the MapPI3's compact status over an encrypted, paired link and turns it into the same shape
// as /api/status, so the rest of the app works the same with Wi-Fi off.
import { useEffect, useState } from 'react';

export const BLE_SERVICE = '6d617069-3301-4c6e-9b5e-6d6170693300';
const STATUS = '6d617069-3301-4c6e-9b5e-6d6170693301';
const COMMAND = '6d617069-3301-4c6e-9b5e-6d6170693302';
const state = { status: 'idle', message: '', data: null, device: null, command: null, at: 0 };
const listeners = new Set();
const emit = () => listeners.forEach(fn => fn({ ...state }));
const set = patch => { Object.assign(state, patch); emit(); };

function toPiLive(d) {
  if (!d?.ok) return null;
  return {
    ok: true, via: 'bluetooth', fetchedAt: Date.now(), connection_mode: 'bluetooth',
    gps: { fix: d.g?.f, lat: d.g?.la, lon: d.g?.lo, alt: d.g?.al, satellites: d.g?.s, eph: d.g?.e, mode: d.g?.m },
    sense: { ok: d.s?.ok, compass: d.s?.h, compass_cardinal: d.s?.c, pressure: d.s?.p, humidity: d.s?.hu },
    power: { percent: d.b?.p, charging: d.b?.c },
    state: { herbie_event: d.h?.n ? { name: d.h.n, until: d.h.u, reason: d.h.r } : null },
    herbie_calendar: d.h?.cal ? { reason: d.h.cal } : null
  };
}

export async function connectBle() {
  if (!navigator.bluetooth) { set({ status: 'unsupported', message: 'This browser cannot use Bluetooth. Use Chrome on Android, or Wi-Fi.' }); return; }
  try {
    set({ status: 'connecting', message: 'Choose "MapPI3" in the list.' });
    const device = await navigator.bluetooth.requestDevice({ filters: [{ services: [BLE_SERVICE] }, { name: 'MapPI3' }], optionalServices: [BLE_SERVICE] });
    device.addEventListener('gattserverdisconnected', () => set({ status: 'disconnected', message: 'Bluetooth link dropped. Tap Connect to rejoin.', command: null }));
    const server = await device.gatt.connect();
    const service = await server.getPrimaryService(BLE_SERVICE);
    const statusChar = await service.getCharacteristic(STATUS);
    const command = await service.getCharacteristic(COMMAND).catch(() => null);
    const read = async () => { const v = await statusChar.readValue(); const d = JSON.parse(new TextDecoder().decode(v)); set({ data: toPiLive(d), at: Date.now(), status: 'connected', message: 'Connected over Bluetooth.' }); };
    await read(); // first encrypted read triggers pairing on the phone if needed
    statusChar.addEventListener('characteristicvaluechanged', e => { try { set({ data: toPiLive(JSON.parse(new TextDecoder().decode(e.target.value))), at: Date.now() }); } catch { read().catch(() => {}); } });
    await statusChar.startNotifications().catch(() => { const t = setInterval(() => (device.gatt.connected ? read().catch(() => {}) : clearInterval(t)), 3000); });
    set({ device, command });
  } catch (e) {
    set({ status: 'error', message: e.name === 'NotFoundError' ? 'No MapPI3 chosen. Make sure the Bluetooth phone link extra is installed and pairing is open.' : e.message });
  }
}
export function disconnectBle() { try { state.device?.gatt?.disconnect(); } catch { /* ignore */ } set({ status: 'idle', message: '', data: null, device: null, command: null }); }
export async function bleHerbieEvent(event, ttl = 20, reason = '') {
  if (!state.command) return false;
  try { await state.command.writeValue(new TextEncoder().encode(JSON.stringify({ cmd: 'herbie-event', event, ttl, reason }))); return true; } catch { return false; }
}
export function useBleLink() {
  const [s, setS] = useState({ ...state });
  useEffect(() => { listeners.add(setS); return () => listeners.delete(setS); }, []);
  return s;
}

// Latest Bluetooth snapshot (null when not connected or older than 30 s).
export function bleSnapshot() { return state.status === 'connected' && Date.now() - state.at < 30000 ? state.data : null; }
