import React, { useEffect, useState } from 'react';
import { connectBle, disconnectBle, useBleLink } from './bleLink.js';

// Phone setup: how this phone is connected, installing MapPI3 as an app, every permission it uses
// (with a one-tap request), offline storage, and battery saving choices.
const isIOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const standalone = () => window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true;

// The install prompt fires once, early; keep it for the Install button.
if (typeof window !== 'undefined') window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); window.__mappi3Install = e; window.dispatchEvent(new CustomEvent('mappi3-installable')); });

async function queryPerm(name) { try { const r = await navigator.permissions.query({ name }); return r.state; } catch { return 'unknown'; } }

export function usePhonePermissions() {
  const [state, setState] = useState({});
  const refresh = async () => {
    const [geo, cam, mic] = await Promise.all([queryPerm('geolocation'), queryPerm('camera'), queryPerm('microphone')]);
    let persisted = false, usage = null, quota = null;
    try { persisted = await navigator.storage?.persisted?.(); const est = await navigator.storage?.estimate?.(); usage = est?.usage; quota = est?.quota; } catch { /* ignore */ }
    setState({ geo, cam, mic, notif: typeof Notification !== 'undefined' ? Notification.permission : 'unsupported', persisted, usage, quota, motion: sessionStorageGet('mappi3.motion') || (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function' ? 'prompt' : 'unknown') });
  };
  useEffect(() => { refresh(); }, []);
  return [state, refresh];
}
function sessionStorageGet(k) { try { return sessionStorage.getItem(k); } catch { return null; } }
function sessionStorageSet(k, v) { try { sessionStorage.setItem(k, v); } catch { /* ignore */ } }

const label = s => ({ granted: 'Allowed', denied: 'Blocked', prompt: 'Not asked yet', default: 'Not asked yet', unknown: 'Unknown', unsupported: 'Not on this phone' })[s] || s;
const tone = s => s === 'granted' ? 'good' : s === 'denied' ? 'bad' : 'warn';
const mb = b => (b ? `${(b / 1048576).toFixed(b > 1e8 ? 0 : 1)} MB` : '—');

export default function PhoneSetup({ settings = {}, setSettings, piLive = null, battery = null }) {
  const [p, refresh] = usePhonePermissions();
  const [installable, setInstallable] = useState(Boolean(window.__mappi3Install));
  const [msg, setMsg] = useState('');
  useEffect(() => { const on = () => setInstallable(true); window.addEventListener('mappi3-installable', on); return () => window.removeEventListener('mappi3-installable', on); }, []);
  const secure = window.isSecureContext;
  const host = window.location.hostname;
  const onPiHotspot = /^10\.42\.0\.1$|^mappi3\.local$/i.test(host);
  const where = onPiHotspot ? (secure ? 'MapPI3 hotspot, secure address' : 'MapPI3 hotspot, plain address') : /vercel\.app$|\.ts\.net$/.test(host) ? 'online app' : /^(localhost|127\.)/.test(host) ? 'this computer' : host;
  const set = patch => setSettings && setSettings(s => ({ ...s, ...patch }));

  const ask = {
    geo: () => new Promise(res => navigator.geolocation.getCurrentPosition(() => res('Location allowed.'), e => res(`Location: ${e.message}`), { enableHighAccuracy: true, timeout: 10000 })),
    motion: async () => { if (typeof DeviceOrientationEvent?.requestPermission === 'function') { const r = await DeviceOrientationEvent.requestPermission(); sessionStorageSet('mappi3.motion', r); return r === 'granted' ? 'Motion and compass allowed.' : 'Motion and compass were not allowed.'; } return 'This phone shares motion and compass without asking.'; },
    cam: async () => { const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }); s.getTracks().forEach(t => t.stop()); return 'Camera allowed.'; },
    mic: async () => { const s = await navigator.mediaDevices.getUserMedia({ audio: true }); s.getTracks().forEach(t => t.stop()); return 'Microphone allowed.'; },
    notif: async () => `Notifications: ${label(await Notification.requestPermission())}.`,
    persist: async () => (await navigator.storage.persist()) ? 'Offline maps and photos are now protected from automatic cleanup.' : 'The browser did not grant protected storage. Installing MapPI3 as an app usually allows it.'
  };
  const run = async (k) => { try { setMsg(await ask[k]()); } catch (e) { setMsg(`${e.message}. If it stays blocked, allow it in the browser's site settings.`); } refresh(); };
  const rows = [
    { k: 'geo', name: 'Location', why: 'Phone GPS when the MapPI3 GPS has no fix, and for photos.', st: p.geo, needsSecure: true },
    { k: 'motion', name: 'Motion and compass', why: 'Sky view, compass and which way you are facing.', st: p.motion, needsSecure: true },
    { k: 'cam', name: 'Camera', why: 'Live sky view. Trail photos use the camera app and need no permission.', st: p.cam, needsSecure: true },
    { k: 'mic', name: 'Microphone', why: 'Talking to Hey Herbie.', st: p.mic, needsSecure: true },
    { k: 'notif', name: 'Notifications', why: 'Off-trail, storm and turnaround alerts when the screen is off.', st: p.notif, needsSecure: true },
    { k: 'persist', name: 'Protected offline storage', why: `Keeps saved areas and photos from being cleared. Using ${mb(p.usage)} of ${mb(p.quota)}.`, st: p.persisted ? 'granted' : 'prompt', needsSecure: false }
  ];
  return <section className="panel st-phone">
    <div className="section-head"><div><h2>Phone</h2><p className="muted">Set up this phone once so GPS, compass, camera, voice and alerts all work, offline too.</p></div></div>
    <div className="st-phone-grid">
      <div className="st-card">
        <div className="st-label">Connection</div>
        <p><strong>{where}</strong> · {piLive ? 'MapPI3 unit connected' : 'MapPI3 unit not reachable'} · {secure ? 'secure (HTTPS)' : 'not secure (HTTP)'}</p>
        {!secure && <div className="alert warn">Phones only share GPS, compass, camera and microphone with secure pages. On the MapPI3 Wi-Fi, open <code>https://10.42.0.1:5443</code> and accept the certificate once. Everything else keeps working here.{onPiHotspot && <> <a className="st-link" href="https://10.42.0.1:5443/">Open the secure address</a></>}</div>}
        <div className="st-label" style={{ marginTop: 10 }}>Install</div>
        {standalone() ? <p>MapPI3 is installed as an app on this phone.</p>
          : installable ? <button type="button" className="primary" onClick={async () => { const e = window.__mappi3Install; e.prompt(); const r = await e.userChoice; setMsg(r.outcome === 'accepted' ? 'Installed. Open MapPI3 from your home screen.' : 'Install cancelled.'); window.__mappi3Install = null; setInstallable(false); }}>Install MapPI3 as an app</button>
          : isIOS() ? <p>In Safari tap the Share button, then <strong>Add to Home Screen</strong>. It opens full screen and keeps working offline.</p>
          : <p className="muted">Use your browser menu and choose <strong>Install app</strong> or <strong>Add to Home screen</strong>.</p>}
      </div>
      <div className="st-card">
        <div className="st-label">Permissions</div>
        <div className="st-perms">{rows.map(r => <div key={r.k} className="st-perm"><div><strong>{r.name}</strong><span>{r.why}</span></div><em className={tone(r.st)}>{label(r.st)}</em>{r.st !== 'granted' && (secure || !r.needsSecure) && <button type="button" className="ghost small" onClick={() => run(r.k)}>Allow</button>}</div>)}</div>
        {msg && <p className="st-phone-msg" aria-live="polite">{msg}</p>}
      </div>
      <div className="st-card">
        <div className="st-label">Battery</div>
        <p>{battery ? `Phone battery ${Math.round(battery.level * 100)}%${battery.charging ? ', charging' : ''}.` : 'This browser does not report the phone battery.'} {piLive?.power?.percent != null ? `MapPI3 battery ${Math.round(piLive.power.percent)}%.` : ''}</p>
        <label className="st-phone-row"><span>Battery saver</span><select value={settings.batterySaver || 'auto'} onChange={e => set({ batterySaver: e.target.value })}><option value="auto">Automatic below 25%</option><option value="on">Always on</option><option value="off">Off</option></select></label>
        <label className="st-phone-row"><span>GPS source</span><select value={settings.gpsPreference || 'auto'} onChange={e => set({ gpsPreference: e.target.value })}><option value="auto">Phone first, MapPI3 backup</option><option value="pi">MapPI3 first (saves phone battery)</option><option value="phone">Phone only</option></select></label>
        <p className="muted">Battery saver turns off background effects, checks the MapPI3 less often, and uses the MapPI3 GPS instead of the phone's whenever it has a fix. The app always pauses its checks while the screen is off.</p>
      </div>
      <BleCard />
    </div>
  </section>;
}

function BleCard() {
  const ble = useBleLink();
  const [pair, setPair] = useState('');
  const openPairing = async () => { try { const r = await fetch('/api/command/ble-pair-window', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(x => x.json()); setPair(r.message || r.error || 'Done.'); } catch { setPair('Connect to the MapPI3 Wi-Fi once to open pairing.'); } };
  return <div className="st-card">
    <div className="st-label">Bluetooth link</div>
    <p>{!navigator.bluetooth ? 'This browser cannot use Bluetooth (iPhone browsers and Firefox do not). Wi-Fi stays the way in.' : ble.status === 'connected' ? <strong>Connected over Bluetooth. GPS, compass and battery are coming in with Wi-Fi off.</strong> : 'This phone can link to the MapPI3 over Bluetooth.'}</p>
    <p className="muted">The link uses very little power and works with the phone's Wi-Fi off or on another network. It is encrypted and only works with a phone you paired. First time: open pairing while on the MapPI3 Wi-Fi, then connect.</p>
    {navigator.bluetooth && <div className="st-ble-actions">
      <button type="button" className="ghost" onClick={openPairing}>Open pairing for 2 minutes</button>
      {ble.status === 'connected' ? <button type="button" className="ghost" onClick={disconnectBle}>Disconnect</button> : <button type="button" className="primary" onClick={connectBle}>Connect over Bluetooth</button>}
    </div>}
    {(pair || ble.message) && <p className="st-phone-msg" aria-live="polite">{pair || ble.message}</p>}
  </div>;
}
