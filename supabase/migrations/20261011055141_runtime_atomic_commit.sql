-- Conferma atomica delle mutazioni runtime: confronto con la versione letta,
-- stesso lock degli upsert storici, rollback dell'intera unità di lavoro.
create or replace function public.gc_commit_documents(p_changes jsonb)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $function$
declare
  change jsonb;
  current_data jsonb;
  collection_name text;
  upserts jsonb;
  result jsonb;
  duplicate_result jsonb;
begin
  perform public.gc_assert_runtime_secret();
  if p_changes is null or jsonb_typeof(p_changes) <> 'array' then
    raise invalid_parameter_value using message = 'mutazioni non valide';
  end if;
  if exists (
    select 1 from jsonb_array_elements(p_changes) c
    where jsonb_typeof(c) <> 'object'
      or coalesce(c->>'collection', '') = '' or coalesce(c->>'id', '') = ''
      or not (c ? 'before' and c ? 'after')
      or jsonb_typeof(c->'before') not in ('null', 'object')
      or jsonb_typeof(c->'after') not in ('null', 'object')
      or (jsonb_typeof(c->'after') = 'object' and c->'after'->>'_id' is distinct from c->>'id')
  ) or exists (
    select 1 from jsonb_array_elements(p_changes) c
    group by c->>'collection', c->>'id' having count(*) > 1
  ) then
    raise invalid_parameter_value using message = 'mutazione senza identità univoca';
  end if;

  -- Ordine stabile anche per le transazioni che toccano più collezioni.
  for collection_name in
    select distinct c->>'collection' from jsonb_array_elements(p_changes) c order by 1
  loop
    perform pg_advisory_xact_lock(hashtext('gc_upsert_documents:' || collection_name));
  end loop;

  for change in select c from jsonb_array_elements(p_changes) c order by c->>'collection', c->>'id'
  loop
    select data into current_data from gestionale.documents
      where collection = change->>'collection' and id = change->>'id' for update;
    if (change->'before' = 'null'::jsonb and found)
       or (change->'before' <> 'null'::jsonb and
           (not found or current_data is distinct from ((change->'before') - '_id'))) then
      return jsonb_build_object('status', 'conflict');
    end if;
  end loop;

  -- Il blocco ha una subtransazione: anche un duplicato dell'ultima
  -- collezione annulla gli inserimenti nelle collezioni precedenti.
  begin
    -- Stessa autorizzazione delle RPC delete esistenti, dentro la sola
    -- transazione autenticata e dopo il confronto di tutte le versioni.
    perform gestionale.consenti_cancellazione();
    for collection_name in
      select distinct c->>'collection' from jsonb_array_elements(p_changes) c order by 1
    loop
      delete from gestionale.documents d using jsonb_array_elements(p_changes) c
        where c->>'collection' = collection_name and c->'after' = 'null'::jsonb
          and d.collection = collection_name and d.id = c->>'id';
      select jsonb_agg(c->'after') into upserts from jsonb_array_elements(p_changes) c
        where c->>'collection' = collection_name and c->'after' <> 'null'::jsonb;
      if upserts is not null then
        result := public.gc_upsert_documents(collection_name, upserts);
        if jsonb_array_length(coalesce(result->'rejected', '[]'::jsonb)) > 0 then
          duplicate_result := jsonb_build_object('status', 'duplicate',
            'collection', collection_name, 'rejected', result->'rejected');
          raise exception using errcode = 'P0002', message = 'chiave duplicata';
        end if;
      end if;
    end loop;
  exception when no_data_found then
    if duplicate_result is null then raise; end if;
    return duplicate_result;
  end;
  return jsonb_build_object('status', 'committed');
end;
$function$;
revoke all on function public.gc_commit_documents(jsonb) from public, authenticated;
grant execute on function public.gc_commit_documents(jsonb) to anon, service_role;
