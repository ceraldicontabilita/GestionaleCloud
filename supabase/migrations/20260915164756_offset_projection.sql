-- Applica le proiezioni esclusive anche alle collezioni paginate a OFFSET.

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
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(btrim(p_collection), '') = '' then
    raise invalid_parameter_value using message = 'collezione mancante';
  end if;
  if p_offset < 0 or p_limit < 1 or p_limit > 500 then
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
    order by d.id
    offset p_offset
    limit p_limit
  ) page;
  return result;
end;
$function$;

revoke all on function public.gc_fetch_collection_projected(text, integer, integer, text[])
  from public, anon, authenticated;
grant execute on function public.gc_fetch_collection_projected(text, integer, integer, text[])
  to anon, service_role;
