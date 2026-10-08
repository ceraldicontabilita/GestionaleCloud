-- Impedisce che un oggetto omonimo creato in uno schema anteposto nel
-- search_path venga risolto al posto delle tabelle/funzioni applicative.
do $$
declare
  funzione record;
begin
  for funzione in
    select p.oid::regprocedure as firma, n.nspname as schema_name
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'gestionale', 'hr', 'lotti', 'menu', 'cassa', 'catalogo')
      and not exists (
        select 1
        from unnest(coalesce(p.proconfig, '{}'::text[])) configurazione
        where configurazione like 'search_path=%'
      )
  loop
    if funzione.schema_name = 'public' then
      execute format(
        'alter function %s set search_path to public, extensions',
        funzione.firma
      );
    else
      execute format(
        'alter function %s set search_path to %I, public, extensions',
        funzione.firma,
        funzione.schema_name
      );
    end if;
  end loop;
end
$$;
