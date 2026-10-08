-- Le funzioni trigger sono invocate dal motore PostgreSQL, non dai client.
-- Togliere EXECUTE ai ruoli API riduce la superficie esposta senza cambiare
-- il funzionamento dei trigger associati alle tabelle.
do $migration$
declare
  funzione record;
begin
  for funzione in
    select n.nspname as schema_name,
           p.proname as function_name,
           pg_get_function_identity_arguments(p.oid) as arguments
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where p.prorettype = 'trigger'::regtype
       and n.nspname in ('gestionale', 'hr', 'lotti', 'menu', 'public', 'cassa', 'catalogo')
  loop
    execute format(
      'revoke execute on function %I.%I(%s) from public, anon, authenticated',
      funzione.schema_name,
      funzione.function_name,
      funzione.arguments
    );
  end loop;
end
$migration$;
