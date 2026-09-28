// Browser stand-in for Node's "path", for @meshtastic/core's logger.
export const normalize = p => String(p ?? '');
export default { normalize };
