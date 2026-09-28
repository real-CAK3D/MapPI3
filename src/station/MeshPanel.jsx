import React, { useEffect, useMemo, useRef, useState } from 'react';
import LiveLeafletMap from '../components/LiveLeafletMap.jsx';
import { bluetoothSupported, connectBluetooth, disconnectBluetooth, markRead, sendText, useMesh } from './mesh.js';

// Meshtastic inside MapPI3: chat, nodes and a map, through the Pi's radio or straight to the radio
// over Bluetooth, so the separate Meshtastic app is not needed on the trail.
const PRESETS = ['Long Fast', 'Long Slow', 'Very Long Slow', 'Medium Slow', 'Medium Fast', 'Short Slow', 'Short Fast', 'Long Moderate', 'Short Turbo'];
const REGIONS = { 1: 'US', 2: 'EU 433', 3: 'EU 868', 4: 'CN', 5: 'JP', 6: 'ANZ', 7: 'KR', 8: 'TW', 9: 'RU', 10: 'IN', 11: 'NZ 865', 12: 'TH' };
const ago = t => { if (!t) return 'not heard yet'; const s = Math.max(0, (Date.now() - t) / 1000); return s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`; };
const CARD = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
function distBearing(a, b) {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  const y = Math.sin(dLon) * Math.cos(b.lat * r), x = Math.cos(a.lat * r) * Math.sin(b.lat * r) - Math.sin(a.lat * r) * Math.cos(b.lat * r) * Math.cos(dLon);
  return { miles: 7917.6 * Math.asin(Math.sqrt(h)), bearing: (Math.atan2(y, x) / r + 360) % 360 };
}
const bars = snr => (snr == null ? 0 : snr >= 5 ? 4 : snr >= 0 ? 3 : snr >= -7 ? 2 : 1);

export default function MeshPanel({ originPoint = null }) {
  const m = useMesh();
  const [convo, setConvo] = useState('^all');
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const listRef = useRef(null);
  useEffect(() => { markRead(); }, [m.messages.length]);
  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight; }, [m.messages.length, convo]);

  const nodes = useMemo(() => Object.values(m.nodes).map(n => {
    const where = originPoint && n.lat != null ? distBearing(originPoint, n) : null;
    return { ...n, name: n.long || n.short || n.id, ...(where || {}) };
  }).sort((a, b) => (b.lastHeard || 0) - (a.lastHeard || 0)), [m.nodes, originPoint]);

  // conversations: the shared channel plus one per person you have direct messages with
  const convos = useMemo(() => {
    const direct = new Map();
    m.messages.filter(x => x.direct).forEach(x => { const other = x.mine ? x.to : x.from; if (other) direct.set(other, x.at); });
    return [['^all', 'Everyone'], ...[...direct.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => [id, m.nodes[id]?.long || m.nodes[id]?.short || id])];
  }, [m.messages, m.nodes]);
  const thread = m.messages.filter(x => (convo === '^all' ? !x.direct : x.direct && (x.from === convo || x.to === convo)));
  const bytes = new TextEncoder().encode(draft).length;

  const send = async e => {
    e.preventDefault(); if (!draft.trim() || busy) return;
    setBusy(true); setNote('');
    try { await sendText(draft, convo); setDraft(''); } catch (err) { setNote(String(err.message || err)); }
    setBusy(false);
  };
  const bt = async () => { setNote(''); try { await connectBluetooth(); } catch (err) { setNote(m.error || String(err.message || err)); } };

  const via = m.source === 'pi' ? 'Through MapPI3' : m.source === 'ble' ? 'Phone Bluetooth' : null;
  const preset = m.radio?.preset || (m.radio?.presetNum != null ? PRESETS[m.radio.presetNum] : null);
  const region = m.radio?.region || (m.radio?.regionNum != null ? REGIONS[m.radio.regionNum] : null);
  const mapNodes = nodes.filter(n => n.lat != null && n.lon != null);
  const mapCenter = mapNodes[0] ? [mapNodes[0].lat, mapNodes[0].lon] : originPoint ? [originPoint.lat, originPoint.lon] : null;

  return <section className="panel mesh-panel">
    <div className="mesh-head">
      <div>
        <h2>Mesh</h2>
        <p className="muted">Meshtastic chat and nearby nodes, no separate app needed.</p>
      </div>
      <div className="mesh-conn">
        <span className={`mesh-chip ${m.status === 'connected' ? 'on' : m.status === 'connecting' ? 'wait' : 'off'}`}>{m.status === 'connected' ? via : m.status === 'connecting' ? 'Connecting…' : 'Not connected'}</span>
        {m.source === 'ble' ? <button type="button" className="ghost small" onClick={disconnectBluetooth}>Disconnect</button>
          : bluetoothSupported() ? <button type="button" className={m.source === 'pi' ? 'ghost small' : 'primary small'} onClick={bt} disabled={m.status === 'connecting'}>{m.source === 'pi' ? 'Use phone Bluetooth instead' : 'Connect by Bluetooth'}</button> : null}
      </div>
    </div>
    {m.status === 'connected' && <p className="mesh-me">{(m.me?.long || m.me?.short || 'Your radio')}{m.me?.id ? ` · ${m.me.id}` : ''}{preset ? ` · ${preset}` : ''}{region ? ` · ${region}` : ''}{m.me?.battery != null ? ` · ${m.me.battery > 100 ? 'on USB power' : `battery ${m.me.battery}%`}` : ''}</p>}
    {m.status !== 'connected' && <div className="mesh-help">
      <p><b>Two ways to connect</b></p>
      <ul>
        <li><b>Through MapPI3:</b> plug the radio into the Pi's USB port and join the MapPI3 hotspot (or Tailscale). The app picks it up by itself.</li>
        <li><b>Phone Bluetooth:</b> open the app from <code>map-pi3.vercel.app</code> in Chrome on your phone and tap Connect by Bluetooth. Close the Meshtastic app first; the radio talks to one Bluetooth app at a time.{!bluetoothSupported() && ' This browser or page cannot use Bluetooth.'}</li>
      </ul>
      {(m.error || note) && <p className="mesh-err">{note || m.error}</p>}
    </div>}

    <div className="mesh-grid">
      <div className="mesh-chat st-card">
        <div className="mesh-convos">{convos.map(([id, label]) => <button key={id} type="button" className={convo === id ? 'on' : ''} onClick={() => setConvo(id)}>{label}</button>)}</div>
        <div className="mesh-thread" ref={listRef}>
          {thread.length ? thread.map(x => <div key={`${x.from}-${x.id}`} className={`mesh-msg ${x.mine ? 'mine' : ''}`}>
            {!x.mine && <b>{x.fromName || m.nodes[x.from]?.long || x.from}</b>}
            <span>{x.text}</span>
            <small>{new Date(x.at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}{x.snr != null ? ` · SNR ${Math.round(x.snr * 10) / 10}` : ''}</small>
          </div>) : <p className="muted mesh-empty">{convo === '^all' ? 'No channel messages yet.' : 'No direct messages yet.'}</p>}
        </div>
        <form className="mesh-send" onSubmit={send}>
          <input id="mesh-draft" value={draft} onChange={e => setDraft(e.target.value)} placeholder={convo === '^all' ? 'Message everyone on the channel' : `Message ${convos.find(c => c[0] === convo)?.[1] || ''}`} maxLength={240} disabled={m.status !== 'connected'} />
          <button type="submit" className="primary" disabled={m.status !== 'connected' || !draft.trim() || busy || bytes > 200}>{busy ? 'Sending…' : 'Send'}</button>
        </form>
        <p className={`mesh-count ${bytes > 200 ? 'over' : ''}`}>{bytes}/200 bytes{note && m.status === 'connected' ? ` · ${note}` : ''}</p>
      </div>

      <div className="mesh-side">
        <div className="st-card mesh-nodes">
          <div className="st-label">Nodes heard · {nodes.length}</div>
          {nodes.length ? nodes.map(n => <div key={n.id} className="mesh-node">
            <div className="mesh-node-main">
              <b>{n.name}</b>
              <small>{[n.miles != null ? (n.miles >= 0.1 ? `${n.miles.toFixed(1)} mi ${CARD[Math.round(n.bearing / 45) % 8]}` : `${Math.round(n.miles * 5280)} ft`) : null, n.hops ? `${n.hops} hop${n.hops > 1 ? 's' : ''}` : n.hops === 0 ? 'direct' : null, ago(n.lastHeard), n.battery != null ? (n.battery > 100 ? 'USB power' : `${n.battery}%`) : null].filter(Boolean).join(' · ')}</small>
            </div>
            <span className={`mesh-bars b${bars(n.snr)}`} title={n.snr != null ? `SNR ${n.snr}` : 'no signal reading'}><i /><i /><i /><i /></span>
            <button type="button" className="ghost small" onClick={() => setConvo(n.id)}>Message</button>
          </div>) : <p className="muted">No other nodes heard yet.</p>}
        </div>
        {mapCenter && <div className="st-card mesh-map">
          <LiveLeafletMap center={mapCenter} waypoints={mapNodes.map(n => ({ id: n.id, name: n.name, type: 'Mesh node', lat: n.lat, lon: n.lon }))} showCenterMarker={Boolean(originPoint)} />
          <p className="muted">{mapNodes.length ? `${mapNodes.length} node${mapNodes.length > 1 ? 's' : ''} sharing a position` : 'No node has shared a position yet.'}</p>
        </div>}
      </div>
    </div>
  </section>;
}
