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

Do not add database passwords, `sb_secret_*`, JWT secrets, or GitHub tokens to the client build.

After deployment, verify:

```bash
npm run build
npm run smoke
```

Then test the live URL on a phone: empty search prompt, `table rock`, `speck pond`, Account setup, Settings sync readiness, and GPS permission behavior over HTTPS.
