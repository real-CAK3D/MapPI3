# MapPI3 Supabase free-plan sync guardrails

MapPI3 should stay offline-first. Supabase is for optional sync/public notes, not live telemetry streaming.

## Tables planned

- `mappi3_sync_records` — generic plugin/device records, batched and deduped.
- `mappi3_public_notes` — AI/wiki-style correction notes for public fact-checking.
- `mappi3_public_note_votes` — one vote per note per device.
- `mappi3_plugin_catalog` — lightweight plugin/theme catalog metadata.

Schema file: `docs/supabase-sync-public-notes-schema.sql`.

## Free-plan friendly write rules

- Do not upload every GPS tick.
- Do not upload raw camera/video/audio by default.
- Batch route traces into summaries or compressed route packs.
- Write on user action: save route, publish note, vote, sync now, end hike.
- Cache reads locally and refresh on demand or at most every 15–60 minutes.
- Keep NOAA/weather live fetching on the Pi/cache side, not through Supabase.
- Public notes should be small text + metadata; images/model training sets need Storage quotas or later paid plan.

## Suggested monthly-safe caps per device

- Public AI corrections: 50/day max locally queued, sync latest when online.
- Votes: 200/day max, dedupe by `note_id + device_id`.
- Route/history sync: 20/day unless explicitly exporting.
- Plugin catalog refresh: daily or manual.
- Weather/public note reads: cached; manual refresh button preferred.

## Sync behavior

1. App writes locally first.
2. Queue records with a dedupe key.
3. When online, push a small batch.
4. Mark synced locally.
5. If Supabase fails or rate-limits, keep local data and retry later with backoff.

## Safety / quality

Public correction notes are user claims. The app should display them as community notes/fact-checks beneath default AI output, not as verified truth unless reviewed/upvoted/trusted later. Field safety warnings remain primary: MapPI3 assists but does not replace expert ID, maps, emergency services, or local regulations.
