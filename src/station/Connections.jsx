import React, { useEffect, useState } from 'react';
import { supabaseConfig, supabaseHealth } from '../lib/supabaseClient.js';

// Every address MapPI3 lives at, with live status where the app can check it, and how to connect.
// Passwords and keys are never shown here: the hotspot password is the one set on the Pi, and SSH
// uses your key.
const KNOWN = {
  hotspotSsid: 'MapPI3', hotspotIp: '10.42.0.1', piPort: 5050, piUser: 'mappi3',
  github: 'https://github.com/real-CAK3D/MapPI3', vercel: 'https://map-pi3.vercel.app',
  supabaseRef: 'adbsxppzotasctjdiwgc',
  garden: { ip: '100.82.165.23', dns: 'terminal-vnic.tailac984b.ts.net', https: 'https://terminal-vnic.tailac984b.ts.net:8443/' }
};
const load = (k, f) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : f; } catch { return f; } };

function Row({ label, value, href, status, note }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* select it instead */ } };
  return <div className="cx-row">
    <div className="cx-label">{status && <i className={`cx-dot ${status}`} title={status} />}{label}</div>
    <div className="cx-value">{href ? <a href={href} target="_blank" rel="noreferrer">{value}</a> : <code>{value}</code>}{note && <small>{note}</small>}</div>
    <button type="button" className="ghost small" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
  </div>;
}

export default function Connections({ piLive = null }) {
  const [net, setNet] = useState(() => load('mappi3.connectionsCache', null));
  const [cloud, setCloud] = useState(null);
  const [checking, setChecking] = useState(false);
  const refresh = async () => {
    setChecking(true);
    try {
      const r = await fetch('/api/network/status', { cache: 'no-store' });
      const j = r.ok ? await r.json() : null;
      if (j?.ok) { const keep = { at: Date.now(), tailscale: j.tailscale || null, wifi: j.wifi || null, ssh: j.ssh ? { ok: j.ssh.ok } : null }; setNet({ ...keep, live: true }); try { localStorage.setItem('mappi3.connectionsCache', JSON.stringify(keep)); } catch { /* optional */ } }
      else setNet(n => (n ? { ...n, live: false } : n));
    } catch { setNet(n => (n ? { ...n, live: false } : n)); }
    supabaseHealth().then(setCloud);
    setChecking(false);
  };
  useEffect(() => { refresh(); }, []);

  const piOnline = Boolean(piLive) || Boolean(net?.live);
  const ts = net?.tailscale || {};
  const tsIps = (ts.tailscale_ips || []).filter(Boolean);
  const tsDns = String(ts.dns_name || '').replace(/\.$/, '');
  const supaUrl = supabaseConfig.url || `https://${KNOWN.supabaseRef}.supabase.co`;
  const ref = (supaUrl.match(/https:\/\/([a-z0-9]+)\.supabase\.co/) || [])[1] || KNOWN.supabaseRef;
  const onPi = typeof window !== 'undefined' && window.location.hostname === KNOWN.hotspotIp;
  const secure = typeof window !== 'undefined' && window.isSecureContext;
  const seen = net?.at ? `last seen ${new Date(net.at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'not seen from this device yet';

  return <section className="panel cx">
    <div className="section-head"><div><h2>Connections</h2><p className="muted">Where MapPI3 lives and how to reach it. Green = answering now.</p></div><button type="button" className="ghost small" onClick={refresh} disabled={checking}>{checking ? 'Checking…' : 'Check again'}</button></div>

    <h3>MapPI3 Pi</h3>
    <Row label="Hotspot Wi-Fi" value={KNOWN.hotspotSsid} note="Password: the one set on the Pi (not stored in the app)." />
    <Row label="Pi address (hotspot)" value={KNOWN.hotspotIp} status={piOnline ? 'on' : 'off'} note={piOnline ? 'the Pi is answering this app' : seen} />
    <Row label="Pi app" value={`http://${KNOWN.hotspotIp}:${KNOWN.piPort}`} href={`http://${KNOWN.hotspotIp}:${KNOWN.piPort}`} status={piOnline ? 'on' : 'off'} />
    <Row label="SSH" value={`ssh ${KNOWN.piUser}@${KNOWN.hotspotIp}`} note="Key login only." />
    <Row label="Pi Tailscale IP" value={tsIps[0] || 'unknown yet'} status={ts.online ? 'on' : tsIps.length ? 'off' : undefined} note={tsIps.length ? `${ts.online ? 'online' : 'offline'} · ${seen}` : 'Shows once the app has reached the Pi (join the hotspot and tap Check again).'} />
    {tsDns && <Row label="Pi Tailscale name" value={tsDns} note={`Pi app over Tailscale: http://${tsDns}:${KNOWN.piPort}`} />}

    <h3>Online</h3>
    <Row label="Web app (Vercel)" value={KNOWN.vercel} href={KNOWN.vercel} status={typeof window !== 'undefined' && window.location.host === new URL(KNOWN.vercel).host ? 'on' : undefined} note="HTTPS: phone GPS, camera and compass work here." />
    <Row label="Supabase" value={supaUrl} href={`https://supabase.com/dashboard/project/${ref}`} status={cloud ? (cloud.ok ? 'on' : 'off') : undefined} note={cloud ? (cloud.ok ? 'account server online' : cloud.reason === 'not-configured' ? 'not set up in this build' : 'not responding (paused or offline)') : 'checking…'} />
    <Row label="GitHub" value={KNOWN.github} href={KNOWN.github} />
    <Row label="Garden VM (Tailscale)" value={KNOWN.garden.ip} note={`${KNOWN.garden.dns} · dev server ${KNOWN.garden.https}`} />

    <h3>How to connect</h3>
    <ol className="cx-steps">
      <li><b>On the trail (no internet):</b> join the <code>{KNOWN.hotspotSsid}</code> Wi-Fi on your phone, then open <code>http://{KNOWN.hotspotIp}:{KNOWN.piPort}</code>. If the phone warns “no internet”, choose to stay connected.</li>
      <li><b>Phone GPS, camera and pulse check</b> need HTTPS. Plan at home on <code>{KNOWN.vercel.replace('https://', '')}</code> while online; on the Pi page the Pi's own GPS is used instead.</li>
      <li><b>Bluetooth:</b> Settings → Bluetooth shows the Pi's Bluetooth link and lets you pair the phone for internet sharing.</li>
      <li><b>From home:</b> when the Pi is on Tailscale, use its Tailscale address above from any of your devices.</li>
      <li><b>From the PC:</b> join the hotspot and run <code>ssh {KNOWN.piUser}@{KNOWN.hotspotIp}</code>.</li>
    </ol>
    <p className="muted cx-now">This device: {onPi ? 'on the Pi hotspot page' : typeof window !== 'undefined' ? window.location.host : ''} · {secure ? 'secure (HTTPS or localhost)' : 'not secure: phone GPS and camera are blocked here'}</p>
  </section>;
}
