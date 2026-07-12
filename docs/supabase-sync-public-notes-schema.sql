-- MapPI3 optional sync/public notes schema extension.
-- Designed for Supabase free plan: batch sync, offline-first app behavior, modest indexes, and no high-frequency writes.
-- Apply manually after approval in the Supabase SQL editor or Management API.

-- Per-device/plugin records for local-first sync. Avoid writing every GPS tick; store summaries/batches.
create table if not exists public.mappi3_sync_records (
  id uuid primary key default gen_random_uuid(),
  owner text not null default 'Guest',
  device_id text,
  plugin_id text not null,
  record_type text not null,
  dedupe_key text,
  payload jsonb not null default '{}'::jsonb,
  public boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(plugin_id, record_type, dedupe_key)
);

-- Public AI/wiki fact-check notes. Client may insert candidate notes; moderation/trust can come later.
create table if not exists public.mappi3_public_notes (
  id uuid primary key default gen_random_uuid(),
  subject_key text not null,
  category text not null,
  ai_guess text,
  correction text not null,
  evidence text,
  source text not null default 'user',
  owner text not null default 'Guest',
  device_id text,
  status text not null default 'candidate' check (status in ('candidate','verified','rejected','hidden')),
  upvotes integer not null default 0,
  downvotes integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- One vote per device per public note to reduce accidental spam on free tier.
create table if not exists public.mappi3_public_note_votes (
  note_id uuid not null references public.mappi3_public_notes(id) on delete cascade,
  device_id text not null,
  vote smallint not null check (vote in (-1, 1)),
  created_at timestamptz not null default now(),
  primary key(note_id, device_id)
);

-- Plugin/theme package catalog cache. Keeps GitHub/plugin metadata lightweight in app.
create table if not exists public.mappi3_plugin_catalog (
  plugin_id text primary key,
  category text not null,
  name text not null,
  version text not null default '0.1.0',
  targets text[] not null default array[]::text[],
  manifest jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

alter table public.mappi3_sync_records enable row level security;
alter table public.mappi3_public_notes enable row level security;
alter table public.mappi3_public_note_votes enable row level security;
alter table public.mappi3_plugin_catalog enable row level security;

-- Prototype policies for publishable-key local-first mode. Tighten after Supabase Auth/Edge Functions.
drop policy if exists "MapPI3 sync public read" on public.mappi3_sync_records;
create policy "MapPI3 sync public read" on public.mappi3_sync_records for select using (public = true or owner in ('CAK3D','tiny-Z','Guest'));
drop policy if exists "MapPI3 sync insert candidate" on public.mappi3_sync_records;
create policy "MapPI3 sync insert candidate" on public.mappi3_sync_records for insert with check (true);
drop policy if exists "MapPI3 sync update prototype" on public.mappi3_sync_records;
create policy "MapPI3 sync update prototype" on public.mappi3_sync_records for update using (true) with check (true);

drop policy if exists "MapPI3 notes public read" on public.mappi3_public_notes;
create policy "MapPI3 notes public read" on public.mappi3_public_notes for select using (status <> 'hidden');
drop policy if exists "MapPI3 notes insert candidate" on public.mappi3_public_notes;
create policy "MapPI3 notes insert candidate" on public.mappi3_public_notes for insert with check (status = 'candidate');
drop policy if exists "MapPI3 notes update prototype" on public.mappi3_public_notes;
create policy "MapPI3 notes update prototype" on public.mappi3_public_notes for update using (true) with check (true);

drop policy if exists "MapPI3 votes public read" on public.mappi3_public_note_votes;
create policy "MapPI3 votes public read" on public.mappi3_public_note_votes for select using (true);
drop policy if exists "MapPI3 votes insert" on public.mappi3_public_note_votes;
create policy "MapPI3 votes insert" on public.mappi3_public_note_votes for insert with check (true);
drop policy if exists "MapPI3 votes update own prototype" on public.mappi3_public_note_votes;
create policy "MapPI3 votes update own prototype" on public.mappi3_public_note_votes for update using (true) with check (true);

drop policy if exists "MapPI3 plugin catalog read" on public.mappi3_plugin_catalog;
create policy "MapPI3 plugin catalog read" on public.mappi3_plugin_catalog for select using (enabled = true);

create index if not exists mappi3_sync_records_plugin_type_idx on public.mappi3_sync_records(plugin_id, record_type, updated_at desc);
create index if not exists mappi3_sync_records_payload_gin_idx on public.mappi3_sync_records using gin(payload);
create index if not exists mappi3_public_notes_subject_idx on public.mappi3_public_notes(subject_key, category, status, created_at desc);
create index if not exists mappi3_public_notes_votes_idx on public.mappi3_public_notes((upvotes - downvotes) desc, created_at desc);

insert into public.mappi3_plugin_catalog(plugin_id, category, name, version, targets, manifest)
values
('nature-organic-theme','themes','Nature Organic Theme','0.1.0',array['Pi Zero 2 WH','Pi 5'], '{"install":"plugins/nature-organic-theme/install.sh","theme":"Nature Organic"}'::jsonb),
('noaa-weather','weather','NOAA/weather data pack','0.1.0',array['Pi Zero 2 WH','Pi 5'], '{"endpoint":"/api/noaa-weather","cache":"/var/lib/mappi3/noaa-weather-cache.json"}'::jsonb),
('media-library','media','Music + video library','0.1.0',array['Pi Zero 2 WH','Pi 5'], '{"endpoint":"/api/media/library","root":"/var/lib/mappi3/media"}'::jsonb)
on conflict (plugin_id) do update set category=excluded.category,name=excluded.name,version=excluded.version,targets=excluded.targets,manifest=excluded.manifest,updated_at=now();
