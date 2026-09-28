import React, { useState } from 'react';
import { installSteps, promptInstall, useInstall } from './install.js';

// Put MapPI3 on the home screen like a normal app. `banner` is the small dismissible version for Home.
export default function InstallApp({ banner = false }) {
  const { canPrompt, installed } = useInstall();
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem('mappi3.installBannerHidden') === '1'; } catch { return false; } });
  const [msg, setMsg] = useState('');
  if (installed) return banner ? null : <div className="install-card st-card"><b>Installed</b><p className="muted">MapPI3 is on this device's home screen.</p></div>;
  if (banner && (hidden || !canPrompt)) return null;
  const install = async () => { const out = await promptInstall(); setMsg(out === 'accepted' ? 'Installing… look for MapPI3 on your home screen.' : out === 'dismissed' ? 'Not installed. You can do it any time from here.' : installSteps()); };
  const hide = () => { setHidden(true); try { localStorage.setItem('mappi3.installBannerHidden', '1'); } catch { /* optional */ } };
  return <div className={`install-card st-card ${banner ? 'banner' : ''}`}>
    <img src="/icon-192.png" alt="" width="44" height="44" />
    <div className="install-text"><b>Add MapPI3 to your home screen</b><p className="muted">{canPrompt ? 'Opens full screen like a normal app, and works offline on the trail.' : installSteps()}</p>{msg && <p className="install-msg">{msg}</p>}</div>
    <div className="install-actions">
      {canPrompt && <button type="button" className="primary small" onClick={install}>Install app</button>}
      {banner && <button type="button" className="ghost small" onClick={hide}>Not now</button>}
    </div>
  </div>;
}
