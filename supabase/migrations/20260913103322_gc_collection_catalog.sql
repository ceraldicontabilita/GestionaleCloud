-- Startup needs current names/counts, not a digest of every JSON/PDF payload.
-- The existing digest manifest remains unchanged for integrity audits.
create or replace function public.gc_collection_catalog()
returns table(collection text, row_count bigint)
language plpgsql
security definer
set search_path to 'pg_catalog'
as $function$
begin
  perform public.gc_assert_runtime_secret();
  return query
  select d.collection, count(*)::bigint
  from gestionale.documents d
  group by d.collection
  order by d.collection;
end;
$function$;

-- Same callers and runtime-secret guard as gc_collection_manifest.
revoke all on function public.gc_collection_catalog() from public, anon, authenticated;
grant execute on function public.gc_collection_catalog() to anon, service_role;
