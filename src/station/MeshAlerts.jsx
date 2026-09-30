import React, { useEffect, useState } from 'react';
import { onNewMessage, startPi } from './mesh.js';

// App-wide mesh alerts: a popup on any screen when a Meshtastic message arrives, red + vibration for
// alerts (SOS, bell), and a phone notification when the app is in the background (if allowed).
export default function MeshAlerts({ piConnected = false, onOpen }) {
  const [toast, setToast] = useState(null);
  useEffect(() => { if (piConnected) startPi(); }, [piConnected]);
  useEffect(() => onNewMessage(m => {
    setToast(m);
    if (m.alert && navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 600]);
    else if (navigator.vibrate) navigator.vibrate(120);
    try {
      if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
        const n = new Notification(m.alert ? `ALERT from ${m.fromName || m.from}` : `Mesh · ${m.fromName || m.from}`, { body: m.text, tag: `mesh-${m.id}`, icon: '/icon-192.png', requireInteraction: !!m.alert });
        n.onclick = () => { window.focus(); onOpen && onOpen(); n.close(); };
      }
    } catch { /* notifications are optional */ }
  }), [onOpen]);
  useEffect(() => { if (!toast) return undefined; const t = setTimeout(() => setToast(null), toast.alert ? 30000 : 9000); return () => clearTimeout(t); }, [toast]);
  if (!toast) return null;
  return <div className={`mesh-toast ${toast.alert ? 'alert' : ''}`} role={toast.alert ? 'alert' : 'status'}>
    <div><b>{toast.alert ? 'ALERT · ' : toast.direct ? 'Direct · ' : 'Mesh · '}{toast.fromName || toast.from}</b><span>{toast.text}</span></div>
    <button type="button" className="primary small" onClick={() => { setToast(null); onOpen && onOpen(); }}>Open</button>
    <button type="button" className="ghost small" aria-label="Dismiss" onClick={() => setToast(null)}>×</button>
  </div>;
}
