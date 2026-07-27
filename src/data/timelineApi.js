const TIMELINE_HEADERS = { 'Content-Type': 'application/json' };

async function timelineJson(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data?.ok === false) {
    throw new Error(data?.error || data?.message || `MapPI3 timeline API failed: ${response.status}`);
  }
  return data;
}

function qs(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : '';
}

export const timelineApi = {
  listTrips: () => timelineJson('/api/trips'),
  startTrip: (payload = {}) => timelineJson('/api/trips/start', { method: 'POST', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  pauseTrip: (tripId, payload = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/pause`, { method: 'POST', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  resumeTrip: (tripId, payload = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/resume`, { method: 'POST', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  endTrip: (tripId, payload = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/end`, { method: 'POST', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  loadTimeline: (tripId, params = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/timeline${qs(params)}`),
  stateAt: (tripId, timestamp) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/state-at${qs({ timestamp })}`),
  search: (tripId, query) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/timeline/search${qs({ query })}`),
  getEvent: (tripId, eventId) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/events/${encodeURIComponent(eventId)}`),
  addEvent: (tripId, payload = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/events`, { method: 'POST', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  patchEvent: (tripId, eventId, payload = {}) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/events/${encodeURIComponent(eventId)}`, { method: 'PATCH', headers: TIMELINE_HEADERS, body: JSON.stringify(payload) }),
  deleteEvent: (tripId, eventId) => timelineJson(`/api/trips/${encodeURIComponent(tripId)}/events/${encodeURIComponent(eventId)}`, { method: 'DELETE' }),
};

export default timelineApi;
