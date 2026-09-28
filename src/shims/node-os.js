// Browser stand-in for Node's "os", for @meshtastic/core's logger.
export const hostname = () => 'browser';
export default { hostname };
