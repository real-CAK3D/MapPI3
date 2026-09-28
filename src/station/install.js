// "Install app": Chrome/Edge/Samsung Internet hand the page an install prompt it can show on request.
// We catch it early (before React renders) and keep it for the Install buttons.
import { useEffect, useState } from 'react';

let deferred = null;
const listeners = new Set();
const notify = () => listeners.forEach(fn => fn({ canPrompt: !!deferred, installed: isInstalled() }));
export const isInstalled = () => typeof window !== 'undefined' && (window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true);

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferred = e; notify(); });
  window.addEventListener('appinstalled', () => { deferred = null; notify(); });
}

export async function promptInstall() {
  if (!deferred) return 'unavailable';
  deferred.prompt();
  const choice = await deferred.userChoice.catch(() => ({ outcome: 'dismissed' }));
  deferred = null; notify();
  return choice.outcome; // 'accepted' | 'dismissed'
}

export function useInstall() {
  const [s, set] = useState({ canPrompt: !!deferred, installed: isInstalled() });
  useEffect(() => { listeners.add(set); return () => listeners.delete(set); }, []);
  return s;
}

// What to tap when the browser cannot show the prompt itself.
export function installSteps() {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  if (/iPhone|iPad|iPod/.test(ua)) return 'In Safari, tap Share, then "Add to Home Screen".';
  if (/SamsungBrowser/.test(ua)) return 'Tap the menu (☰), then "Add page to" → "Home screen".';
  if (/Android/.test(ua)) return 'In Chrome, tap the ⋮ menu, then "Add to Home screen" or "Install app".';
  if (!window.isSecureContext) return 'Open the https app (map-pi3.vercel.app) to install it; the Pi hotspot page cannot be installed.';
  return 'In Chrome or Edge, use the install icon in the address bar, or the ⋮ menu → "Install MapPI3".';
}
