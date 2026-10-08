-- Letture puntuali per find_one e mutazioni: evita di trasferire l'intera
-- collezione prima di inserire o aggiornare un singolo documento.

create index if not exists documents_collection_logical_id_idx
  on gestionale.documents (collection, (data->>'id'));

create or replace function public.gc_fetch_documents_exact(
  p_collection text,
  p_field text,
  p_values text[],
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
  if p_field not in ('_id', 'id', 'idempotency_key', 'file_hash', 'content_hash') then
    raise invalid_parameter_value using message = 'campo lookup non consentito';
  end if;
  if coalesce(array_length(p_values, 1), 0) < 1
     or coalesce(array_length(p_values, 1), 0) > 500 then
    raise invalid_parameter_value using message = 'valori lookup non validi';
  end if;
  if coalesce(array_length(p_exclude_fields, 1), 0) > 32 then
    raise invalid_parameter_value using message = 'troppe esclusioni';
  end if;

  select coalesce(jsonb_agg(page.document order by page.id), '[]'::jsonb)
  into result
  from (
    select d.id,
           (d.data - coalesce(p_exclude_fields, array[]::text[]))
             || jsonb_build_object('_id', d.id) as document
    from gestionale.documents d
    where d.collection = p_collection
      and case p_field
        when '_id' then d.id = any(p_values)
        when 'id' then d.data->>'id' = any(p_values)
        when 'idempotency_key' then d.idempotency_key = any(p_values)
        when 'file_hash' then d.data->>'file_hash' = any(p_values)
        when 'content_hash' then d.data->>'content_hash' = any(p_values)
        else false
      end
    order by d.id
    limit 500
  ) page;
  return result;
end;
$function$;

revoke all on function public.gc_fetch_documents_exact(text, text, text[], text[])
  from public, anon, authenticated;
grant execute on function public.gc_fetch_documents_exact(text, text, text[], text[])
  to anon, service_role;
