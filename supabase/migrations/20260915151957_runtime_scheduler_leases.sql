-- Lease tecniche distribuite per impedire che due istanze Render eseguano lo
-- stesso scheduler durante un rolling deploy. Non sono documenti aziendali e
-- quindi vivono fuori da gestionale.documents.

begin;

create table if not exists gestionale.runtime_scheduler_leases (
  job_id text primary key,
  owner_id text not null,
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

alter table gestionale.runtime_scheduler_leases enable row level security;
revoke all on table gestionale.runtime_scheduler_leases
  from public, anon, authenticated, service_role;

create or replace function public.gc_try_scheduler_lease(
  p_job_id text,
  p_owner_id text,
  p_ttl_seconds integer default 900
)
returns boolean
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  affected integer := 0;
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_job_id), '') = '' or coalesce(btrim(p_owner_id), '') = '' then
    raise invalid_parameter_value using message = 'job_id e owner_id obbligatori';
  end if;
  if p_ttl_seconds < 60 or p_ttl_seconds > 21600 then
    raise invalid_parameter_value using message = 'ttl scheduler non valido';
  end if;

  insert into gestionale.runtime_scheduler_leases (
    job_id, owner_id, acquired_at, expires_at, updated_at
  ) values (
    p_job_id, p_owner_id, now(), now() + make_interval(secs => p_ttl_seconds), now()
  )
  on conflict (job_id) do update
    set owner_id = excluded.owner_id,
        acquired_at = case
          when gestionale.runtime_scheduler_leases.owner_id = excluded.owner_id
            then gestionale.runtime_scheduler_leases.acquired_at
          else now()
        end,
        expires_at = excluded.expires_at,
        updated_at = now()
    where gestionale.runtime_scheduler_leases.expires_at <= now()
       or gestionale.runtime_scheduler_leases.owner_id = excluded.owner_id;

  get diagnostics affected = row_count;
  return affected = 1;
end;
$function$;

create or replace function public.gc_renew_scheduler_lease(
  p_job_id text,
  p_owner_id text,
  p_ttl_seconds integer default 900
)
returns boolean
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  affected integer := 0;
begin
  perform public.gc_assert_runtime_secret();
  update gestionale.runtime_scheduler_leases
  set expires_at = now() + make_interval(secs => p_ttl_seconds),
      updated_at = now()
  where job_id = p_job_id
    and owner_id = p_owner_id
    and expires_at > now();
  get diagnostics affected = row_count;
  return affected = 1;
end;
$function$;

create or replace function public.gc_release_scheduler_lease(
  p_job_id text,
  p_owner_id text
)
returns boolean
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  affected integer := 0;
begin
  perform public.gc_assert_runtime_secret();
  delete from gestionale.runtime_scheduler_leases
  where job_id = p_job_id and owner_id = p_owner_id;
  get diagnostics affected = row_count;
  return affected = 1;
end;
$function$;

revoke all on function public.gc_try_scheduler_lease(text, text, integer)
  from public, anon, authenticated;
revoke all on function public.gc_renew_scheduler_lease(text, text, integer)
  from public, anon, authenticated;
revoke all on function public.gc_release_scheduler_lease(text, text)
  from public, anon, authenticated;
grant execute on function public.gc_try_scheduler_lease(text, text, integer)
  to anon, service_role;
grant execute on function public.gc_renew_scheduler_lease(text, text, integer)
  to anon, service_role;
grant execute on function public.gc_release_scheduler_lease(text, text)
  to anon, service_role;

notify pgrst, 'reload schema';

commit;
