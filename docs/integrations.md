# GitHub, Supabase, and Vercel Readiness

## GitHub

This workspace is initialized as a local Git repo. Do not push until CAK3D picks the remote owner/repo. Future CI should run:

```bash
npm ci
npm run build
npm run smoke
```

## Supabase

Frontend should use only browser-safe values:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_PUBLISHABLE_KEY`

Never commit service-role keys, database passwords, JWT secrets, PATs, or management tokens. Privileged actions belong in Supabase Edge Functions or a later Vercel server boundary.

Suggested first table later: generic local-first records with device id, kind, payload JSON, timestamps, and sync status.

## Vercel

Vercel can eventually host a companion version of the app for planning/admin/sync. The Pi hotspot version remains the primary hiking mode. Environment variables on Vercel should mirror `.env.example` with only browser-safe public values.
