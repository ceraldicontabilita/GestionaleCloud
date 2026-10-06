-- Fondazione enterprise: outbox transazionale delle proiezioni tra domini.
-- La tabella e' privata; l'applicazione accede soltanto tramite RPC protette
-- dalla stessa runtime secret del document store.

begin;

create table if not exists gestionale.domain_outbox (
  id uuid primary key default extensions.gen_random_uuid(),
  event_type text not null,
  aggregate_type text not null,
  aggregate_id text not null,
  source_version text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  locked_at timestamptz,
  lock_token uuid,
  processed_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (event_type, aggregate_type, aggregate_id, source_version)
);

create index if not exists domain_outbox_ready_idx
  on gestionale.domain_outbox (available_at, created_at)
  where status in ('pending', 'failed');

alter table gestionale.domain_outbox enable row level security;
revoke all on table gestionale.domain_outbox from public, anon, authenticated, service_role;

create or replace function gestionale.tg_invoice_projection_outbox()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, gestionale, extensions
as $$
declare
  v_source_version text;
begin
  if new.collection <> 'invoices'
     or coalesce(new.data->>'entity_status', '') = 'deleted'
     or lower(coalesce(new.data->>'status', '')) in ('archived', 'deleted')
     or lower(coalesce(new.data->>'stato_import', '')) = 'archivio_storico'
     or lower(coalesce(new.data->>'duplicate_review_required', 'false')) = 'true' then
    return new;
  end if;

  v_source_version := coalesce(
    nullif(new.data->>'content_hash', ''),
    encode(extensions.digest(convert_to(new.data::text, 'UTF8'), 'sha256'), 'hex')
  );

  insert into gestionale.domain_outbox (
    event_type, aggregate_type, aggregate_id, source_version, payload
  ) values (
    'invoice.project', 'invoice', new.id, v_source_version,
    jsonb_build_object(
      'source_id', new.id,
      'content_hash', v_source_version,
      'updated_at', new.updated_at
    )
  )
  on conflict (event_type, aggregate_type, aggregate_id, source_version) do nothing;
  return new;
end;
$$;

drop trigger if exists invoices_projection_outbox on gestionale.documents;
create trigger invoices_projection_outbox
  after insert or update on gestionale.documents
  for each row execute function gestionale.tg_invoice_projection_outbox();

create or replace function public.gc_outbox_claim(p_limit integer default 20)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, gestionale, public, extensions
as $$
declare
  v_result jsonb;
begin
  perform public.gc_assert_runtime_secret();

  update gestionale.domain_outbox
     set status = 'failed', available_at = now(), lock_token = null,
         locked_at = null, last_error = 'lease_scaduta', updated_at = now()
   where status = 'processing' and locked_at < now() - interval '15 minutes';

  with candidates as (
    select id from gestionale.domain_outbox
     where status in ('pending', 'failed') and attempts < 10 and available_at <= now()
     order by available_at, created_at
     for update skip locked
     limit greatest(1, least(coalesce(p_limit, 20), 100))
  ), claimed as (
    update gestionale.domain_outbox o
       set status = 'processing', attempts = o.attempts + 1,
           locked_at = now(), lock_token = extensions.gen_random_uuid(), updated_at = now()
      from candidates c where o.id = c.id
     returning o.id, o.event_type, o.aggregate_type, o.aggregate_id,
               o.source_version, o.payload, o.attempts, o.lock_token
  )
  select coalesce(jsonb_agg(to_jsonb(claimed)), '[]'::jsonb)
    into v_result from claimed;
  return v_result;
end;
$$;

create or replace function public.gc_outbox_complete(p_event_id uuid, p_lock_token uuid)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, gestionale, public
as $$
begin
  perform public.gc_assert_runtime_secret();
  update gestionale.domain_outbox
     set status = 'completed', processed_at = now(), updated_at = now(),
         locked_at = null, lock_token = null, last_error = null
   where id = p_event_id and status = 'processing' and lock_token = p_lock_token;
  return found;
end;
$$;

create or replace function public.gc_outbox_fail(
  p_event_id uuid, p_lock_token uuid, p_error text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, gestionale, public
as $$
begin
  perform public.gc_assert_runtime_secret();
  update gestionale.domain_outbox
     set status = 'failed',
         available_at = now() + make_interval(secs => least(900, 15 * power(2, least(attempts, 6))::integer)),
         updated_at = now(), locked_at = null, lock_token = null,
         last_error = left(coalesce(p_error, 'errore_non_specificato'), 1000)
   where id = p_event_id and status = 'processing' and lock_token = p_lock_token;
  return found;
end;
$$;

revoke all on function public.gc_outbox_claim(integer) from public;
revoke all on function public.gc_outbox_complete(uuid, uuid) from public;
revoke all on function public.gc_outbox_fail(uuid, uuid, text) from public;
grant execute on function public.gc_outbox_claim(integer) to anon, service_role;
grant execute on function public.gc_outbox_complete(uuid, uuid) to anon, service_role;
grant execute on function public.gc_outbox_fail(uuid, uuid, text) to anon, service_role;

notify pgrst, 'reload schema';

commit;
