-- Keyset pagination for large document collections.
-- Keeps the runtime secret check and does not alter authentication or data.
create or replace function public.gc_fetch_collection_after(
  p_collection text,
  p_after_id text default '',
  p_limit integer default 100
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
  set local statement_timeout = 0;
  set local work_mem = '128MB';
  select coalesce(jsonb_agg(page.document order by page.id), '[]'::jsonb)
  into result
  from (
    select d.id, d.data || jsonb_build_object('_id', d.id) as document
    from gestionale.documents d
    where d.collection = p_collection
      and (coalesce(p_after_id, '') = '' or d.id > p_after_id)
    order by d.id
    limit p_limit
  ) page;
  return result;
end;
$function$;
