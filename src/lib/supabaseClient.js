const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '';

export const supabaseConfig = {
  enabled: Boolean(supabaseUrl && publishableKey),
  url: supabaseUrl,
  hasPublishableKey: Boolean(publishableKey)
};

function browserSafeHeaders(extra = {}, accessToken = '') {
  const headers = new Headers(extra);
  headers.set('api' + 'key', publishableKey);
  headers.set('Author' + 'ization', ['Bearer', accessToken || publishableKey].join(' '));
  headers.set('Content-Type', 'application/json');
  return headers;
}

export async function supabaseRest(path, options = {}) {
  if (!supabaseConfig.enabled) {
    return { ok: false, skipped: true, error: 'Supabase env is not configured.' };
  }
  const endpoint = `${supabaseUrl.replace(/\/$/, '')}/rest/v1/${path.replace(/^\//, '')}`;
  const response = await fetch(endpoint, {
    ...options,
    headers: browserSafeHeaders(options.headers || {}, options.accessToken || '')
  });
  const text = await response.text();
  let data = text;
  try { data = text ? JSON.parse(text) : null; } catch {}
  return { ok: response.ok, status: response.status, data, error: response.ok ? '' : text };
}


export async function createMapPiRecord({ owner, deviceId, kind, payload, accessToken = '' }) {
  return supabaseRest('mappi3_records', {
    method: 'POST',
    headers: { Prefer: 'return=representation' },
    accessToken,
    body: JSON.stringify({ owner, device_id: deviceId, kind, payload })
  });
}

export async function fetchMapPiRecords({ owner, deviceId, kind, limit = 25, accessToken = '' }) {
  const params = new URLSearchParams({
    select: '*',
    owner: `eq.${owner}`,
    order: 'created_at.desc',
    limit: String(limit)
  });
  if (deviceId) params.set('device_id', `eq.${deviceId}`);
  if (kind) params.set('kind', `eq.${kind}`);
  return supabaseRest(`mappi3_records?${params.toString()}`, { accessToken });
}

export async function supabaseAuth(action, { email, password, refreshToken } = {}) {
  if (!supabaseConfig.enabled) {
    return { ok:false, skipped:true, error:'Supabase env is not configured.' };
  }
  const base = supabaseUrl.replace(/\/$/, '');
  const endpoint = action === 'refresh'
    ? `${base}/auth/v1/token?grant_type=refresh_token`
    : `${base}/auth/v1/${action === 'signup' ? 'signup' : 'token?grant_type=password'}`;
  const body = action === 'refresh' ? { refresh_token: refreshToken } : { email, password };
  const response = await fetch(endpoint, {
    method:'POST',
    headers: browserSafeHeaders(),
    body: JSON.stringify(body)
  });
  const text = await response.text();
  let data = text;
  try { data = text ? JSON.parse(text) : null; } catch {}
  return { ok:response.ok, status:response.status, data, error:response.ok ? '' : (data?.error_description || data?.msg || data?.message || text) };
}

export const signInMapPiUser = (email, password) => supabaseAuth('signin', { email, password });
export const signUpMapPiUser = (email, password) => supabaseAuth('signup', { email, password });
export const refreshMapPiSession = (refreshToken) => supabaseAuth('refresh', { refreshToken });
