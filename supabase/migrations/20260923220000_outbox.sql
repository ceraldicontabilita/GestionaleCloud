-- Outbox transazionale (RST-0510). Non e' un documento aziendale: vive
-- fuori da gestionale.documents. Le RPC usano il segreto runtime.

begin;

create table if not exists gestionale.outbox_events (
  id text primary key,
  event_type text not null,
  entity_id text not null default '',
  entity_version integer not null default 1,
  payload jsonb not null default '{}'::jsonb,
  payload_version integer not null default 1,
  idempotency_key text not null,
  source_module text not null default '',
  actor text not null default 'sistema',
  created_at timestamptz not null default now(),
  unique (idempotency_key)
);

create table if not exists gestionale.outbox_deliveries (
  event_id text not null references gestionale.outbox_events(id) on delete restrict,
  consumer text not null,
  stato text not null default 'pending'
    check (stato in ('pending', 'processing', 'done', 'error', 'non_applicabile')),
  tentativi integer not null default 0,
  errore text,
  leased_until timestamptz,
  updated_at timestamptz not null default now(),
  primary key (event_id, consumer)
);

create index if not exists outbox_deliveries_pending_idx
  on gestionale.outbox_deliveries (stato, leased_until)
  where stato in ('pending', 'error', 'processing');

alter table gestionale.outbox_events enable row level security;
alter table gestionale.outbox_deliveries enable row level security;
revoke all on table gestionale.outbox_events
  from public, anon, authenticated, service_role;
revoke all on table gestionale.outbox_deliveries
  from public, anon, authenticated, service_role;

create or replace function public.gc_outbox_enqueue(
  p_id text,
  p_event_type text,
  p_entity_id text,
  p_entity_version integer,
  p_payload jsonb,
  p_payload_version integer,
  p_idempotency_key text,
  p_source_module text,
  p_actor text,
  p_consumers text[]
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  existing_id text;
  consumer text;
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_id), '') = '' or coalesce(btrim(p_event_type), '') = ''
     or coalesce(btrim(p_idempotency_key), '') = '' then
    raise invalid_parameter_value using message = 'id, event_type e idempotency_key obbligatori';
  end if;

  insert into gestionale.outbox_events (
    id, event_type, entity_id, entity_version, payload, payload_version,
    idempotency_key, source_module, actor
  ) values (
    p_id, p_event_type, coalesce(p_entity_id, ''), coalesce(p_entity_version, 1),
    coalesce(p_payload, '{}'::jsonb), coalesce(p_payload_version, 1),
    p_idempotency_key, coalesce(p_source_module, ''), coalesce(p_actor, 'sistema')
  )
  on conflict (idempotency_key) do nothing;

  select id into existing_id
  from gestionale.outbox_events
  where idempotency_key = p_idempotency_key;

  if p_consumers is not null then
    foreach consumer in array p_consumers loop
      if coalesce(btrim(consumer), '') = '' then
        continue;
      end if;
      insert into gestionale.outbox_deliveries (event_id, consumer, stato)
      values (existing_id, consumer, 'pending')
      on conflict (event_id, consumer) do nothing;
    end loop;
  end if;

  return jsonb_build_object('id', existing_id, 'duplicato', existing_id is distinct from p_id);
end;
$function$;

create or replace function public.gc_outbox_claim(
  p_limit integer default 25,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare
  claimed jsonb;
begin
  perform public.gc_assert_runtime_secret();
  if p_limit < 1 or p_limit > 200 then
    raise invalid_parameter_value using message = 'limit outbox non valido';
  end if;
  if p_lease_seconds < 30 or p_lease_seconds > 900 then
    raise invalid_parameter_value using message = 'lease outbox non valida';
  end if;

  with candidati as (
    select d.event_id, d.consumer
    from gestionale.outbox_deliveries d
    where d.stato in ('pending', 'error')
       or (d.stato = 'processing' and (d.leased_until is null or d.leased_until <= now()))
    order by d.updated_at
    for update skip locked
    limit p_limit
  ),
  aggiornati as (
    update gestionale.outbox_deliveries d
    set stato = 'processing',
        leased_until = now() + make_interval(secs => p_lease_seconds),
        tentativi = d.tentativi + 1,
        updated_at = now()
    from candidati c
    where d.event_id = c.event_id and d.consumer = c.consumer
    returning d.event_id, d.consumer, d.tentativi
  )
  select coalesce(jsonb_agg(jsonb_build_object(
    'event_id', a.event_id,
    'consumer', a.consumer,
    'tentativi', a.tentativi,
    'event_type', e.event_type,
    'entity_id', e.entity_id,
    'entity_version', e.entity_version,
    'payload', e.payload,
    'payload_version', e.payload_version,
    'idempotency_key', e.idempotency_key,
    'source_module', e.source_module,
    'actor', e.actor
  )), '[]'::jsonb)
  into claimed
  from aggiornati a
  join gestionale.outbox_events e on e.id = a.event_id;

  return claimed;
end;
$function$;

create or replace function public.gc_outbox_ack(
  p_event_id text,
  p_consumer text,
  p_stato text,
  p_errore text default null
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
  if p_stato not in ('done', 'error', 'non_applicabile', 'pending') then
    raise invalid_parameter_value using message = 'stato outbox non valido';
  end if;
  update gestionale.outbox_deliveries
  set stato = p_stato,
      errore = case when p_stato = 'error' then left(coalesce(p_errore, ''), 500) else null end,
      leased_until = null,
      updated_at = now()
  where event_id = p_event_id and consumer = p_consumer;
  get diagnostics affected = row_count;
  return affected = 1;
end;
$function$;

revoke all on function public.gc_outbox_enqueue(text, text, text, integer, jsonb, integer, text, text, text, text[])
  from public, anon, authenticated;
revoke all on function public.gc_outbox_claim(integer, integer)
  from public, anon, authenticated;
revoke all on function public.gc_outbox_ack(text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.gc_outbox_enqueue(text, text, text, integer, jsonb, integer, text, text, text, text[])
  to anon, service_role;
grant execute on function public.gc_outbox_claim(integer, integer)
  to anon, service_role;
grant execute on function public.gc_outbox_ack(text, text, text, text)
  to anon, service_role;

notify pgrst, 'reload schema';

commit;
