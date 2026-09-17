-- Presenza del payload nella versione leggera dei documenti.
--
-- Le letture proiettate (senza XML/PDF/foto) alimentano la cache in memoria
-- dell'applicazione. Decine di query filtrano pero' su «ha il PDF» / «senza
-- XML» (pdf_data $exists, $ne null, $nin [null, '']): senza sapere se il campo
-- escluso esiste, l'app doveva rileggere l'intera collezione CON gli allegati.
-- Ogni documento proiettato porta ora `_payload_stato` = {campo: stato} per i
-- campi esclusi, con stato in: assente (chiave mancante), nullo, vuoto
-- (stringa/array/oggetto vuoti), pieno. Il jsonb viene comunque de-toastato
-- per intero dalla proiezione: il calcolo non aggiunge I/O.
-- Le firme delle RPC non cambiano: i client precedenti ricevono una chiave in
-- piu' che l'adattatore nuovo toglie prima di restituire i documenti.

create or replace function public.gc_payload_stato(p_data jsonb, p_fields text[])
returns jsonb
language sql
immutable
set search_path to 'pg_catalog'
as $function$
  select coalesce(jsonb_object_agg(f, case
      when p_data is null or not (p_data ? f) then 'assente'
      when jsonb_typeof(p_data -> f) = 'null' then 'nullo'
      when jsonb_typeof(p_data -> f) = 'string' then
        case when (p_data ->> f) = '' then 'vuoto' else 'pieno' end
      when jsonb_typeof(p_data -> f) = 'array' then
        case when jsonb_array_length(p_data -> f) = 0 then 'vuoto' else 'pieno' end
      when jsonb_typeof(p_data -> f) = 'object' then
        case when (p_data -> f) = '{}'::jsonb then 'vuoto' else 'pieno' end
      else 'pieno' end), '{}'::jsonb)
  from unnest(coalesce(p_fields, array[]::text[])) as f;
$function$;

revoke all on function public.gc_payload_stato(jsonb, text[]) from public, anon, authenticated;

create or replace function public.gc_fetch_collection_projected(
  p_collection text,
  p_offset integer default 0,
  p_limit integer default 100,
  p_exclude_fields text[] default array[]::text[]
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare result jsonb;
declare excl text[] := coalesce(p_exclude_fields, array[]::text[]);
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_offset < 0 or p_limit < 1 or p_limit > 500 then
    raise invalid_parameter_value using message = 'paginazione non valida';
  end if;
  if coalesce(array_length(excl, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.id), '[]'::jsonb)
  into result
  from (
    select d.id,
           (d.data - excl)
             || jsonb_build_object('_id', d.id)
             || case when coalesce(array_length(excl, 1), 0) > 0
                     then jsonb_build_object('_payload_stato', public.gc_payload_stato(d.data, excl))
                     else '{}'::jsonb end as document
    from gestionale.documents d
    where d.collection = p_collection
    order by d.id
    offset p_offset
    limit p_limit
  ) page;
  return result;
end;
$function$;

create or replace function public.gc_fetch_collection_after_projected(
  p_collection text,
  p_after_id text default '',
  p_limit integer default 100,
  p_exclude_fields text[] default array[]::text[]
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare result jsonb;
declare excl text[] := coalesce(p_exclude_fields, array[]::text[]);
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_limit < 1 or p_limit > 500 then
    raise invalid_parameter_value using message = 'paginazione non valida';
  end if;
  if coalesce(array_length(excl, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.id), '[]'::jsonb)
  into result
  from (
    select d.id,
           (d.data - excl)
             || jsonb_build_object('_id', d.id)
             || case when coalesce(array_length(excl, 1), 0) > 0
                     then jsonb_build_object('_payload_stato', public.gc_payload_stato(d.data, excl))
                     else '{}'::jsonb end as document
    from gestionale.documents d
    where d.collection = p_collection
      and (coalesce(p_after_id, '') = '' or d.id > p_after_id)
    order by d.id
    limit p_limit
  ) page;
  return result;
end;
$function$;

create or replace function public.gc_fetch_collection_since(
  p_collection text,
  p_since timestamptz,
  p_offset integer default 0,
  p_limit integer default 500,
  p_exclude_fields text[] default array[]::text[]
)
returns jsonb
language plpgsql
security definer
set search_path to 'pg_catalog'
as $$
declare result jsonb;
declare excl text[] := coalesce(p_exclude_fields, array[]::text[]);
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_offset < 0 or p_limit < 1 or p_limit > 500 then
    raise invalid_parameter_value using message = 'paginazione non valida';
  end if;
  if coalesce(array_length(excl, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.updated_at, page.id), '[]'::jsonb)
  into result
  from (
    select d.id, d.updated_at,
           (d.data - excl)
             || jsonb_build_object('_id', d.id)
             || case when coalesce(array_length(excl, 1), 0) > 0
                     then jsonb_build_object('_payload_stato', public.gc_payload_stato(d.data, excl))
                     else '{}'::jsonb end as document
    from gestionale.documents d
    where d.collection = p_collection
      and (p_since is null or d.updated_at > p_since)
    order by d.updated_at, d.id
    offset p_offset
    limit p_limit
  ) page;
  return result;
end;
$$;
