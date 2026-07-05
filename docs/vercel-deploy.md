# Vercel Deploy Notes

MapPI3 is a Vite app. Vercel settings:

- Framework preset: Vite
- Install command: `npm install`
- Build command: `npm run build`
- Output directory: `dist`

Environment variables for browser Supabase wiring:

```text
VITE_SUPABASE_URL
VITE_SUPABASE_PUBLISHABLE_KEY
```

Do not add database passwords, Supabase secret keys, JWT secrets, or GitHub tokens to the client build.

After deployment, verify:

```bash
npm run build
npm run smoke
```

Then test the live URL on a phone: empty search prompt, `table rock`, `speck pond`, Account setup, Settings sync readiness, and GPS permission behavior over HTTPS.


## Production URL

Vercel URL: https://map-pi3.vercel.app

Add these Vercel environment variables before testing cloud sync:

```text
VITE_SUPABASE_URL=https://adbsxppzotasctjdiwgc.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable key only>
```

The Supabase table `public.mappi3_records` has been applied. Account > Sync device settings and Navigate > Mark trail complete write local-first records to Supabase when those browser env vars are present in the deployed build.
