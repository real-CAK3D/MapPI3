// Browser stand-in for Node's "util", for @meshtastic/core's logger.
const show = a => { if (typeof a === 'string') return a; if (a instanceof Error) return a.stack || a.message; try { return JSON.stringify(a); } catch { return String(a); } };
export const formatWithOptions = (_opts, ...args) => args.map(show).join(' ');
export const inspect = a => show(a);
export const types = new Proxy({ isError: e => e instanceof Error, isPromise: p => p instanceof Promise, isDate: d => d instanceof Date, isRegExp: r => r instanceof RegExp }, { get: (t, k) => t[k] || (() => false) });
export default { formatWithOptions, inspect, types };
