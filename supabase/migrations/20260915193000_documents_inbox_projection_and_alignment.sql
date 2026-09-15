-- Evita di trasferire gli allegati pesanti quando la pagina chiede una
-- proiezione esclusiva e allinea i badge con un solo UPDATE atomico.

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
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_limit < 1 or p_limit > 500 then
    raise invalid_parameter_value using message = 'paginazione non valida';
  end if;
  if coalesce(array_length(p_exclude_fields, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.id), '[]'::jsonb)
  into result
  from (
    select d.id,
           (d.data - coalesce(p_exclude_fields, array[]::text[]))
             || jsonb_build_object('_id', d.id) as document
    from gestionale.documents d
    where d.collection = p_collection
      and (coalesce(p_after_id, '') = '' or d.id > p_after_id)
    order by d.id
    limit p_limit
  ) page;
  return result;
end;
$function$;

create or replace function public.gc_align_processed_document_status()
returns integer
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
declare affected integer;
begin
  perform public.gc_assert_runtime_secret();

  update gestionale.documents d
     set data = jsonb_set(d.data, '{status}', '"processato"'::jsonb, true),
         updated_at = now()
   where d.collection = any(array[
           'documents_inbox',
           'documents_inbox__shard_001'
         ]::text[])
     and (d.data @> '{"processed": true}'::jsonb
          or d.data @> '{"xml_processed": true}'::jsonb)
     and (not d.data ? 'status'
          or d.data->'status' = 'null'::jsonb
          or d.data->>'status' in ('nuovo', 'da_processare'));
  get diagnostics affected = row_count;
  return affected;
end;
$function$;

revoke all on function public.gc_fetch_collection_after_projected(text, text, integer, text[])
  from public, anon, authenticated;
revoke all on function public.gc_align_processed_document_status()
  from public, anon, authenticated;
grant execute on function public.gc_fetch_collection_after_projected(text, text, integer, text[])
  to anon, service_role;
grant execute on function public.gc_align_processed_document_status()
  to anon, service_role;

-- Chiude anche il permesso implicito della precedente RPC keyset.
revoke all on function public.gc_fetch_collection_after(text, text, integer)
  from public, anon, authenticated;
grant execute on function public.gc_fetch_collection_after(text, text, integer)
  to anon, service_role;
