-- MapPi3 Supabase schema.
-- Original prototype applied to project adbsxppzotasctjdiwgc on 2026-07-05.
-- 2026-07-28 v2: supports real Supabase Auth account owners and compact trip snapshots.
-- Do not put database passwords or secret keys in the app repo.

create table if not exists public.mappi3_records (
  id uuid primary key default gen_random_uuid(),
  owner text not null,
  device_id text,
  kind text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- If upgrading from the early prototype, relax the CAK3D/tiny-Z/Guest and fixed-kind checks.
alter table public.mappi3_records drop constraint if exists mappi3_records_owner_check;
alter table public.mappi3_records drop constraint if exists mappi3_records_kind_check;

alter table public.mappi3_records enable row level security;

-- Public/prototype fallback remains for the current publishable-key static app path.
-- Tighten to auth-only once the Pi and Vercel builds both carry Supabase Auth sessions reliably.
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

-- Auth-aware policies for the new account flow. These coexist with the prototype policies above.
drop policy if exists "MapPi3 auth read own owner" on public.mappi3_records;
create policy "MapPi3 auth read own owner"
  on public.mappi3_records for select
  to authenticated
  using (owner = auth.email() or owner = auth.uid()::text);

drop policy if exists "MapPi3 auth insert own owner" on public.mappi3_records;
create policy "MapPi3 auth insert own owner"
  on public.mappi3_records for insert
  to authenticated
  with check (owner = auth.email() or owner = auth.uid()::text);

drop policy if exists "MapPi3 auth update own owner" on public.mappi3_records;
create policy "MapPi3 auth update own owner"
  on public.mappi3_records for update
  to authenticated
  using (owner = auth.email() or owner = auth.uid()::text)
  with check (owner = auth.email() or owner = auth.uid()::text);

create index if not exists mappi3_records_owner_kind_idx on public.mappi3_records(owner, kind, created_at desc);
create index if not exists mappi3_records_device_idx on public.mappi3_records(device_id, created_at desc);
create index if not exists mappi3_records_payload_gin_idx on public.mappi3_records using gin(payload);
