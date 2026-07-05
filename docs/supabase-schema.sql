-- MapPi3 starter Supabase schema.
-- Applied to project adbsxppzotasctjdiwgc on 2026-07-05. Do not put database passwords or secret keys in the app repo.

create table if not exists public.mappi3_records (
  id uuid primary key default gen_random_uuid(),
  owner text not null check (owner in ('CAK3D', 'tiny-Z', 'Guest')),
  device_id text,
  kind text not null check (kind in ('completed_trail', 'route_pack', 'device_settings', 'hike_plan', 'walk_trace')),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.mappi3_records enable row level security;

-- Temporary local-first policy for publishable-key prototyping.
-- Tighten this once Supabase Auth identities replace local device accounts.
drop policy if exists "MapPi3 public prototype read" on public.mappi3_records;
create policy "MapPi3 public prototype read"
  on public.mappi3_records for select
  using (true);

drop policy if exists "MapPi3 public prototype insert" on public.mappi3_records;
create policy "MapPi3 public prototype insert"
  on public.mappi3_records for insert
  with check (true);

drop policy if exists "MapPi3 public prototype update own device" on public.mappi3_records;
create policy "MapPi3 public prototype update own device"
  on public.mappi3_records for update
  using (true)
  with check (true);

create index if not exists mappi3_records_owner_kind_idx on public.mappi3_records(owner, kind, created_at desc);
create index if not exists mappi3_records_payload_gin_idx on public.mappi3_records using gin(payload);
